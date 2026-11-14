"""Prepare and index Nexova's Markdown corpus in Qdrant (phase 1).

Copy this module to data/process/rag.py once that directory is writable.
Idempotency uses tenant-filtered clean-and-reload plus deterministic UUIDv5 IDs.
"""

from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

from openai import OpenAI
from qdrant_client import QdrantClient, models

COLLECTION_NAME = "nexova_knowledge"
COMPANY = "nexova"
DEFAULT_EMBEDDING_MODEL = "pplx-embed-v1-0.6b"
DEFAULT_EMBEDDING_BASE_URL = "https://api.perplexity.ai"
def _find_documents_dir() -> Path:
    """Find the corpus relative to either scripts/ or data/process/."""
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "docs" / "company-knowledge-base"
        if candidate.is_dir():
            return candidate
    return Path(__file__).resolve().parents[1] / "docs" / "company-knowledge-base"


DEFAULT_DOCUMENTS_DIR = _find_documents_dir()
MAX_CHUNK_CHARS = 1200


@dataclass(frozen=True)
class Chunk:
    source_document: str
    section: str
    chunk_index: int
    text: str


def _embedding_client() -> OpenAI:
    api_key = os.getenv("LLM_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Define LLM_API_KEY en .env con la credencial proporcionada "
            "por la academia."
        )
    return OpenAI(
        api_key=api_key,
        base_url=os.getenv("LLM_BASE_URL", DEFAULT_EMBEDDING_BASE_URL),
    )


def _qdrant_client() -> QdrantClient:
    return QdrantClient(url=os.getenv("QDRANT_URL", "http://localhost:6333"))


