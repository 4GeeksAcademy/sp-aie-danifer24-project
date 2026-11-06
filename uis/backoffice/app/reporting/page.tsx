"use client";

import { useCallback, useEffect, useState } from "react";
import { getWeeklyKpiReport, type WeeklyKpiReport } from "@/lib/reporting";

const dateFormatter = new Intl.DateTimeFormat("es-ES", {
  day: "numeric",
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});

function weekRange(weekStart: string) {
  const start = new Date(`${weekStart}T00:00:00Z`);
  const end = new Date(start);
  end.setUTCDate(end.getUTCDate() + 6);
  return `${dateFormatter.format(start)} – ${dateFormatter.format(end)}`;
}

function formatCost(amount: number, currency: "EUR" | "USD") {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount);
}

function formatOffice(office: string) {
  return office === "valencia" ? "Valencia" : "Miami";
}

export default function ReportingPage() {
  const [report, setReport] = useState<WeeklyKpiReport | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  const loadReport = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setReport(await getWeeklyKpiReport());
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : "No se pudo cargar el reporte semanal.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const timer = window.setTimeout(() => { void loadReport(); }, 0);
    return () => window.clearTimeout(timer);
  }, [loadReport]);

  return (
    <main className="shell reporting-page">
      <section className="hero reporting-hero">
        <p className="badge">Resultados semanales · Valencia y Miami</p>
        <h1>Rendimiento de oficinas y programas</h1>
        <p>Indicadores de materiales, entregas y operación para el seguimiento del negocio.</p>
        {report && (
          <p className="reporting-period" aria-live="polite">
            <strong>Periodo del reporte:</strong> {weekRange(report.week_start)}
          </p>
        )}
      </section>

      <section className="panel reporting-panel" aria-labelledby="weekly-kpis-heading" aria-busy={loading}>
        <div className="reporting-section-heading">
          <div>
            <p className="eyebrow">RESUMEN DE NEGOCIO</p>
            <h2 id="weekly-kpis-heading">KPIs a medir</h2>
            <p>Resultados por oficina y programa. Los eventos reflejan el total registrado durante el periodo semanal.</p>
          </div>
          <button className="reporting-refresh" type="button" onClick={() => void loadReport()} disabled={loading}>
            {loading ? "Actualizando…" : "Actualizar datos"}
          </button>
        </div>

        {loading && !report && (
          <div className="reporting-state" role="status" aria-live="polite">
            <span className="reporting-spinner" aria-hidden="true" />
            <span>Cargando los resultados semanales…</span>
          </div>
        )}

        {!loading && error && (
          <div className="reporting-error" role="alert">
            <p>{error}</p>
            <button type="button" onClick={() => void loadReport()}>Reintentar</button>
          </div>
        )}

        {!loading && !error && report && report.entries.length === 0 && (
          <div className="reporting-state" role="status">
            No hay resultados disponibles para la semana del {dateFormatter.format(new Date(`${report.week_start}T00:00:00Z`))}.
          </div>
        )}

        {!error && report && report.entries.length > 0 && (
          <div className="reporting-table-wrap">
            <table className="reporting-table">
              <caption className="reporting-caption">
                Indicadores por oficina y programa · Semana del {weekRange(report.week_start)}
              </caption>
              <thead>
                <tr>
                  <th scope="col">Oficina</th>
                  <th scope="col">Programa</th>
                  <th scope="col">Costo de material por oficina/programa</th>
                  <th scope="col">Kits entregados</th>
                  <th scope="col">Frecuencia de escasez</th>
                  <th scope="col">Frecuencia de variación de costo</th>
                </tr>
              </thead>
              <tbody>
                {report.entries.map((entry) => (
                  <tr key={`${entry.office}-${entry.programme_id}`}>
                    <th scope="row">{formatOffice(entry.office)}</th>
                    <td>{entry.programme_id}</td>
                    <td className="reporting-number">{formatCost(entry.total_material_cost, entry.currency)}</td>
                    <td className="reporting-number">{entry.kits_delivered_count.toLocaleString("es-ES")}</td>
                    <td className="reporting-number">{entry.shortage_events_count.toLocaleString("es-ES")} <span>eventos</span></td>
                    <td className="reporting-number">{entry.cost_variance_events_count.toLocaleString("es-ES")} <span>eventos</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {loading && report && <p className="reporting-refresh-status" role="status">Actualizando los datos del reporte…</p>}
      </section>
      <p className="reporting-footnote">Frecuencia semanal · El coste se presenta en la moneda correspondiente a cada oficina.</p>
    </main>
  );
}
