"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  BRANCH_LABELS,
  CATEGORY_LABELS,
  INCIDENT_BRANCHES,
  INCIDENT_ORIGINS,
  INCIDENT_STATUSES,
  NEXT_STATUSES,
  ORIGIN_LABELS,
  STATUS_LABELS,
  getIncidentSummary,
  listIncidents,
  readableError,
  updateIncidentStatus,
  type Incident,
  type IncidentBranch,
  type IncidentOrigin,
  type IncidentStatus,
  type IncidentSummary,
} from "../../lib/incidents";

const EMPTY_FILTERS = { status: "", origin: "", branch: "" };

type Filters = typeof EMPTY_FILTERS;

export default function IncidentsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [loadState, setLoadState] = useState<{ loading: boolean; error: string; incidents: Incident[] }>({ loading: true, error: "", incidents: [] });
  const { loading, error } = loadState;
  const [summaryLoad, setSummaryLoad] = useState<{ state: "loading" | "ready" | "error"; summary: IncidentSummary | null }>({ state: "loading", summary: null });
  const { state: summaryState, summary: metrics } = summaryLoad;
  const [summaryRetry, setSummaryRetry] = useState(0);
  const [retry, setRetry] = useState(0);
  const [updating, setUpdating] = useState<Record<number, boolean>>({});
  const [notice, setNotice] = useState("");
  const [summaryRefresh, setSummaryRefresh] = useState(0);

  function setIncidents(update: Incident[] | ((current: Incident[]) => Incident[])) {
    setLoadState((current) => ({ ...current, incidents: typeof update === "function" ? update(current.incidents) : update }));
  }

  const loadIncidents = useCallback(async (signal: AbortSignal) => {
    try {
      const result = await listIncidents({
        status: filters.status as IncidentStatus || undefined,
        origin: filters.origin as IncidentOrigin || undefined,
        branch: filters.branch as IncidentBranch || undefined,
      });
      if (!signal.aborted) setLoadState({ loading: false, error: "", incidents: result });
    } catch (caught) {
      if (!signal.aborted) setLoadState((current) => ({ ...current, loading: false, error: readableError(caught) }));
    }
  }, [filters]);

  useEffect(() => {
    const controller = new AbortController();
    void loadIncidents(controller.signal);
    return () => controller.abort();
  }, [loadIncidents, retry]);

  useEffect(() => {
    const controller = new AbortController();
    void getIncidentSummary().then((result) => {
      if (!controller.signal.aborted) {
        setSummaryLoad({ summary: result, state: "ready" });
      }
    }).catch(() => {
      if (!controller.signal.aborted) setSummaryLoad((current) => ({ ...current, state: "error" }));
    });
    return () => controller.abort();
  }, [summaryRetry, summaryRefresh]);

  async function changeStatus(incident: Incident, next: IncidentStatus) {
    const previous = loadState.incidents;
    setNotice("");
    setIncidents((current) => current.flatMap((item) => {
      if (item.id !== incident.id) return [item];
      if (filters.status && next !== filters.status) return [];
      return [{ ...item, status: next }];
    }));
    setUpdating((current) => ({ ...current, [incident.id]: true }));
    try {
      const updated = await updateIncidentStatus(incident.id, next);
      setIncidents((current) => current.map((item) => item.id === updated.id ? updated : item));
      setNotice(`Estado actualizado: ${STATUS_LABELS[next]}.`);
      setSummaryRefresh((value) => value + 1);
    } catch (caught) {
      setIncidents(previous);
      setNotice(readableError(caught));
    } finally {
      setUpdating((current) => ({ ...current, [incident.id]: false }));
    }
  }

  const hasFilters = Object.values(filters).some(Boolean);
  const displayedIncidents = loadState.incidents;

  return (
    <main className="shell incidents-shell">
      <section className="hero incidents-hero">
        <div>
          <p className="badge">Nexova · Operaciones</p>
          <h1>Panel de incidencias</h1>
          <p>Consulta los reportes y mantén actualizado su seguimiento.</p>
        </div>
        <Link className="btn btn-dark" href="/incidents/new">Registrar incidencia</Link>
      </section>

      <SummaryPanel summary={metrics} state={summaryState} onRetry={() => { setSummaryLoad((current) => ({ ...current, state: "loading" })); setSummaryRetry((value) => value + 1); }} />

      <section className="incident-panel">
        <div className="panel-header incident-list-header">
          <div><p className="eyebrow">Seguimiento</p><h2>Incidencias registradas</h2></div>
          {loading && displayedIncidents.length > 0
            ? <span className="refresh-indicator" role="status"><span className="spinner" /> Actualizando…</span>
            : !error && <span className="count-pill">{displayedIncidents.length} {displayedIncidents.length === 1 ? "resultado" : "resultados"}</span>}
        </div>

        <div className="filters" aria-label="Filtros de incidencias">
          <label htmlFor="filter-status">Estado
            <select id="filter-status" value={filters.status} onChange={(event) => { setLoadState((current) => ({ ...current, loading: true, error: "" })); setFilters((current) => ({ ...current, status: event.target.value })); }}>
              <option value="">Todos</option>
              {INCIDENT_STATUSES.map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
            </select>
          </label>
          <label htmlFor="filter-origin">Origen
            <select id="filter-origin" value={filters.origin} onChange={(event) => { setLoadState((current) => ({ ...current, loading: true, error: "" })); setFilters((current) => ({ ...current, origin: event.target.value })); }}>
              <option value="">Todos</option>
              {INCIDENT_ORIGINS.map((origin) => <option key={origin} value={origin}>{ORIGIN_LABELS[origin]}</option>)}
            </select>
          </label>
          <label htmlFor="filter-branch">Sede
            <select id="filter-branch" value={filters.branch} onChange={(event) => { setLoadState((current) => ({ ...current, loading: true, error: "" })); setFilters((current) => ({ ...current, branch: event.target.value })); }}>
              <option value="">Todas</option>
              {INCIDENT_BRANCHES.map((branch) => <option key={branch} value={branch}>{BRANCH_LABELS[branch]}</option>)}
            </select>
          </label>
          {hasFilters && <button className="text-button" type="button" onClick={() => { setLoadState((current) => ({ ...current, loading: true, error: "" })); setFilters(EMPTY_FILTERS); }}>Limpiar filtros</button>}
        </div>

        {notice && <p className="notice notice-info" role="status">{notice}</p>}
        {loading && displayedIncidents.length === 0 && <div className="loading-state" role="status"><span className="spinner" /> Cargando incidencias…</div>}
        {!loading && error && displayedIncidents.length === 0 && <div className="empty-state error-state" role="alert"><span className="state-icon">!</span><h3>No se pudieron cargar las incidencias</h3><p>{error}</p><button className="btn btn-dark" type="button" onClick={() => { setLoadState((current) => ({ ...current, loading: true, error: "" })); setRetry((value) => value + 1); }}>Reintentar</button></div>}
        {!loading && error && displayedIncidents.length > 0 && <p className="notice notice-error" role="alert">No se pudieron actualizar los resultados: {error} <button className="text-button" type="button" onClick={() => { setLoadState((current) => ({ ...current, loading: true, error: "" })); setRetry((value) => value + 1); }}>Reintentar</button></p>}
        {!loading && !error && displayedIncidents.length === 0 && <div className="empty-state"><span className="state-icon">✓</span><h3>{hasFilters ? "No hay resultados con estos filtros" : "Aún no hay incidencias"}</h3><p>{hasFilters ? "Prueba con otros criterios o limpia los filtros." : "Cuando registres una incidencia aparecerá aquí."}</p>{hasFilters && <button className="btn btn-outline" type="button" onClick={() => { setLoadState((current) => ({ ...current, loading: true, error: "" })); setFilters(EMPTY_FILTERS); }}>Limpiar filtros</button>}</div>}
        {displayedIncidents.length > 0 && (
          <div className="incident-list">
            {displayedIncidents.map((incident) => <article className="incident-card" key={incident.id}>
              <div className="incident-card-main">
                <div className="incident-card-title"><h3>{incident.title}</h3><span className={`status-badge status-${incident.status}`}>{STATUS_LABELS[incident.status]}</span></div>
                <p className="incident-description">{incident.description}</p>
                <div className="incident-meta"><span>{CATEGORY_LABELS[incident.category]}</span><span>{ORIGIN_LABELS[incident.origin]}</span><span>{BRANCH_LABELS[incident.branch]}</span><time dateTime={incident.created_at}>{new Intl.DateTimeFormat("es-ES", { dateStyle: "medium" }).format(new Date(incident.created_at))}</time></div>
              </div>
              <label className="status-control" htmlFor={`status-${incident.id}`}>Cambiar estado
                <select id={`status-${incident.id}`} value={incident.status} disabled={Boolean(updating[incident.id]) || NEXT_STATUSES[incident.status].length === 0} onChange={(event) => void changeStatus(incident, event.target.value as IncidentStatus)}>
                  <option value={incident.status}>{STATUS_LABELS[incident.status]}</option>
                  {NEXT_STATUSES[incident.status].map((status) => <option key={status} value={status}>{STATUS_LABELS[status]}</option>)}
                </select>
                {updating[incident.id] && <span className="field-hint">Actualizando…</span>}
              </label>
            </article>)}
          </div>
        )}
      </section>
    </main>
  );
}

