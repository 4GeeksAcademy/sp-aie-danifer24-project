from services.api.schemas import AssetResponse
from services.api.services import knowledge_graph as knowledge_graph_module
from services.api.services.inventory_tool import (
    InventoryLookupInput,
    InventoryLookupOutput,
    InventoryToolOutcome,
)
from services.api.services.knowledge_graph import build_knowledge_graph


def test_graph_routes_inventory_question_to_live_lookup_and_uses_real_result(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_graph_module, "TRACE_DIR", tmp_path)
    calls = []
    product = AssetResponse(
        id=5,
        name="Laptop",
        sku="LAP-5",
        category="hardware",
        office="Valencia",
        current_stock=7,
    )

    def inventory_lookup(request):
        calls.append(request)
        return InventoryLookupOutput(outcome=InventoryToolOutcome.FOUND, products=[product])

    graph = build_knowledge_graph(
        lambda question: (_ for _ in ()).throw(AssertionError("RAG should not be used")),
        lambda question, context: (_ for _ in ()).throw(AssertionError("generation should not be used")),
        inventory_fn=inventory_lookup,
    )
    result = graph.invoke(
        {"question": "¿Cuánto stock hay del producto Laptop?", "run_id": "inventory-found"},
        config={"configurable": {"thread_id": "inventory-found"}},
    )
    assert result["answer"] == "Laptop (SKU LAP-5): 7 unidades disponibles."
    assert calls == [InventoryLookupInput(name="Laptop")]
    assert result["trace"] == [
        "receive_question", "route_request", "inventory_lookup", "inventory_response"
    ]


def test_graph_inventory_failure_uses_honest_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_graph_module, "TRACE_DIR", tmp_path)
    graph = build_knowledge_graph(
        lambda question: [],
        lambda question, context: "not used",
        inventory_fn=lambda request: InventoryLookupOutput(
            outcome=InventoryToolOutcome.ERROR,
            message="internal database detail",
        ),
    )
    result = graph.invoke(
        {"question": "Dime el stock del SKU: ABC-1", "run_id": "inventory-error"},
        config={"configurable": {"thread_id": "inventory-error"}},
    )
    assert result["answer"] == "No pude confirmar el stock del producto ahora mismo."
    assert "internal database detail" not in result["answer"]
    assert result["trace"][-2:] == ["inventory_lookup", "inventory_response"]


def test_graph_inventory_missing_product_does_not_claim_stock(tmp_path, monkeypatch):
    monkeypatch.setattr(knowledge_graph_module, "TRACE_DIR", tmp_path)
    graph = build_knowledge_graph(
        lambda question: [],
        lambda question, context: "not used",
        inventory_fn=lambda request: InventoryLookupOutput(outcome=InventoryToolOutcome.NOT_FOUND),
    )
    result = graph.invoke(
        {"question": "¿Qué stock tiene el producto 404?", "run_id": "inventory-missing"},
        config={"configurable": {"thread_id": "inventory-missing"}},
    )
    assert result["answer"] == "No encontré un producto que coincida con la consulta."
    assert "unidades" not in result["answer"]
