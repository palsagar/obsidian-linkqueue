import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from agent.queue_client import QueueClient
from agent.run import run_triage

ROOT_INDEX = """# Vault Index

## Technical Knowledge
- [[AI Engineering/_Index|AI Engineering]] — LLM tooling

## Personal
- [[Investing/_Index|Investing]] — money
"""

AI_INDEX = """# AI Engineering

## Agents
- [[Old Note]]
"""

ARTICLE_HTML = "<html><head><title>Attention Is Overrated</title></head><body><article><p>Real text.</p></article></body></html>"


@pytest.fixture()
def vault(tmp_path):
    (tmp_path / "_Index.md").write_text(ROOT_INDEX)
    (tmp_path / "AI Engineering").mkdir()
    (tmp_path / "AI Engineering" / "_Index.md").write_text(AI_INDEX)
    return tmp_path


@pytest.fixture()
def queue_http(tmp_path, monkeypatch):
    monkeypatch.setenv("QUEUE_DB", str(tmp_path / "queue.db"))
    monkeypatch.setenv("QUEUE_AUTH_MODE", "disabled")
    from app.main import create_app

    return TestClient(create_app())


@pytest.fixture()
def web():
    def handler(request):
        if request.url.path == "/good":
            return httpx.Response(200, text=ARTICLE_HTML)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def make_model(classification: dict, rewritten_index: str):
    def respond(messages, info):
        if info.output_tools:
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, classification)]
            )
        return ModelResponse(parts=[TextPart(rewritten_index)])

    return FunctionModel(respond)


class TestRunTriage:
    def test_end_to_end_done_and_failed(self, vault, queue_http, web):
        queue_http.post("/links", json={"url": "https://example.com/good"})
        queue_http.post("/links", json={"url": "https://example.com/dead"})
        model = make_model(
            {
                "note_title": "Attention Is Overrated",
                "note_body": "Summary.",
                "tags": ["attention"],
                "folder": "AI Engineering",
                "is_new_folder": False,
                "folder_description": "",
                "section": "Agents",
                "root_section": "",
            },
            "# AI Engineering\n\n## Agents\n- [[Old Note]]\n- [[Attention Is Overrated]]\n",
        )
        stats = run_triage(QueueClient(queue_http), web, vault, model, limit=10)

        assert stats == {"done": 1, "failed": 1}
        note = (vault / "AI Engineering" / "Attention Is Overrated.md").read_text()
        assert 'source: "https://example.com/good"' in note
        index = (vault / "AI Engineering" / "_Index.md").read_text()
        assert "[[Old Note]]" in index
        assert "[[Attention Is Overrated]]" in index
        links = {link["url"]: link for link in queue_http.get("/links").json()}
        good = links["https://example.com/good"]
        assert good["status"] == "done"
        assert good["note_path"] == "AI Engineering/Attention Is Overrated.md"
        dead = links["https://example.com/dead"]
        assert dead["status"] == "failed"
        assert dead["error"] == "HTTP 404"

    def test_lossy_index_rewrite_falls_back_to_append(self, vault, queue_http, web):
        queue_http.post("/links", json={"url": "https://example.com/good"})
        model = make_model(
            {
                "note_title": "Attention Is Overrated",
                "note_body": "Summary.",
                "tags": [],
                "folder": "AI Engineering",
                "is_new_folder": False,
                "folder_description": "",
                "section": "Agents",
                "root_section": "",
            },
            "# AI Engineering\n\n## Agents\n- [[Attention Is Overrated]]\n",  # drops Old Note
        )
        run_triage(QueueClient(queue_http), web, vault, model, limit=10)
        index = (vault / "AI Engineering" / "_Index.md").read_text()
        assert "[[Old Note]]" in index  # guard kept it
        assert "- [[Attention Is Overrated]]" in index

    def test_new_folder_is_created_and_added_to_root_index(self, vault, queue_http, web):
        queue_http.post("/links", json={"url": "https://example.com/good"})
        model = make_model(
            {
                "note_title": "Sourdough Basics",
                "note_body": "Bread.",
                "tags": ["cooking"],
                "folder": "Cooking",
                "is_new_folder": True,
                "folder_description": "Recipes and technique",
                "section": "Recipes",
                "root_section": "Personal",
            },
            "(rewrite should not be called for new folders)",
        )
        run_triage(QueueClient(queue_http), web, vault, model, limit=10)

        assert (vault / "Cooking" / "Sourdough Basics.md").exists()
        folder_index = (vault / "Cooking" / "_Index.md").read_text()
        assert folder_index.startswith("# Cooking")
        assert "- [[Sourdough Basics]]" in folder_index
        root = (vault / "_Index.md").read_text()
        lines = root.splitlines()
        personal_i = lines.index("## Personal")
        assert "- [[Cooking/_Index|Cooking]] — Recipes and technique" in lines[personal_i:]

    def test_traversal_folder_from_model_marks_link_failed(self, vault, queue_http, web):
        queue_http.post("/links", json={"url": "https://example.com/good"})
        model = make_model(
            {
                "note_title": "Evil",
                "note_body": "x",
                "tags": [],
                "folder": "../outside",
                "is_new_folder": True,
                "folder_description": "d",
                "section": "S",
                "root_section": "Personal",
            },
            "",
        )
        stats = run_triage(QueueClient(queue_http), web, vault, model, limit=10)
        assert stats == {"done": 0, "failed": 1}
        assert not (vault.parent / "outside").exists()
        link = queue_http.get("/links").json()[0]
        assert link["status"] == "failed"

    def test_progress_is_logged(self, vault, queue_http, web, caplog):
        import logging

        queue_http.post("/links", json={"url": "https://example.com/good"})
        queue_http.post("/links", json={"url": "https://example.com/dead"})
        model = make_model(
            {
                "note_title": "Attention Is Overrated",
                "note_body": "Summary.",
                "tags": [],
                "folder": "AI Engineering",
                "is_new_folder": False,
                "folder_description": "",
                "section": "Agents",
                "root_section": "",
            },
            "# AI Engineering\n\n## Agents\n- [[Old Note]]\n- [[Attention Is Overrated]]\n",
        )
        with caplog.at_level(logging.INFO):
            run_triage(QueueClient(queue_http), web, vault, model, limit=10)

        messages = [r.message for r in caplog.records]
        assert any("claimed 2 links" in m for m in messages)
        assert any("[1/2] https://example.com/good" in m for m in messages)
        assert any("done: AI Engineering/Attention Is Overrated.md" in m for m in messages)
        assert any("[2/2] https://example.com/dead" in m for m in messages)
        assert any("failed: HTTP 404" in m for m in messages)

    def test_model_failure_marks_link_failed(self, vault, queue_http, web):
        queue_http.post("/links", json={"url": "https://example.com/good"})

        def explode(messages, info):
            raise RuntimeError("provider down")

        stats = run_triage(
            QueueClient(queue_http), web, vault, FunctionModel(explode), limit=10
        )
        assert stats == {"done": 0, "failed": 1}
        link = queue_http.get("/links").json()[0]
        assert link["status"] == "failed"
        assert "provider down" in link["error"]
