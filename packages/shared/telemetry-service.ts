/**
 * TelemetryService: cliente universal de telemetría para todas las apps (Website, Backoffice, Tracker)
 * - Validación estricta de eventos contra schema
 * - Cola en memoria con reintentos
 * - Captura de userId pseudonimizado desde /api/auth/me
 * - Flush automático y al cerrar sesión
 */

import { TELEMETRY_SCHEMA_VERSION } from "./telemetry";

export const ACCESS_TOKEN_STORAGE_KEY = "nexova_access_token";

type TelemetryValue = string | number | boolean | null;

interface TelemetryEvent {
  eventId: string;
  timestamp: string;
  sessionId: string | null;
  userId: string | null;
  event_type: string;
  schemaVersion: typeof TELEMETRY_SCHEMA_VERSION;
  requestId: string;
  properties: Record<string, TelemetryValue>;
}

interface TelemetryConfig {
  endpoint?: string;
  batchSize?: number;
  flushIntervalMs?: number;
  retryDelaysMs?: number[];
  appVersion?: string;
}

const DEFAULT_CONFIG: Required<TelemetryConfig> = {
  endpoint: "/api/telemetry/events",
  batchSize: 20,
  flushIntervalMs: 10_000,
  retryDelaysMs: [500, 1_000, 2_000],
  appVersion: "unknown",
};

// Allowlist de propiedades por evento type
const allowedProperties: Record<string, readonly string[]> = {
  inbound_order_created: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id", "supplier_id", "unit_cost"],
  outbound_order_created: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id"],
  stock_threshold_triggered: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id", "stock_before", "stock_after", "minimum_stock"],
  direct_stock_edit_rejected: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "reason_code"],
  kit_cost_variance_detected: [
    "office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id", "supplier_id",
    "unit_cost", "baseline_unit_cost", "variance_ratio", "threshold_ratio", "direction", "baseline_window_days", "baseline_order_count",
  ],
  inventory_order_validation_failed: ["order_type", "layer", "field", "reason_code", "office", "product_id", "product_category", "programme_id", "quantity", "currency"],
  login_attempted: ["source"],
  login_succeeded: ["source", "duration_ms"],
  login_failed: ["reason_code", "layer", "duration_ms"],
  session_expired: ["reason_code", "source"],
  api_request_completed: ["route_template", "method", "status_code", "duration_ms"],
  frontend_data_load_completed: ["section", "outcome", "duration_ms", "reason_code"],
  frontend_unhandled_error: ["section", "source", "error_code", "fingerprint", "app_version"],
  backoffice_section_viewed: ["section", "entry_type"],
};

// Propiedades requeridas por evento type
const requiredProperties: Record<string, readonly string[]> = {
  inbound_order_created: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id", "supplier_id", "unit_cost"],
  outbound_order_created: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id"],
  stock_threshold_triggered: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id", "stock_before", "stock_after", "minimum_stock"],
  direct_stock_edit_rejected: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "reason_code"],
  kit_cost_variance_detected: ["office", "product_id", "product_category", "programme_id", "quantity", "currency", "order_id", "supplier_id", "unit_cost", "baseline_unit_cost", "variance_ratio", "threshold_ratio", "direction", "baseline_window_days", "baseline_order_count"],
  inventory_order_validation_failed: ["order_type", "layer", "field", "reason_code"],
  login_attempted: ["source"],
  login_succeeded: ["source", "duration_ms"],
  login_failed: ["reason_code", "layer", "duration_ms"],
  session_expired: ["reason_code", "source"],
  api_request_completed: ["route_template", "method", "status_code", "duration_ms"],
  frontend_data_load_completed: ["section", "outcome", "duration_ms"],
  frontend_unhandled_error: ["section", "source", "error_code", "fingerprint", "app_version"],
  backoffice_section_viewed: ["section", "entry_type"],
};

