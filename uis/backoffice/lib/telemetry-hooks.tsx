/**
 * Hooks de telemetría para Backoffice
 * Capturan: page views, latencias API, errores no capturados, cargas de datos
 */

"use client";

import { useEffect, ReactNode, useCallback } from "react";
import { usePathname } from "next/navigation";
import crypto from "crypto";
import { telemetryService } from "@packages/shared/telemetry-service";

/**
 * Hook: Capturar page views cuando accedes a secciones principales
 */
export function useTelemetryPageView(sectionMap?: Record<string, string>) {
  const pathname = usePathname();
  const defaultMap: Record<string, string> = {
    "/": "home",
    "/inventory/products": "inventory_products",
    "/inventory/orders/inbound": "inventory_inbound",
    "/inventory/orders/outbound": "inventory_outbound",
    "/inventory/orders": "inventory_orders",
    "/suppliers": "suppliers",
    "/incidents": "incidents",
    "/incidents/new": "incident_new",
    "/account/profile": "account_profile",
    "/account/change-password": "account_password",
    "/login": "login",
    "/register": "register",
    "/forgot-password": "password_recovery",
    "/reset-password": "password_reset",
  };

  const map = sectionMap ?? defaultMap;

  useEffect(() => {
    const section = map[pathname] ?? "unknown";
    const entryType = pathname === "/" ? "direct" : "internal_link";

    telemetryService.track("backoffice_section_viewed", {
      section,
      entry_type: entryType,
    });
  }, [pathname, map]);
}

/**
 * Hook: Capturar latencias de llamadas API
 */
export function useApiTelemetry() {
  return useCallback((routeTemplate: string, method: string = "GET") => {
    return async (url: string, options?: RequestInit): Promise<Response> => {
      const startTime = performance.now();
      try {
        const response = await fetch(url, options);
        const duration = Math.round(performance.now() - startTime);
        telemetryService.track("api_request_completed", {
          route_template: routeTemplate,
          method: method.toUpperCase(),
          status_code: response.status,
          duration_ms: duration,
        });
        return response;
      } catch (error) {
        const duration = Math.round(performance.now() - startTime);
        telemetryService.track("api_request_completed", {
          route_template: routeTemplate,
          method: method.toUpperCase(),
          status_code: 0,
          duration_ms: duration,
        });
        throw error;
      }
    };
  }, []);
}

/**
 * Hook: Capturar cargas de datos en secciones
 */
export function useTelemetryDataLoad(section: string) {
  const startTimeRef = { current: null as number | null };

  return {
    onLoadStart: () => {
      startTimeRef.current = performance.now();
    },
    onLoadEnd: (outcome: "ready" | "empty" | "error", reasonCode?: string) => {
      if (startTimeRef.current === null) return;
      const duration = Math.round(performance.now() - startTimeRef.current);
      telemetryService.track("frontend_data_load_completed", {
        section,
        outcome,
        duration_ms: duration,
        ...(reasonCode && { reason_code: reasonCode }),
      });
    },
  };
}

/**
 * Error Boundary: Capturar errores no capturados
 */
interface ErrorBoundaryProps {
  children: ReactNode;
  section?: string;
  fallback?: ReactNode;
}

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

export class TelemetryErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  private appVersion: string;

  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
    this.appVersion = process.env.NEXT_PUBLIC_BUILD_SHA?.slice(0, 7) ?? process.env.NEXT_PUBLIC_BUILD_ID?.slice(0, 7) ?? "unknown";
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    const section = this.props.section ?? "unknown";
    const fingerprint = this.createFingerprint(error);
    telemetryService.track("frontend_unhandled_error", {
      section,
      source: "error_boundary",
      error_code: "render_error",
      fingerprint,
      app_version: this.appVersion,
    });
  }

  private createFingerprint(error: Error): string {
    const sanitized = (error.stack ?? error.message ?? "unknown")
      .split("\n")
      .slice(0, 3)
      .map((line) => line.replace(/\d+/g, "N").replace(/\//g, "/").replace(/\\/g, "\\"))
      .join(" | ");
    const hash = crypto.createHash("sha256").update(sanitized).digest("hex");
    return hash;
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback ?? <div>Error al cargar esta sección. Por favor, recarga la página.</div>;
    }
    return this.props.children;
  }
}

/**
 * Hook: Capturar errores globales no capturados
 */
export function useGlobalErrorHandlers(appVersion?: string) {
  const version = appVersion ?? process.env.NEXT_PUBLIC_BUILD_SHA?.slice(0, 7) ?? "unknown";

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleWindowError = (event: ErrorEvent) => {
      const fingerprint = createErrorFingerprint(event.error?.stack ?? event.message ?? "unknown");
      telemetryService.track("frontend_unhandled_error", {
        section: "unknown",
        source: "window_error",
        error_code: event.error?.name === "ChunkLoadError" ? "chunk_load_error" : "unknown",
        fingerprint,
        app_version: version,
      });
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      const message = event.reason?.message ?? String(event.reason) ?? "unknown";
      const fingerprint = createErrorFingerprint(message);
      telemetryService.track("frontend_unhandled_error", {
        section: "unknown",
        source: "unhandled_rejection",
        error_code: "unhandled_rejection",
        fingerprint,
        app_version: version,
      });
    };

    window.addEventListener("error", handleWindowError);
    window.addEventListener("unhandledrejection", handleUnhandledRejection);

    return () => {
      window.removeEventListener("error", handleWindowError);
      window.removeEventListener("unhandledrejection", handleUnhandledRejection);
    };
  }, [version]);
}

function createErrorFingerprint(stackOrMessage: string): string {
  const sanitized = (stackOrMessage ?? "unknown")
    .split("\n")
    .slice(0, 3)
    .map((line) => line.replace(/\d+/g, "N").replace(/\//g, "/").replace(/\\/g, "\\"))
    .join(" | ");
  const hash = crypto.createHash("sha256").update(sanitized).digest("hex");
  return hash;
}

import React from "react";