def embed(text: str) -> list[float]:
    """Create one embedding using Perplexity's dedicated embedding endpoint."""
    if not text.strip():
        raise ValueError("No se puede generar un embedding para texto vacío.")
    response = _embedding_client().embeddings.create(
        model=os.getenv("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL),
        input=[text],
    )
    vector = response.data[0].embedding
    if not vector:
        raise ValueError("El proveedor devolvió un embedding vacío.")
    return [float(value) for value in vector]


def _split_at_sentence_boundaries(text: str, max_chars: int) -> list[str]:
    """Split oversized semantic units at sentence boundaries only."""
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    parts: list[str] = []
    current: list[str] = []
    length = 0
    for sentence in sentences:
        if len(sentence) > max_chars:
            raise ValueError(
                "Una frase supera MAX_CHUNK_CHARS; no se dividirá por la mitad. "
                "Aumenta el límite o revisa el documento fuente."
            )
        extra = len(sentence) + (1 if current else 0)
        if current and length + extra > max_chars:
            parts.append(" ".join(current))
            current = []
            length = 0
        current.append(sentence)
        length += len(sentence) + (1 if len(current) > 1 else 0)
    if current:
        parts.append(" ".join(current))
    return parts


def _semantic_units(markdown: str) -> list[tuple[str, str]]:
    """Return (section, unit) pairs, retaining headings, bullets and paragraphs."""
    section = "General"
    units: list[tuple[str, str]] = []
    paragraph: list[str] = []

    def flush() -> None:
        text = " ".join(line.strip() for line in paragraph if line.strip()).strip()
        if text:
            units.append((section, text))
        paragraph.clear()

    for line in markdown.splitlines():
        stripped = line.strip()
        heading = re.match(r"^#{1,6}\s+(.+?)\s*#*\s*$", stripped)
        if heading:
            flush()
            section = heading.group(1)
            continue
        if not stripped:
            flush()
            continue
        # A Markdown list item is its own semantic unit. Wrapped continuation
        # lines remain with that item until a blank line or the next list item.
        is_list_item = bool(re.match(r"^(?:[-*+]\s+|\d+[.)]\s+)", stripped))
        if is_list_item:
            flush()
        paragraph.append(stripped)
    flush()
    return units


def prepare_document(path: Path, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """Parse Markdown and form self-contained chunks without cutting sentences."""
    if max_chars <= 0:
        raise ValueError("max_chars debe ser positivo.")
    markdown = path.read_text(encoding="utf-8")
    initial_section = path.stem.removeprefix("nexova-").replace("-", " ").title()
    units = _semantic_units(markdown)
    if units and units[0][0] == "General":
        units[0] = (initial_section, units[0][1])

    chunks: list[Chunk] = []
    for section, unit in units:
        for text in _split_at_sentence_boundaries(unit, max_chars):
            chunks.append(
                Chunk(
                    source_document=path.stem.removeprefix("nexova-"),
                    section=section,
                    chunk_index=len(chunks),
                    text=text,
                )
            )
    return chunks


def _point_id(chunk: Chunk) -> str:
    identity = f"{COMPANY}:{chunk.source_document}:{chunk.chunk_index}:{chunk.text}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def _collection_vector_size(info: Any) -> int | None:
    vectors = info.config.params.vectors
    if isinstance(vectors, dict):
        sizes = {config.size for config in vectors.values()}
        if len(sizes) != 1:
            raise ValueError("La colección Qdrant debe usar un único tamaño de vector.")
        return sizes.pop()
    return vectors.size


def setup(
    documents_dir: str | Path = DEFAULT_DOCUMENTS_DIR,
    *,
    client: Any | None = None,
    embedding_function: Callable[[str], list[float]] | None = None,
    max_chars: int = MAX_CHUNK_CHARS,
) -> dict[str, Any]:
    """Chunk and index all Markdown documents in docs/company-knowledge-base/."""
    source_dir = Path(documents_dir)
    if not source_dir.is_dir():
        raise FileNotFoundError(f"No existe el corpus de conocimiento: {source_dir}")
    paths = sorted(source_dir.glob("*.md"))
    if not paths:
        raise ValueError(f"No hay documentos Markdown en {source_dir}")
    chunks = [
        chunk
        for path in paths
        for chunk in prepare_document(path, max_chars=max_chars)
    ]
    if not chunks:
        raise ValueError(f"El corpus no contiene texto indexable: {source_dir}")

    make_embedding = embedding_function or embed
    vectors = [make_embedding(chunk.text) for chunk in chunks]
    vector_size = len(vectors[0])
    if vector_size == 0 or any(len(vector) != vector_size for vector in vectors):
        raise ValueError("El proveedor devolvió embeddings vacíos o de dimensiones distintas.")

    qdrant = client or _qdrant_client()
    if not qdrant.collection_exists(COLLECTION_NAME):
        qdrant.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=models.VectorParams(
                size=vector_size,
                distance=models.Distance.COSINE,
            ),
        )
    else:
        existing_size = _collection_vector_size(qdrant.get_collection(COLLECTION_NAME))
        if existing_size != vector_size:
            raise ValueError(
                f"La colección {COLLECTION_NAME} tiene dimensión {existing_size}, "
                f"pero el modelo configurado produce {vector_size}. Recrea la colección "
                "tras confirmar que contiene solo datos de esta aplicación."
            )

    # Delete only Nexova's points so other tenants in a shared collection survive.
    qdrant.delete(
        collection_name=COLLECTION_NAME,
        points_selector=models.FilterSelector(
            filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="company",
                        match=models.MatchValue(value=COMPANY),
                    )
                ]
            )
        ),
        wait=True,
    )
    qdrant.upsert(
        collection_name=COLLECTION_NAME,
        points=[
            models.PointStruct(
                id=_point_id(chunk),
                vector=vector,
                payload={
                    "source_document": chunk.source_document,
                    "section": chunk.section,
                    "company": COMPANY,
                    "language": "es",
                    "chunk_index": chunk.chunk_index,
                    "text": chunk.text,
                },
            )
            for chunk, vector in zip(chunks, vectors)
        ],
        wait=True,
    )
    return {
        "collection": COLLECTION_NAME,
        "documents": len(paths),
        "chunks": len(chunks),
        "vector_size": vector_size,
        "directory": str(source_dir),
        "idempotency": "limpieza filtrada por company=nexova y recarga con UUIDv5 deterministas",
    }


if __name__ == "__main__":
    print(setup())
