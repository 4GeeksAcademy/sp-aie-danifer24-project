"use client";

import { ReactNode } from "react";
import { useTelemetryPageView, useGlobalErrorHandlers, TelemetryErrorBoundary } from "@/lib/telemetry-hooks";

export default function TrackerClientLayout({ children }: { children: ReactNode }) {
  // Capturar page views cuando cambia la ruta en Tracker
  useTelemetryPageView({
    "/": "home",
    "/candidates": "candidates",
  });

  // Capturar errores globales no capturados
  useGlobalErrorHandlers();

  return (
    <TelemetryErrorBoundary section="candidates">
      {children}
    </TelemetryErrorBoundary>
  );
}