function SummaryPanel({ summary, state, onRetry }: { summary: IncidentSummary | null; state: "loading" | "ready" | "error"; onRetry: () => void }) {
  return (
    <section className="summary-panel" aria-labelledby="summary-title">
      <div className="summary-heading"><div><p className="eyebrow">Vista general</p><h2 id="summary-title">Resumen operativo</h2></div>{summary && state === "ready" && <strong className="summary-total">{summary.total}<span>total</span></strong>}</div>
      {state === "loading" && <p className="summary-state" role="status"><span className="spinner" /> Cargando métricas…</p>}
      {state === "error" && <div className="summary-state summary-error" role="alert"><span>No se pudieron cargar las métricas.</span><button className="text-button" type="button" onClick={onRetry}>Reintentar</button></div>}
      {state === "ready" && summary && <div className="metrics-grid">
        <MetricGroup title="Por estado" values={summary.by_status} labels={STATUS_LABELS} />
        <MetricGroup title="Por categoría" values={summary.by_category} labels={CATEGORY_LABELS} />
        <MetricGroup title="Por origen" values={summary.by_origin} labels={ORIGIN_LABELS} />
        <MetricGroup title="Por sede" values={summary.by_branch} labels={BRANCH_LABELS} />
      </div>}
    </section>
  );
}

function MetricGroup({ title, values, labels }: { title: string; values: Record<string, number>; labels: Record<string, string> }) {
  return <article className="metric-group"><h3>{title}</h3><dl>{Object.entries(values).map(([key, count]) => <div key={key}><dt>{labels[key] ?? key}</dt><dd>{count}</dd></div>)}</dl></article>;
}
