import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from agent.clippings import merge_frontmatter, split_note, triage_clippings

CLIPPING = """---
title: "(1) DAN KOE on X: \\"How to fix your entire life\\""
source: "https://x.com/thedankoe/status/123"
created: 2026-06-20
tags:
  - "clippings"
---
![Cover image](https://example.com/img.jpg)

If you're anything like me, you think resolutions are stupid.
"""

ROOT_INDEX = """# Vault Index

## Personal
- [[Personal Development/_Index|Personal Development]] — growth
"""

PD_INDEX = """# Personal Development

## Mindset
- [[Old Note]]
"""


class TestSplitNote:
    def test_splits_frontmatter_and_body(self):
        fm, body = split_note(CLIPPING)
        assert fm["source"] == "https://x.com/thedankoe/status/123"
        assert fm["tags"] == ["clippings"]
        assert body.startswith("![Cover image]")

    def test_no_frontmatter_yields_empty_dict(self):
        fm, body = split_note("just text")
        assert fm == {}
        assert body == "just text"


class TestMergeFrontmatter:
    def test_adds_triaged_and_merges_tags_keeping_original_keys(self):
        fm, body = split_note(CLIPPING)
        merged = merge_frontmatter(fm, triaged="2026-07-18", tags=["mindset", "clippings"])
        assert merged["triaged"] == "2026-07-18"
        assert merged["tags"] == ["clippings", "mindset"]  # deduped, original first
        assert merged["source"] == "https://x.com/thedankoe/status/123"


def make_model(classification, rewritten_index):
    def respond(messages, info):
        if info.output_tools:
            return ModelResponse(
                parts=[ToolCallPart(info.output_tools[0].name, classification)]
            )
        return ModelResponse(parts=[TextPart(rewritten_index)])

    return FunctionModel(respond)


@pytest.fixture()
def vault(tmp_path):
    (tmp_path / "_Index.md").write_text(ROOT_INDEX)
    (tmp_path / "Personal Development").mkdir()
    (tmp_path / "Personal Development" / "_Index.md").write_text(PD_INDEX)
    (tmp_path / "Clippings").mkdir()
    (tmp_path / "Clippings" / "DAN KOE on X.md").write_text(CLIPPING)
    return tmp_path


CLASSIFICATION = {
    "note_title": "How to Fix Your Entire Life — Dan Koe",
    "note_body": "(unused for clippings)",
    "tags": ["mindset", "habits"],
    "folder": "Personal Development",
    "is_new_folder": False,
    "folder_description": "",
    "section": "Mindset",
    "root_section": "",
}


class TestTriageClippings:
    def test_moves_renames_and_indexes_clipping(self, vault):
        model = make_model(
            CLASSIFICATION,
            "# Personal Development\n\n## Mindset\n- [[Old Note]]\n"
            "- [[How to Fix Your Entire Life — Dan Koe]]\n",
        )
        stats = triage_clippings(vault, model)
        assert stats == {"done": 1, "failed": 0}

        moved = vault / "Personal Development" / "How to Fix Your Entire Life — Dan Koe.md"
        assert moved.exists()
        assert not (vault / "Clippings" / "DAN KOE on X.md").exists()
        text = moved.read_text()
        assert "you think resolutions are stupid" in text  # content kept
        assert "source: https://x.com/thedankoe/status/123" in text
        assert "triaged: '2026-" in text or "triaged: 2026-" in text
        assert "- mindset" in text
        index = (vault / "Personal Development" / "_Index.md").read_text()
        assert "[[How to Fix Your Entire Life — Dan Koe]]" in index
        assert "[[Old Note]]" in index

    def test_model_failure_leaves_clipping_in_place(self, vault):
        def explode(messages, info):
            raise RuntimeError("provider down")

        stats = triage_clippings(vault, FunctionModel(explode))
        assert stats == {"done": 0, "failed": 1}
        assert (vault / "Clippings" / "DAN KOE on X.md").exists()

    def test_missing_clippings_folder_is_a_noop(self, tmp_path):
        (tmp_path / "_Index.md").write_text(ROOT_INDEX)
        model = make_model(CLASSIFICATION, "")
        assert triage_clippings(tmp_path, model) == {"done": 0, "failed": 0}

    def test_index_note_inside_clippings_is_ignored(self, vault):
        (vault / "Clippings" / "_Index.md").write_text("# Clippings")
        model = make_model(
            CLASSIFICATION,
            "# Personal Development\n\n## Mindset\n- [[Old Note]]\n"
            "- [[How to Fix Your Entire Life — Dan Koe]]\n",
        )
        stats = triage_clippings(vault, model)
        assert stats == {"done": 1, "failed": 0}
        assert (vault / "Clippings" / "_Index.md").exists()
