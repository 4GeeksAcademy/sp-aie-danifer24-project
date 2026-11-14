from pathlib import Path

from qdrant_client import models

from data.process.rag import (
    COLLECTION_NAME,
    DEFAULT_DOCUMENTS_DIR,
    MAX_CHUNK_CHARS,
    setup,
    prepare_document,
)


class FakeQdrant:
    def __init__(self, existing=False):
        self.existing = existing
        self.create_args = None
        self.deleted = None
        self.upserted = None

    def collection_exists(self, name):
        assert name == COLLECTION_NAME
        return self.existing

    def create_collection(self, **kwargs):
        self.create_args = kwargs

    def get_collection(self, name):
        assert name == COLLECTION_NAME
        return type(
            "Info",
            (),
            {
                "config": type(
                    "Config",
                    (),
                    {
                        "params": type(
                            "Params",
                            (),
                            {
                                "vectors": models.VectorParams(
                                    size=1536,
                                    distance=models.Distance.COSINE,
                                )
                            },
                        )()
                    },
                )()
            },
        )()

    def delete(self, **kwargs):
        self.deleted = kwargs

    def upsert(self, **kwargs):
        self.upserted = kwargs


def test_setup_reads_company_docs_and_indexes_at_least_three_chunks_each():
    client = FakeQdrant()
    result = setup(
        client=client,
        embedding_function=lambda text: [0.1, 0.2, 0.3],
    )

    assert Path(result["directory"]) == DEFAULT_DOCUMENTS_DIR
    assert result["collection"] == "nexova_knowledge"
    assert result["documents"] == 4
    points = client.upserted["points"]
    assert result["chunks"] == len(points)
    assert result["chunks"] >= 12
    assert client.create_args["vectors_config"].size == 3
    assert all(point.payload["company"] == "nexova" for point in points)
    assert all(point.payload["language"] == "es" for point in points)
    assert all(point.payload["text"] for point in points)
    sources = {point.payload["source_document"] for point in points}
    assert len(sources) == 4
    assert client.deleted["collection_name"] == COLLECTION_NAME


def test_setup_is_idempotent_with_deterministic_ids():
    fake_client = FakeQdrant()
    embed = lambda text: [0.1, 0.2, 0.3]
    first = setup(client=fake_client, embedding_function=embed)
    first_ids = [point.id for point in fake_client.upserted["points"]]
    second = setup(client=fake_client, embedding_function=embed)
    second_ids = [point.id for point in fake_client.upserted["points"]]

    assert first["chunks"] == second["chunks"]
    assert first_ids == second_ids
    assert fake_client.deleted["points_selector"].filter.must[0].key == "company"


def test_markdown_chunking_keeps_bullets_and_section_metadata(tmp_path):
    source = tmp_path / "example.md"
    source.write_text(
        "# Pricing\n\n- One complete rule.\n- Another complete rule.\n\n"
        "A paragraph with two sentences. This sentence stays intact.",
        encoding="utf-8",
    )

    chunks = prepare_document(source)

    assert len(chunks) == 3
    assert [chunk.section for chunk in chunks] == ["Pricing"] * 3
    assert chunks[0].text == "- One complete rule."
    assert chunks[1].text == "- Another complete rule."
    assert "This sentence stays intact." in chunks[2].text
    assert all(len(chunk.text) <= MAX_CHUNK_CHARS for chunk in chunks)


def test_oversized_single_sentence_is_not_silently_cut(tmp_path):
    source = tmp_path / "long.md"
    source.write_text("A" * 30, encoding="utf-8")

    try:
        prepare_document(source, max_chars=10)
    except ValueError as error:
        assert "no se dividirá por la mitad" in str(error)
    else:
        raise AssertionError("Oversized sentence should be rejected")
