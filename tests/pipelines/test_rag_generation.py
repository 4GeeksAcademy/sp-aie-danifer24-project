from types import SimpleNamespace

import pytest
from qdrant_client import models

from data.pipelines.rag import (
    COLLECTION_NAME,
    DEFAULT_MIN_SCORE,
    generate_answer,
    query,
    retrieve,
)


class FakeQdrant:
    def __init__(self, points):
        self.points = points
        self.request = None

    def query_points(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(points=self.points)


class FakeLLM:
    def __init__(self, content="Respuesta generada"):
        self.content = content
        self.request = None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def test_retrieve_embeds_searches_filters_by_score_and_returns_payloads():
    qdrant_point = SimpleNamespace(
        payload={"text": "La tarifa estándar es 22%.", "company": "nexova"},
        score=0.81,
    )
    low_score = SimpleNamespace(
        payload={"text": "Texto irrelevante", "company": "nexova"},
        score=0.2,
    )
    client = FakeQdrant([qdrant_point, low_score])
    embedded_queries = []

    results = retrieve(
        "¿Cuál es la tarifa?",
        k=2,
        min_score=0.5,
        client=client,
        embedding_function=lambda text: embedded_queries.append(text) or [0.1, 0.2],
    )

    assert embedded_queries == ["¿Cuál es la tarifa?"]
    assert client.request["collection_name"] == COLLECTION_NAME
    assert client.request["limit"] == 2
    assert client.request["with_payload"] is True
    assert client.request["with_vectors"] is False
    assert client.request["query_filter"].must[0].key == "company"
    assert results == [{"text": "La tarifa estándar es 22%.", "company": "nexova"}]
    assert all(isinstance(item, dict) for item in results)


def test_retrieve_validates_query_k_and_min_score():
    with pytest.raises(ValueError):
        retrieve(" ", embedding_function=lambda _: [0.0], client=FakeQdrant([]))
    with pytest.raises(ValueError):
        retrieve("hola", k=0, embedding_function=lambda _: [0.0], client=FakeQdrant([]))
    with pytest.raises(ValueError):
        retrieve("hola", min_score=1.1, embedding_function=lambda _: [0.0], client=FakeQdrant([]))


def test_generate_answer_uses_grounded_sales_prompt_and_generation_model(monkeypatch):
    monkeypatch.setenv("GENERATION_MODEL", "academy-chat-model")
    llm = FakeLLM()
    context = [
        {
            "source_document": "pricing-model",
            "section": "Headhunting",
            "text": "Tarifa estándar: 22% del salario anual bruto.",
        }
    ]

    answer = generate_answer("¿Cuál es la tarifa?", context, client=llm)

    assert answer == "Respuesta generada"
    assert llm.request["model"] == "academy-chat-model"
    prompt = llm.request["messages"][0]["content"]
    user_message = llm.request["messages"][1]["content"]
    assert "SDRs y account managers" in prompt
    assert "nunca ofrezcas descuentos" in prompt
    assert "promedios, no como garantías" in prompt
    assert "22% del salario anual bruto" in user_message
    assert "pricing-model" in user_message


def test_generate_answer_handles_empty_context_without_external_fallback(monkeypatch):
    monkeypatch.setenv("GENERATION_MODEL", "academy-chat-model")
    llm = FakeLLM("No tengo información suficiente en la base de conocimiento.")

    answer = generate_answer("¿Qué descuento me darán?", [], client=llm)

    assert "información suficiente" in answer
    user_message = llm.request["messages"][1]["content"]
    assert "(Sin contexto relevante recuperado.)" in user_message
    assert "no completes con conocimiento externo" in user_message


def test_query_orchestrates_retrieve_then_generate(monkeypatch):
    calls = []
    context = [{"text": "fragmento recuperado"}]

    def fake_retrieve(question, *, k, min_score):
        calls.append(("retrieve", question, k, min_score))
        return context

    def fake_generate(question, retrieved_context):
        calls.append(("generate", question, retrieved_context))
        return "Respuesta final"

    monkeypatch.setattr("data.pipelines.rag.retrieve", fake_retrieve)
    monkeypatch.setattr("data.pipelines.rag.generate_answer", fake_generate)

    assert query("pregunta") == "Respuesta final"
    assert calls == [
        ("retrieve", "pregunta", 5, DEFAULT_MIN_SCORE),
        ("generate", "pregunta", context),
    ]