// Enums permitidos para validación
const propertyEnums: Record<string, readonly (string | number)[]> = {
  // Inventario
  "inbound_order_created.office": ["valencia", "miami"],
  "inbound_order_created.product_category": ["training_kit", "certification", "onboarding_equipment"],
  "inbound_order_created.currency": ["EUR", "USD"],
  "outbound_order_created.office": ["valencia", "miami"],
  "outbound_order_created.product_category": ["training_kit", "certification", "onboarding_equipment"],
  "outbound_order_created.currency": ["EUR", "USD"],
  "stock_threshold_triggered.office": ["valencia", "miami"],
  "stock_threshold_triggered.product_category": ["training_kit", "certification", "onboarding_equipment"],
  "stock_threshold_triggered.currency": ["EUR", "USD"],
  "direct_stock_edit_rejected.office": ["valencia", "miami"],
  "direct_stock_edit_rejected.product_category": ["training_kit", "certification", "onboarding_equipment"],
  "direct_stock_edit_rejected.currency": ["EUR", "USD"],
  "direct_stock_edit_rejected.reason_code": ["direct_stock_write_forbidden"],
  "kit_cost_variance_detected.office": ["valencia", "miami"],
  "kit_cost_variance_detected.product_category": ["training_kit", "certification", "onboarding_equipment"],
  "kit_cost_variance_detected.currency": ["EUR", "USD"],
  "kit_cost_variance_detected.direction": ["increase", "decrease"],
  "kit_cost_variance_detected.baseline_window_days": [90],
  // Autenticación
  "inventory_order_validation_failed.order_type": ["inbound", "outbound"],
  "inventory_order_validation_failed.layer": ["browser", "frontend", "backend"],
  "inventory_order_validation_failed.field": ["product_id", "quantity", "supplier_id", "assigned_to", "stock", "other"],
  "inventory_order_validation_failed.reason_code": ["required", "invalid_type", "out_of_range", "unknown_product", "direct_stock_write_forbidden", "other"],
  "inventory_order_validation_failed.office": ["valencia", "miami"],
  "inventory_order_validation_failed.product_category": ["training_kit", "certification", "onboarding_equipment"],
  "inventory_order_validation_failed.currency": ["EUR", "USD"],
  "login_attempted.source": ["backoffice", "website", "tracker"],
  "login_succeeded.source": ["backoffice", "website", "tracker"],
  "login_failed.reason_code": ["invalid_credentials", "network_error", "service_unavailable", "invalid_response", "unknown"],
  "login_failed.layer": ["frontend", "backend"],
  "session_expired.reason_code": ["token_expired"],
  "session_expired.source": ["backend"],
  // API y rendimiento
  "api_request_completed.route_template": [
    "/inventory/products", "/inventory/products/{id}", "/inventory/orders/inbound", "/inventory/orders/outbound", "/inventory/orders",
    "/auth/login", "/auth/me", "/auth/forgot-password", "/auth/reset-password", "/auth/change-password",
    "/users", "/users/{user_id}", "/profiles/me",
    "/suppliers", "/suppliers/{id}", "/suppliers/{id}/rate", "/suppliers/{id}/status",
    "/api/incidents", "/api/incidents/summary", "/api/incidents/{id}", "/api/incidents/{id}/status", "/api/incidents/analyze", "/api/incidents/results/report",
    "unmatched", "auxiliary",
  ],
  "api_request_completed.method": ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"],
  "frontend_data_load_completed.section": [
    "home", "inventory_products", "inventory_inbound", "inventory_outbound", "inventory_orders",
    "suppliers", "incidents", "incident_new", "account_profile", "account_password", "technical_validation",
    "login", "register", "password_recovery", "password_reset", "candidates", "candidate_detail", "unknown",
  ],
  "frontend_data_load_completed.outcome": ["ready", "empty", "error"],
  "frontend_data_load_completed.reason_code": ["network_error", "invalid_response", "unauthorized", "service_unavailable", "unknown"],
  // Errores
  "frontend_unhandled_error.section": [
    "home", "inventory_products", "inventory_inbound", "inventory_outbound", "inventory_orders",
    "suppliers", "incidents", "incident_new", "account_profile", "account_password", "technical_validation",
    "login", "register", "password_recovery", "password_reset", "candidates", "candidate_detail", "unknown",
  ],
  "frontend_unhandled_error.source": ["error_boundary", "window_error", "unhandled_rejection"],
  "frontend_unhandled_error.error_code": ["render_error", "chunk_load_error", "unhandled_rejection", "unknown"],
  // Navegación
  "backoffice_section_viewed.section": [
    "home", "inventory_products", "inventory_inbound", "inventory_outbound", "inventory_orders",
    "suppliers", "incidents", "incident_new", "account_profile", "account_password", "technical_validation",
    "login", "register", "password_recovery", "password_reset", "candidates", "candidate_detail", "unknown",
  ],
  "backoffice_section_viewed.entry_type": ["direct", "menu", "internal_link", "history", "unknown"],
};

