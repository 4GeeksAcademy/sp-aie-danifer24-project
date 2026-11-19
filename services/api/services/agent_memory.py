"""
Agent Memory Service — episodic and semantic fact storage for the Nexova agent.

Uses **Redis** as backend with key prefix ``agent_memory:*``.
Never writes to Qdrant knowledge collections (``*_knowledge``).

Key layout
----------
- ``agent_memory:fact:<id>``           → Hash {id, type, content, entity, …}
- ``agent_memory:fact_ids``            → Set of active fact IDs
- ``agent_memory:proposal``            → Hash {fact_json, created_at, source_run_id} (singleton pending proposal)
- ``agent_memory:audit:<ts>:<uuid>``   → Hash {action, user_id, …}
- ``agent_memory:next_id``             → Atomic counter
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import redis as _redis

logger = logging.getLogger(__name__)


class AgentMemoryService:
    """Persistent fact store for agent-learned knowledge backed by Redis."""

    REDIS_PREFIX = "agent_memory:"
    MAX_FACTS = 200
    EXPIRY_DAYS = 90
    PROPOSAL_KEY = f"{REDIS_PREFIX}proposal"

    def __init__(self, redis_url: str = "redis://redis:6379/0") -> None:
        self._redis = _redis.Redis.from_url(redis_url, decode_responses=True)

    # ── Fact CRUD ──────────────────────────────────────────────────────────

    def store_fact(self, fact: dict) -> str:
        """
        Persist an approved fact with auditable metadata.

        Required *fact* keys: ``content``.
        Optional keys: ``type``, ``entity``, ``source_message``, ``approved_by``,
        ``business_line``.
        Returns the assigned fact ID (string).
        """
        fact_id = str(self._redis.incr(f"{self.REDIS_PREFIX}next_id"))
        now = datetime.now(timezone.utc).isoformat()
        record = {
            "id": fact_id,
            "type": fact.get("type", "general"),
            "content": fact["content"],
            "entity": fact.get("entity", ""),
            "business_line": fact.get("business_line", "general"),
            "created_at": now,
            "updated_at": now,
            "source_message": fact.get("source_message", ""),
            "approved_by": str(fact.get("approved_by", "unknown")),
        }
        key = f"{self.REDIS_PREFIX}fact:{fact_id}"
        self._redis.hset(key, mapping=record)
        self._redis.sadd(f"{self.REDIS_PREFIX}fact_ids", fact_id)
        logger.info("AgentMemory fact stored id=%s type=%s", fact_id, record["type"])
        return fact_id

    def get_facts(
        self, limit: int = 20, fact_type: Optional[str] = None
    ) -> list[dict[str, Any]]:
        """Return recent facts, newest first, optionally filtered by ``fact_type``."""
        ids = self._redis.smembers(f"{self.REDIS_PREFIX}fact_ids")
        if not ids:
            return []
        facts: list[dict[str, Any]] = []
        for fid in ids:
            record = self._redis.hgetall(f"{self.REDIS_PREFIX}fact:{fid}")
            if record:
                if fact_type and record.get("type") != fact_type:
                    continue
                facts.append(record)
        facts.sort(key=lambda f: f.get("created_at", ""), reverse=True)
        return facts[:limit]

    def get_fact_by_id(self, fact_id: str) -> Optional[dict[str, Any]]:
        """Retrieve a single fact by its ID."""
        record = self._redis.hgetall(f"{self.REDIS_PREFIX}fact:{fact_id}")
        return record if record else None

    def delete_fact(self, fact_id: str) -> bool:
        """Remove a fact and its ID from the active set."""
        key = f"{self.REDIS_PREFIX}fact:{fact_id}"
        deleted = self._redis.delete(key)
        self._redis.srem(f"{self.REDIS_PREFIX}fact_ids", fact_id)
        return deleted > 0

    # ── Search ─────────────────────────────────────────────────────────────

    def search_facts(
        self,
        query: str,
        limit: int = 5,
        embedding_fn: Optional[Callable[[str], list[float]]] = None,
    ) -> list[dict[str, Any]]:
        """
        Search facts by semantic similarity when *embedding_fn* is provided.

        Falls back to keyword filtering on ``content`` and ``entity`` fields
        when no embedding function is available.
        """
        if embedding_fn is not None:
            # Future enhancement: embed query, compare with stored vectors
            logger.warning("Semantic search via embedding_fn not yet wired; "
                           "falling back to keyword matching.")

        query_lower = query.casefold()
        ids = self._redis.smembers(f"{self.REDIS_PREFIX}fact_ids")
        if not ids:
            return []

        results: list[dict[str, Any]] = []
        for fid in ids:
            record = self._redis.hgetall(f"{self.REDIS_PREFIX}fact:{fid}")
            if not record:
                continue
            content = record.get("content", "").casefold()
            entity = record.get("entity", "").casefold()
            if query_lower in content or query_lower in entity:
                results.append(record)

        results.sort(key=lambda f: f.get("created_at", ""), reverse=True)
        return results[:limit]

    # ── Consolidation ──────────────────────────────────────────────────────

    def consolidate(self) -> dict[str, int]:
        """
        Run the consolidation policy:

        1. **Expiry** – remove facts untouched for ``EXPIRY_DAYS``.
        2. **Deduplication** – keep only the newest copy when content matches.
        3. **Merging** – for facts sharing the same ``(entity, type)``, keep
           the most recent one and concatenate source messages.
        4. **Cap** – enforce ``MAX_FACTS`` upper bound (drop oldest).

        Returns a summary dict with counters.
        """
        report: dict[str, int] = {
            "removed_expired": 0,
            "removed_duplicates": 0,
            "merged": 0,
            "removed_excess": 0,
            "remaining": 0,
        }
        now = datetime.now(timezone.utc)
        ids = self._redis.smembers(f"{self.REDIS_PREFIX}fact_ids")
        if not ids:
            return report

        cutoff = now.timestamp() - (self.EXPIRY_DAYS * 86400)
        seen_content: dict[str, tuple[str, str]] = {}
        entity_type_groups: dict[tuple[str, str], list[dict[str, Any]]] = {}

        for fid in list(ids):
            record = self._redis.hgetall(f"{self.REDIS_PREFIX}fact:{fid}")
            if not record:
                self._redis.srem(f"{self.REDIS_PREFIX}fact_ids", fid)
                continue

            # 1. Expiry
            updated_str = record.get("updated_at", record.get("created_at", ""))
            try:
                updated_ts = datetime.fromisoformat(updated_str).timestamp()
            except (ValueError, TypeError):
                updated_ts = 0
            if updated_ts < cutoff:
                self.delete_fact(fid)
                report["removed_expired"] += 1
                continue

            # 2. Deduplication by content hash
            content = record.get("content", "").strip()
            content_hash = str(hash(content))
            if content_hash in seen_content:
                existing_id, existing_ts = seen_content[content_hash]
                if updated_ts > (
                    datetime.fromisoformat(existing_ts).timestamp()
                    if existing_ts
                    else 0
                ):
                    self.delete_fact(existing_id)
                    seen_content[content_hash] = (fid, updated_str)
                else:
                    self.delete_fact(fid)
                report["removed_duplicates"] += 1
                continue
            seen_content[content_hash] = (fid, updated_str)

            # 3. Group for merging (entity + type)
            key = (record.get("entity", ""), record.get("type", "general"))
            entity_type_groups.setdefault(key, []).append(record)

        # 3b. Merge similar groups
        merged_ids: set[str] = set()
        for (entity, ftype), group in entity_type_groups.items():
            if len(group) <= 1:
                continue
            group.sort(key=lambda f: f.get("created_at", ""), reverse=True)
            keeper = group[0]
            for duplicate in group[1:]:
                existing_sources = keeper.get("source_message", "")
                dup_source = duplicate.get("source_message", "")
                if dup_source and dup_source not in existing_sources:
                    keeper["source_message"] = (
                        existing_sources + " | " + dup_source
                        if existing_sources
                        else dup_source
                    )
                self.delete_fact(duplicate["id"])
                merged_ids.add(duplicate["id"])
                report["merged"] += 1
            if merged_ids:
                keeper["updated_at"] = now.isoformat()
                self._redis.hset(
                    f"{self.REDIS_PREFIX}fact:{keeper['id']}", mapping=keeper
                )

        # 4. Cap at MAX_FACTS
        remaining_ids = sorted(
            self._redis.smembers(f"{self.REDIS_PREFIX}fact_ids"),
            key=lambda fid: (
                self._redis.hget(f"{self.REDIS_PREFIX}fact:{fid}", "created_at")
                or ""
            ),
            reverse=True,
        )
        if len(remaining_ids) > self.MAX_FACTS:
            for fid in remaining_ids[self.MAX_FACTS :]:
                self.delete_fact(fid)
                report["removed_excess"] += 1

        report["remaining"] = self._redis.scard(f"{self.REDIS_PREFIX}fact_ids")
        logger.info("AgentMemory consolidate: %s", report)
        return report

    # ── Audit log ──────────────────────────────────────────────────────────

    def log_audit(self, entry: dict[str, Any]) -> None:
        """
        Record a memory-related decision.

        *entry* keys: ``action``, ``user_id``, ``fact_id``, ``detail``,
        ``proposal_content``.
        """
        ts = datetime.now(timezone.utc)
        audit_id = uuid.uuid4().hex[:12]
        key = (
            f"{self.REDIS_PREFIX}audit:{ts.strftime('%Y%m%dT%H%M%S')}:{audit_id}"
        )
        record = {
            "timestamp": ts.isoformat(),
            "action": entry.get("action", "unknown"),
            "user_id": str(entry.get("user_id", "unknown")),
            "fact_id": str(entry.get("fact_id", "")),
            "detail": entry.get("detail", ""),
            "proposal_content": entry.get("proposal_content", ""),
        }
        self._redis.hset(key, mapping=record)
        self._redis.expire(key, 365 * 86400)  # auto-clean after 1 year
        logger.info("AgentMemory audit: %s (%s)", record["action"], audit_id)

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Return the most recent audit entries."""
        cursor = 0
        pattern = f"{self.REDIS_PREFIX}audit:*"
        keys: list[str] = []
        while True:
            cursor, batch = self._redis.scan(cursor, match=pattern, count=100)
            keys.extend(batch)
            if cursor == 0:
                break
        keys.sort(reverse=True)
        entries: list[dict[str, Any]] = []
        for key in keys[:limit]:
            entry = self._redis.hgetall(key)
            if entry:
                entries.append(entry)
        return entries

    # ── Pending proposal (singleton) ───────────────────────────────────────

    def get_proposal(self) -> Optional[dict[str, Any]]:
        """Return the current pending proposal, or ``None``."""
        raw = self._redis.hgetall(self.PROPOSAL_KEY)
        if not raw:
            return None
        try:
            fact_data = json.loads(raw.get("fact_json", "{}"))
        except (json.JSONDecodeError, TypeError):
            return None
        return {
            "fact": fact_data,
            "created_at": raw.get("created_at", ""),
            "source_run_id": raw.get("source_run_id", ""),
        }

    def set_proposal(self, fact: dict, source_run_id: str = "") -> None:
        """Store a pending proposal. Overwrites any existing proposal silently."""
        mapping = {
            "fact_json": json.dumps(fact, ensure_ascii=False),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "source_run_id": source_run_id,
        }
        self._redis.hset(self.PROPOSAL_KEY, mapping=mapping)
        # Expire after 24 h so stale proposals don't block indefinitely
        self._redis.expire(self.PROPOSAL_KEY, 86400)
        logger.info(
            "AgentMemory proposal set type=%s entity=%s",
            fact.get("type"),
            fact.get("entity"),
        )

    def clear_proposal(self) -> None:
        """Remove the current pending proposal."""
        self._redis.delete(self.PROPOSAL_KEY)
        logger.debug("AgentMemory proposal cleared")

    def has_proposal(self) -> bool:
        """Check whether a proposal is currently pending."""
        return self._redis.exists(self.PROPOSAL_KEY) > 0

    # ── Lifecycle ──────────────────────────────────────────────────────────

    def close(self) -> None:
        """Release the Redis connection."""
        try:
            self._redis.close()
        except Exception:
            pass


# Module-level singleton — one instance per process.
_memory_service: Optional[AgentMemoryService] = None


def get_memory_service(
    redis_url: str = "redis://redis:6379/0",
) -> AgentMemoryService:
    """Return the shared ``AgentMemoryService`` singleton (lazy init)."""
    global _memory_service
    if _memory_service is None:
        _memory_service = AgentMemoryService(redis_url)
    return _memory_service