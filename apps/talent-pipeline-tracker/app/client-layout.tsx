"use client";

import { ReactNode } from "react";
import { useGlobalErrorHandlers, TelemetryErrorBoundary } from "@/lib/telemetry-hooks";

export default function TrackerClientLayout({ children }: { children: ReactNode }) {
  // Capturar errores globales no capturados
  useGlobalErrorHandlers();

  return (
    <TelemetryErrorBoundary section="candidates">
      {children}
    </TelemetryErrorBoundary>
  );
}
