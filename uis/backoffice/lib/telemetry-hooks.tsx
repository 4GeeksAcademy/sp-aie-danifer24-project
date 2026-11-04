/**
 * Hooks de telemetría para Backoffice
 * Capturan: page views, latencias API, errores no capturados, cargas de datos
 */

"use client";

import { useEffect, ReactNode, useCallback, useRef } from "react";
import { createErrorFingerprint, getTelemetryAppVersion } from "@packages/shared/telemetry-sanitization";
import { telemetryService } from "@packages/shared/telemetry-service";

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
        // No HTTP response exists, so this is not api_request_completed.
        throw error;
      }
    };
  }, []);
}

/**
 * Hook: Capturar cargas de datos en secciones
 */
export function useTelemetryDataLoad(section: string) {
  const startTimeRef = useRef<number | null>(null);

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
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error) {
    void this.trackError(error);
  }

  private async trackError(error: Error) {
    const [fingerprint, appVersion] = await Promise.all([createErrorFingerprint(error), getTelemetryAppVersion()]);
    if (!fingerprint || !appVersion) return;
    telemetryService.track("frontend_unhandled_error", {
      section: "unknown",
      source: "error_boundary",
      error_code: "render_error",
      fingerprint,
      app_version: appVersion,
    });
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
  const version = appVersion ?? getTelemetryAppVersion();

  useEffect(() => {
    if (typeof window === "undefined") return;

    const handleWindowError = async (event: ErrorEvent) => {
      const fingerprint = await createErrorFingerprint(event.error);
      if (!fingerprint || !version) return;
      telemetryService.track("frontend_unhandled_error", {
        section: "unknown",
        source: "window_error",
        error_code: event.error?.name === "ChunkLoadError" ? "chunk_load_error" : "unknown",
        fingerprint,
        app_version: version,
      });
    };

    const handleUnhandledRejection = async (event: PromiseRejectionEvent) => {
      const fingerprint = await createErrorFingerprint(event.reason);
      if (!fingerprint || !version) return;
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

import React from "react";
