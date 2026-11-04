/**
 * Instrumentación de eventos de negocio de inventario
 * Captura: ordenes de entrada/salida, umbrales de stock, variancia de costos, rechazos
 */

import { telemetryService } from "@packages/shared/telemetry-service";

export interface InboundOrderData {
  office: "valencia" | "miami";
  product_id: number;
  product_category: "training_kit" | "certification" | "onboarding_equipment";
  programme_id: string;
  quantity: number;
  currency: "EUR" | "USD";
  order_id: number;
  supplier_id: number;
  unit_cost: number;
}

export interface OutboundOrderData {
  office: "valencia" | "miami";
  product_id: number;
  product_category: "training_kit" | "certification" | "onboarding_equipment";
  programme_id: string;
  quantity: number;
  currency: "EUR" | "USD";
  order_id: number;
}

export interface StockThresholdData {
  office: "valencia" | "miami";
  product_id: number;
  product_category: "training_kit" | "certification" | "onboarding_equipment";
  programme_id: string;
  quantity: number;
  currency: "EUR" | "USD";
  order_id: number;
  stock_before: number;
  stock_after: number;
  minimum_stock: number;
}

export interface DirectStockEditRejectedData {
  office: "valencia" | "miami";
  product_id: number;
  product_category: "training_kit" | "certification" | "onboarding_equipment";
  programme_id: string;
  quantity: number;
  currency: "EUR" | "USD";
  reason_code: "direct_stock_write_forbidden";
}

export interface KitCostVarianceData {
  office: "valencia" | "miami";
  product_id: number;
  product_category: "training_kit" | "certification" | "onboarding_equipment";
  programme_id: string;
  quantity: number;
  currency: "EUR" | "USD";
  order_id: number;
  supplier_id: number;
  unit_cost: number;
  baseline_unit_cost: number;
  variance_ratio: number;
  threshold_ratio: number;
  direction: "increase" | "decrease";
  baseline_window_days: 90;
  baseline_order_count: number;
}

export interface OrderValidationFailedData {
  order_type: "inbound" | "outbound";
  layer: "browser" | "frontend" | "backend";
  field: "product_id" | "quantity" | "supplier_id" | "assigned_to" | "stock" | "other";
  reason_code: "required" | "invalid_type" | "out_of_range" | "unknown_product" | "direct_stock_write_forbidden" | "other";
  office?: "valencia" | "miami";
  product_id?: number;
  product_category?: "training_kit" | "certification" | "onboarding_equipment";
  programme_id?: string;
  quantity?: number;
  currency?: "EUR" | "USD";
}

/**
 * Registrar orden de entrada confirmada
 * Se dispara después de que la orden se commit exitosamente en backend
 */
export function trackInboundOrderCreated(data: InboundOrderData): void {
  telemetryService.track("inbound_order_created", data);
}

/**
 * Registrar orden de salida confirmada
 * Se dispara después de que la orden se commit exitosamente en backend
 */
export function trackOutboundOrderCreated(data: OutboundOrderData): void {
  telemetryService.track("outbound_order_created", data);
}

/**
 * Registrar cruce de umbral mínimo de stock
 * Se dispara cuando stock pasa de >= mínimo a < mínimo
 */
export function trackStockThresholdTriggered(data: StockThresholdData): void {
  telemetryService.track("stock_threshold_triggered", data);
}

/**
 * Registrar intento rechazado de edición directa de stock
 * Se dispara cuando el usuario intenta modificar stock fuera de una orden
 */
export function trackDirectStockEditRejected(data: DirectStockEditRejectedData): void {
  telemetryService.track("direct_stock_edit_rejected", data);
}

/**
 * Registrar variancia de costo detectada
 * Se dispara cuando el costo unitario de una orden varía más del umbral respecto al histórico
 */
export function trackKitCostVarianceDetected(data: KitCostVarianceData): void {
  telemetryService.track("kit_cost_variance_detected", data);
}

/**
 * Registrar validación fallida en formulario de orden
 * Se dispara cuando una regla valida rechaza una orden (antes de enviar a backend)
 */
export function trackOrderValidationFailed(data: OrderValidationFailedData): void {
  telemetryService.track("inventory_order_validation_failed", data);
}

/**
 * Registrar intento de login
 * Se dispara cuando el usuario envía el formulario de login
 */
export function trackLoginAttempted(source: "backoffice" | "website" | "tracker"): void {
  telemetryService.track("login_attempted", { source });
}

/**
 * Registrar login exitoso
 * Se dispara cuando backend verifica credenciales correctas
 */
export function trackLoginSucceeded(source: "backoffice" | "website" | "tracker", durationMs: number): void {
  telemetryService.track("login_succeeded", { source, duration_ms: durationMs });
}

/**
 * Registrar login fallido
 * Se dispara cuando credenciales son inválidas o error de transporte
 */
export function trackLoginFailed(reasonCode: "invalid_credentials" | "network_error" | "service_unavailable" | "invalid_response" | "unknown", layer: "frontend" | "backend", durationMs: number): void {
  telemetryService.track("login_failed", { reason_code: reasonCode, layer, duration_ms: durationMs });
}

/**
 * Registrar sesión expirada
 * Se dispara cuando backend verifica que el JWT expiró
 */
export function trackSessionExpired(): void {
  telemetryService.track("session_expired", { reason_code: "token_expired", source: "backend" });
}

/**
 * Registrar carga de datos completada
 * Se dispara cuando una sección termina de cargar (ready/empty) o falla
 */
export function trackDataLoadCompleted(
  section: string,
  outcome: "ready" | "empty" | "error",
  durationMs: number,
  reasonCode?: "network_error" | "invalid_response" | "unauthorized" | "service_unavailable" | "unknown",
): void {
  telemetryService.track("frontend_data_load_completed", {
    section,
    outcome,
    duration_ms: durationMs,
    ...(reasonCode && { reason_code: reasonCode }),
  });
}
