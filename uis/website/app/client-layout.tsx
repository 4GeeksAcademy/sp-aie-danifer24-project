"use client";

import { ReactNode } from "react";
import { useGlobalErrorHandlers, TelemetryErrorBoundary } from "@/lib/telemetry-hooks";

export default function WebsiteClientLayout({ children }: { children: ReactNode }) {
  // Capturar errores globales no capturados
  useGlobalErrorHandlers();

  return (
    <TelemetryErrorBoundary section="website">
      {children}
    </TelemetryErrorBoundary>
  );
}