const integerProperties = new Set([
  "product_id", "quantity", "order_id", "supplier_id", "stock_before", "stock_after",
  "minimum_stock", "baseline_window_days", "baseline_order_count", "status_code",
]);

const userRequiredEventTypes = new Set([
  "inbound_order_created", "outbound_order_created", "stock_threshold_triggered",
  "kit_cost_variance_detected", "login_succeeded", "backoffice_section_viewed",
]);

const sessionStorageKey = "nexova_telemetry_session_id";

class TelemetryServiceImpl {
  private config: Required<TelemetryConfig>;
  private queue: TelemetryEvent[] = [];
  private userIdCache: string | null | undefined;
  private userIdRequest: Promise<string | null> | undefined;
  private userIdCacheToken: string | null | undefined;
  private identityGeneration = 0;
  private initialized = false;
  private flushing = false;

  constructor(config?: TelemetryConfig) {
    this.config = { ...DEFAULT_CONFIG, ...config };
  }

  private uuidV4(): string {
    if (typeof crypto.randomUUID === "function") return crypto.randomUUID();
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    const hex = [...bytes].map((value) => value.toString(16).padStart(2, "0")).join("");
    return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
  }

  private readSessionStorage(key: string): string | null {
    try {
      return typeof window !== "undefined" ? window.sessionStorage?.getItem(key) : null;
    } catch {
      return null;
    }
  }

  private writeSessionStorage(key: string, value: string): void {
    try {
      if (typeof window !== "undefined") window.sessionStorage?.setItem(key, value);
    } catch {
      // Keep telemetry functional when storage is disabled
    }
  }

  private resetUserIdentity(): void {
    this.identityGeneration += 1;
    this.userIdCache = undefined;
    this.userIdRequest = undefined;
    this.userIdCacheToken = undefined;
  }

  private getSessionId(eventType: string): string | null {
    if (eventType === "login_attempted") {
      const sessionId = this.uuidV4();
      this.writeSessionStorage(sessionStorageKey, sessionId);
      this.resetUserIdentity();
      return sessionId;
    }
    if (eventType === "login_succeeded") {
      const sessionId = this.readSessionStorage(sessionStorageKey) ?? this.uuidV4();
      this.writeSessionStorage(sessionStorageKey, sessionId);
      this.resetUserIdentity();
      return sessionId;
    }
    if (eventType === "login_failed" || eventType === "session_expired") {
      return this.readSessionStorage(sessionStorageKey);
    }
    let sessionId = this.readSessionStorage(sessionStorageKey);
    if (!sessionId) {
      sessionId = this.uuidV4();
      this.writeSessionStorage(sessionStorageKey, sessionId);
    }
    return sessionId;
  }

