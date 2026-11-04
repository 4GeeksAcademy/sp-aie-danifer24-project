/**
 * Hooks de telemetría para Website
 */

"use client";

import { useEffect, ReactNode } from "react";
import { createErrorFingerprint, getTelemetryAppVersion } from "@packages/shared/telemetry-sanitization";
import { telemetryService } from "@packages/shared/telemetry-service";

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

import React from "react";
