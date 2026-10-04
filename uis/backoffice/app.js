const form = document.querySelector("#upload-form");
const fileInput = document.querySelector("#csv-file");
const dropzone = document.querySelector("#dropzone");
const fileLabel = document.querySelector("#file-label");
const analyzeButton = document.querySelector("#analyze-button");
const downloadButton = document.querySelector("#download-button");
const notice = document.querySelector("#notice");
const results = document.querySelector("#results");

const invalidLabels = {
  missing_ticket_id: "Falta ticket_id",
  invalid_ticket_id: "ticket_id inválido",
  duplicate_ticket_id: "ticket_id duplicado",
  missing_date: "Falta la fecha",
  invalid_date: "Fecha inválida",
  missing_client_company: "Falta client_company",
  invalid_category: "Categoría inválida o faltante",
  invalid_description: "Descripción inválida o faltante",
  invalid_agent_id: "agent_id inválido o faltante",
  invalid_status: "Estado inválido o faltante",
  invalid_email: "Email inválido o faltante",
  closed_without_score: "Ticket cerrado sin puntuación",
  score_out_of_range: "Puntuación fuera del rango 1-5",
  malformed_csv_row: "Fila CSV mal formada",
};
const scoreLabels = {
  1: "Muy insatisfecho",
  2: "Insatisfecho",
  3: "Neutral",
  4: "Satisfecho",
  5: "Muy satisfecho",
};
const categoryOrder = ["TECHNICAL", "BILLING", "ACCESS", "HR_QUERY", "COMPLAINT"];
const statusOrder = ["OPEN", "CLOSED", "DISCARDED"];
const statusLabels = {
  OPEN: "Abierto",
  CLOSED: "Cerrado",
  DISCARDED: "Descartado",
};

function showNotice(message, isSuccess = false) {
  notice.textContent = message;
  notice.classList.toggle("is-success", isSuccess);
  notice.hidden = false;
}

function setSelectedFile(file) {
  if (!file) return;
  const isCsv = file.name.toLowerCase().endsWith(".csv") || file.type === "text/csv";
  if (!isCsv) {
    fileInput.value = "";
    fileLabel.textContent = "Arrastra el CSV aquí";
    analyzeButton.disabled = true;
    showNotice("El archivo debe tener formato CSV.");
    return;
  }
  fileLabel.textContent = file.name;
  analyzeButton.disabled = false;
  notice.hidden = true;
}

fileInput.addEventListener("change", () => setSelectedFile(fileInput.files[0]));

for (const eventName of ["dragenter", "dragover"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.add("is-dragging");
  });
}

for (const eventName of ["dragleave", "drop"]) {
  dropzone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropzone.classList.remove("is-dragging");
  });
}

dropzone.addEventListener("drop", (event) => {
  const [file] = event.dataTransfer.files;
  if (!file) return;
  const transfer = new DataTransfer();
  transfer.items.add(file);
  fileInput.files = transfer.files;
  setSelectedFile(file);
});

function appendDistribution(container, entries, total, labelFor, showPercent = true) {
  container.replaceChildren();
  for (const [key, item] of entries) {
    const row = document.createElement("div");
    row.className = "distribution-row";

    const label = document.createElement("span");
    label.className = "distribution-label";
    label.textContent = labelFor(key);

    const track = document.createElement("div");
    track.className = "distribution-track";
    track.setAttribute("aria-hidden", "true");
    const fill = document.createElement("div");
    fill.className = "distribution-fill";
    fill.style.width = `${Math.min(100, item.percentage)}%`;
    track.append(fill);

    const value = document.createElement("span");
    value.className = "distribution-value";
    value.textContent = showPercent
      ? `${item.count} · ${item.percentage.toFixed(1)}%`
      : String(item.count);

    row.append(label, track, value);
    container.append(row);
  }
}

