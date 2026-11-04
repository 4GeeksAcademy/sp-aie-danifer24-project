/**
 * Hooks de telemetría para Website
 */

"use client";

import { useEffect, ReactNode } from "react";
import { usePathname } from "next/navigation";
import crypto from "crypto";
import { telemetryService } from "@packages/shared/telemetry-service";

export function useTelemetryPageView(sectionMap?: Record<string, string>) {
  const pathname = usePathname();
  const defaultMap: Record<string, string> = {
    "/": "home",
    "/candidatos": "candidates",
    "/talento": "candidates",
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

import React from "react";
