"use client";

import { FormEvent, useState } from "react";
import { BookOpenText, LoaderCircle, MessageCircleQuestion, Send } from "lucide-react";

type KnowledgeAnswer = { answer?: string; detail?: string };

export default function KnowledgePage() {
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function submitQuestion(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion || loading) return;

    setLoading(true);
    setAnswer("");
    setError("");

    try {
      const response = await fetch("/api/knowledge/query", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ question: normalizedQuestion }),
        cache: "no-store",
      });
      const payload: KnowledgeAnswer = await response.json().catch(() => ({}));

      if (!response.ok) {
        throw new Error(typeof payload.detail === "string" ? payload.detail : "No se pudo obtener una respuesta. Inténtalo de nuevo.");
      }
      if (typeof payload.answer !== "string" || !payload.answer.trim()) {
        throw new Error("El servicio respondió sin una respuesta válida. Inténtalo de nuevo.");
      }
      setAnswer(payload.answer);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "No se pudo conectar con el servicio. Comprueba tu conexión e inténtalo de nuevo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="shell knowledge-page">
      <section className="hero knowledge-hero">
        <p className="badge"><BookOpenText size={15} aria-hidden="true" /> Asistente comercial Nexova</p>
        <h1>Respuestas para tus conversaciones</h1>
        <p>Consulta servicios, tarifas y procesos. Las respuestas se basan en la base de conocimiento de Nexova.</p>
      </section>

      <section className="panel knowledge-panel" aria-labelledby="knowledge-heading">
        <div className="knowledge-panel-heading">
          <span className="knowledge-heading-icon"><MessageCircleQuestion size={20} aria-hidden="true" /></span>
          <div>
            <h2 id="knowledge-heading">¿Qué necesitas saber?</h2>
            <p>Escribe una pregunta concreta y te ayudaremos a preparar tu respuesta.</p>
          </div>
        </div>

        <form className="knowledge-form" onSubmit={submitQuestion}>
          <label htmlFor="knowledge-question">Tu pregunta</label>
          <textarea
            id="knowledge-question"
            name="question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Por ejemplo: ¿Cuál es la tarifa de headhunting y qué incluye?"
            maxLength={4000}
            rows={4}
            required
            disabled={loading}
          />
          <div className="knowledge-form-footer">
            <span>{question.length}/4000</span>
            <button className="knowledge-submit" type="submit" disabled={loading || !question.trim()}>
              {loading ? <><LoaderCircle size={17} className="knowledge-spinner" aria-hidden="true" /> Consultando…</> : <>Consultar <Send size={16} aria-hidden="true" /></>}
            </button>
          </div>
        </form>

        {loading && (
          <p className="knowledge-loading" role="status" aria-live="polite">
            <LoaderCircle size={17} className="knowledge-spinner" aria-hidden="true" /> Buscando información relevante…
          </p>
        )}
        {error && <div className="knowledge-error" role="alert"><strong>No se pudo completar la consulta.</strong><span>{error}</span></div>}
        {answer && (
          <section className="knowledge-answer" aria-labelledby="knowledge-answer-heading" aria-live="polite">
            <p className="knowledge-answer-label" id="knowledge-answer-heading">Respuesta</p>
            <p>{answer}</p>
          </section>
        )}
      </section>
      <p className="knowledge-disclaimer">La respuesta es una ayuda para preparar la conversación. Confirma cualquier condición comercial con la documentación vigente.</p>
    </main>
  );
}