function renderInvalidBreakdown(breakdown, invalidCount) {
  const panel = document.querySelector("#invalid-panel");
  const list = document.querySelector("#invalid-list");
  list.replaceChildren();
  const issues = Object.entries(breakdown).filter(([, count]) => count > 0);
  panel.hidden = invalidCount === 0;
  document.querySelector("#invalid-total").textContent = `${invalidCount} registros`;
  for (const [rule, count] of issues) {
    const item = document.createElement("div");
    item.className = "invalid-item";
    const label = document.createElement("span");
    label.textContent = invalidLabels[rule] || "Otra regla de validación";
    const value = document.createElement("strong");
    value.textContent = String(count);
    item.append(label, value);
    list.append(item);
  }
}

function renderScores(satisfaction) {
  const scoreList = document.querySelector("#score-list");
  scoreList.replaceChildren();
  document.querySelector("#average-score").textContent = satisfaction.average.toFixed(2);
  document.querySelector("#scored-count").textContent =
    `${satisfaction.scored_tickets} de ${satisfaction.closed_tickets} tickets puntuados`;
  for (const score of [1, 2, 3, 4, 5]) {
    const count = satisfaction.scores[String(score)] || 0;
    const row = document.createElement("div");
    row.className = "score-row";
    const label = document.createElement("span");
    label.textContent = `${score} · ${scoreLabels[score]}`;
    const track = document.createElement("div");
    track.className = "score-track";
    track.setAttribute("aria-hidden", "true");
    const fill = document.createElement("div");
    fill.className = "score-fill";
    const denominator = satisfaction.scored_tickets || 1;
    fill.style.width = `${Math.min(100, (count / denominator) * 100)}%`;
    track.append(fill);
    const value = document.createElement("span");
    value.className = "score-value";
    value.textContent = String(count);
    row.append(label, track, value);
    scoreList.append(row);
  }
}

function renderResults(report) {
  document.querySelector("#report-title").textContent = report.source_filename;
  document.querySelector("#report-count").textContent =
    `${report.total_records} registros · informe más reciente`;
  document.querySelector("#total-count").textContent = String(report.total_records);
  document.querySelector("#valid-count").textContent = String(report.valid_records);
  document.querySelector("#invalid-count").textContent = String(report.invalid_records);
  document.querySelector("#invalid-note").textContent = report.invalid_records
    ? "Requieren revisión"
    : "Sin registros que revisar";

  renderInvalidBreakdown(report.invalid_breakdown, report.invalid_records);
  appendDistribution(
    document.querySelector("#category-list"),
    categoryOrder.map((category) => [category, report.categories[category]]),
    report.valid_records,
    (category) => category,
  );
  appendDistribution(
    document.querySelector("#status-list"),
    statusOrder.map((status) => [status, report.statuses[status]]),
    report.valid_records,
    (status) => statusLabels[status],
  );
  renderScores(report.satisfaction);
  results.hidden = false;
  downloadButton.disabled = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const file = fileInput.files[0];
  if (!file) return;

  analyzeButton.disabled = true;
  analyzeButton.textContent = "Analizando…";
  notice.hidden = true;
  const body = new FormData();
  body.append("file", file);

  try {
    const response = await fetch("/api/incidents/analyze", { method: "POST", body });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "No se pudo analizar el archivo.");
    renderResults(payload);
    showNotice("Análisis completado correctamente.", true);
  } catch (error) {
    showNotice(error.message || "No se pudo conectar con el servicio de análisis.");
  } finally {
    analyzeButton.textContent = "Analizar archivo";
    analyzeButton.disabled = !fileInput.files.length;
  }
});

downloadButton.addEventListener("click", async () => {
  downloadButton.disabled = true;
  try {
    const response = await fetch("/api/incidents/results/report");
    if (!response.ok) {
      const payload = await response.json();
      throw new Error(payload.detail || "No hay un informe disponible.");
    }
    const blob = await response.blob();
    const objectUrl = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = objectUrl;
    link.download = "results.csv";
    link.click();
    URL.revokeObjectURL(objectUrl);
  } catch (error) {
    showNotice(error.message || "No se pudo descargar el informe.");
  } finally {
    downloadButton.disabled = false;
  }
});