  private async authenticatedUserId(): Promise<string | null> {
    let token: string | null;
    try {
      token = typeof window !== "undefined" ? window.localStorage?.getItem(ACCESS_TOKEN_STORAGE_KEY) : null;
    } catch {
      token = null;
    }
    if (token !== this.userIdCacheToken) {
      this.resetUserIdentity();
      this.userIdCacheToken = token;
    }
    if (this.userIdCache !== undefined) return this.userIdCache;
    if (this.userIdRequest) return this.userIdRequest;
    if (!token) {
      this.userIdCache = null;
      return null;
    }

    const generation = this.identityGeneration;
    const request = fetch("/api/auth/me", {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
    })
      .then(async (response) => {
        if (!response.ok) return null;
        const payload: unknown = await response.json().catch(() => null);
        if (!payload || typeof payload !== "object" || !("telemetry_user_id" in payload)) return null;
        const userId = payload.telemetry_user_id;
        return typeof userId === "string" && /^u1_[a-f0-9]{64}$/.test(userId) ? userId : null;
      })
      .catch(() => null)
      .then((userId) => {
        let currentToken: string | null;
        try {
          currentToken = typeof window !== "undefined" ? window.localStorage?.getItem(ACCESS_TOKEN_STORAGE_KEY) : null;
        } catch {
          currentToken = null;
        }
        if (generation !== this.identityGeneration || currentToken !== token) return null;
        this.userIdCache = userId;
        return userId;
      });

    const trackedRequest = request.finally(() => {
      if (this.userIdRequest === trackedRequest) this.userIdRequest = undefined;
    });
    this.userIdRequest = trackedRequest;
    return this.userIdRequest;
  }

  private cleanProperties(eventType: string, properties: Record<string, unknown>): Record<string, TelemetryValue> | null {
    const allowlist = allowedProperties[eventType];
    if (!allowlist || !properties || typeof properties !== "object" || Array.isArray(properties)) return null;
    const result: Record<string, TelemetryValue> = {};
    for (const key of allowlist) {
      if (!(key in properties)) continue;
      const value = properties[key];
      if (value === null || typeof value === "string" || typeof value === "boolean" || (typeof value === "number" && Number.isFinite(value))) {
        if (typeof value === "string" && (value.length > 200 || /[\r\n\0]/.test(value))) return null;
        const enumValues = propertyEnums[`${eventType}.${key}`];
        if (enumValues && !enumValues.includes(value as string | number)) return null;
        if (typeof value === "number" && !this.validNumber(eventType, key, value)) return null;
        result[key] = value as TelemetryValue;
      } else {
        return null;
      }
    }
    if (requiredProperties[eventType]?.some((key) => !(key in result))) return null;
    if (result.office === "valencia" && result.currency !== "EUR") return null;
    if (result.office === "miami" && result.currency !== "USD") return null;
    return result;
  }

  private validNumber(eventType: string, key: string, value: number): boolean {
    if (!Number.isFinite(value)) return false;
    if (integerProperties.has(key) && !Number.isSafeInteger(value)) return false;
    if (["product_id", "order_id", "supplier_id", "minimum_stock", "baseline_order_count"].includes(key) && value < 1) return false;
    if (["quantity", "stock_before", "stock_after", "unit_cost"].includes(key) && value < 0) return false;
    if (key === "duration_ms") return value >= 0 && value <= 86_400_000;
    if (key === "status_code") return value >= 100 && value <= 599;
    if (["baseline_unit_cost", "variance_ratio", "threshold_ratio"].includes(key)) return value > 0;
    if (eventType === "inventory_order_validation_failed" && key === "quantity") return Number.isSafeInteger(value);
    return true;
  }

