"use client";

import { ReactNode } from "react";
import { useTelemetryPageView, useGlobalErrorHandlers, TelemetryErrorBoundary } from "@/lib/telemetry-hooks";

export default function BackofficeClientLayout({ children }: { children: ReactNode }) {
  // Capturar page views cuando cambia la ruta
  useTelemetryPageView();

  // Capturar errores globales no capturados
  useGlobalErrorHandlers();

  return (
    <TelemetryErrorBoundary section="backoffice">
      {children}
    </TelemetryErrorBoundary>
  );
}
