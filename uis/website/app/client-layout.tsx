"use client";

import { ReactNode } from "react";
import { useTelemetryPageView, useGlobalErrorHandlers, TelemetryErrorBoundary } from "@/lib/telemetry-hooks";

export default function WebsiteClientLayout({ children }: { children: ReactNode }) {
  // Capturar page views cuando cambia la ruta
  useTelemetryPageView({
    "/": "home",
    "/candidatos": "candidates",
    "/talento": "candidates",
  });

  // Capturar errores globales no capturados
  useGlobalErrorHandlers();

  return (
    <TelemetryErrorBoundary section="website">
      {children}
    </TelemetryErrorBoundary>
  );
}