  private initialize(): void {
    if (this.initialized || typeof window === "undefined") return;
    this.initialized = true;
    window.addEventListener("storage", (event) => {
      if (event.key === ACCESS_TOKEN_STORAGE_KEY || event.key === null) {
        this.resetUserIdentity();
        try {
          window.sessionStorage?.removeItem(sessionStorageKey);
        } catch {
          // Optional cache
        }
      }
    });
    window.setInterval(() => {
      void this.flushQueue();
    }, this.config.flushIntervalMs);
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "hidden") this.flushBeacon();
    });
    window.addEventListener("pagehide", () => this.flushBeacon());
  }

  private removeEvents(events: TelemetryEvent[]): void {
    const ids = new Set(events.map((event) => event.eventId));
    for (let index = this.queue.length - 1; index >= 0; index -= 1) {
      if (ids.has(this.queue[index].eventId)) this.queue.splice(index, 1);
    }
  }

  private batchFromQueue(): TelemetryEvent[] {
    const batch: TelemetryEvent[] = [];
    for (const event of this.queue) {
      if (batch.length >= this.config.batchSize) break;
      const candidate = [...batch, event];
      if (new Blob([JSON.stringify({ events: candidate })]).size > 60 * 1024) break;
      batch.push(event);
    }
    return batch;
  }

  private async sendWithRetries(events: TelemetryEvent[]): Promise<boolean> {
    for (let attempt = 0; attempt <= this.config.retryDelaysMs.length; attempt += 1) {
      try {
        const response = await fetch(this.config.endpoint, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ events }),
          cache: "no-store",
        });
        if (response.ok) {
          const receipt: unknown = await response.json().catch(() => null);
          if (receipt && typeof receipt === "object" && "received" in receipt && receipt.received === events.length) return true;
        }
      } catch {
        // Retries are bounded; telemetry failures never block application work
      }
      if (attempt < this.config.retryDelaysMs.length) {
        await new Promise((resolve) => window.setTimeout(resolve, this.config.retryDelaysMs[attempt]));
      }
    }
    return false;
  }

  private async flushQueue(): Promise<void> {
    if (this.flushing || this.queue.length === 0 || typeof window === "undefined") return;
    const batch = this.batchFromQueue();
    if (batch.length === 0) {
      this.queue.shift();
      return;
    }
    this.flushing = true;
    try {
      await this.sendWithRetries(batch);
      this.removeEvents(batch);
    } finally {
      this.flushing = false;
      if (this.queue.length >= this.config.batchSize) void this.flushQueue();
    }
  }

  private flushBeacon(): void {
    if (typeof navigator === "undefined" || typeof navigator.sendBeacon !== "function") return;
    let batch = this.batchFromQueue();
    while (batch.length > 0) {
      const payload = new Blob([JSON.stringify({ events: batch })], { type: "application/json" });
      if (!navigator.sendBeacon(this.config.endpoint, payload)) return;
      this.removeEvents(batch);
      batch = this.batchFromQueue();
    }
  }

  track(eventType: string, properties: Record<string, unknown> = {}): void {
    if (typeof window === "undefined") return;
    this.initialize();
    const cleaned = this.cleanProperties(eventType, properties);
    if (!cleaned) return;

    const capturedAt = new Date().toISOString();
    const sessionId = this.getSessionId(eventType);
    const eventId = this.uuidV4();
    const requestId = this.uuidV4();
    const anonymous = eventType === "login_attempted" || eventType === "login_failed" || eventType === "session_expired";

    void (async () => {
      const userId = anonymous ? null : await this.authenticatedUserId();
      if (userRequiredEventTypes.has(eventType) && !userId) return;
      this.queue.push({
        eventId,
        timestamp: capturedAt,
        sessionId,
        userId,
        event_type: eventType,
        schemaVersion: TELEMETRY_SCHEMA_VERSION,
        requestId,
        properties: cleaned,
      });
      if (this.queue.length >= this.config.batchSize) void this.flushQueue();
    })();
  }
}

// Singleton exportado
export const telemetryService = new TelemetryServiceImpl();

// Export para instancias custom
export { TelemetryServiceImpl };
