from agent import vault

ROOT_INDEX = """# 🗂️ Vault Index

## Technical Knowledge
- [[ML & Deep Learning/_Index|ML & Deep Learning]] — Transformers
- [[AI Engineering/_Index|AI Engineering]] — LLM tooling

## Personal
- [[Investing/_Index|Investing]] — NRI options
"""

FOLDER_INDEX = """# AI Engineering

Intro prose.

## Agents
- [[Building Agents]]
- [[Tool Use Patterns|tools]]

## Inference
- [[Speculative Decoding]]
"""


class TestWikilinks:
    def test_extracts_targets_ignoring_aliases(self):
        text = "- [[Plain Link]]\n- [[Aliased/Note|shown text]]"
        assert vault.wikilink_targets(text) == {"Plain Link", "Aliased/Note"}

    def test_no_links_yields_empty_set(self):
        assert vault.wikilink_targets("no links here") == set()


class TestTaxonomy:
    def test_lists_folders_from_root_index(self):
        assert vault.taxonomy(ROOT_INDEX) == [
            "ML & Deep Learning",
            "AI Engineering",
            "Investing",
        ]


class TestGuardedRewrite:
    def test_accepts_rewrite_that_keeps_all_links(self):
        rewritten = FOLDER_INDEX.replace(
            "## Inference", "## Inference & Serving"
        ).replace(
            "- [[Speculative Decoding]]",
            "- [[Speculative Decoding]]\n- [[New Note]]",
        )
        assert (
            vault.guarded_rewrite(FOLDER_INDEX, rewritten, "- [[New Note]]", "Inference")
            == rewritten
        )

    def test_rejects_rewrite_that_drops_a_link_and_appends_instead(self):
        dropped = FOLDER_INDEX.replace("- [[Building Agents]]\n", "")
        result = vault.guarded_rewrite(FOLDER_INDEX, dropped, "- [[New Note]]", "Agents")
        assert "[[Building Agents]]" in result  # nothing lost
        assert "- [[New Note]]" in result  # entry still added
        lines = result.splitlines()
        agents_i = lines.index("## Agents")
        inference_i = lines.index("## Inference")
        assert "- [[New Note]]" in lines[agents_i:inference_i]

    def test_fallback_creates_missing_section_at_end(self):
        dropped = FOLDER_INDEX.replace("- [[Building Agents]]\n", "")
        result = vault.guarded_rewrite(FOLDER_INDEX, dropped, "- [[New Note]]", "Evals")
        assert result.rstrip().endswith("## Evals\n- [[New Note]]")


class TestSafeFilename:
    def test_strips_characters_obsidian_rejects(self):
        assert (
            vault.safe_filename('RAG: a "survey" [2026] #1 | notes?')
            == "RAG a survey 2026 1 notes"
        )


class TestWriteNote:
    def test_writes_frontmatter_and_body(self, tmp_path):
        (tmp_path / "AI Engineering").mkdir()
        path = vault.write_note(
            tmp_path,
            folder="AI Engineering",
            title="Building Agents Redux",
            body="Summary here.",
            source="https://example.com/a",
            captured="2026-07-17",
            triaged="2026-07-18",
            tags=["agents", "llm"],
        )
        assert path == "AI Engineering/Building Agents Redux.md"
        text = (tmp_path / path).read_text()
        assert text.startswith("---\n")
        assert 'source: "https://example.com/a"' in text
        assert "captured: 2026-07-17" in text
        assert "triaged: 2026-07-18" in text
        assert "  - agents" in text
        assert text.rstrip().endswith("Summary here.")

    def test_title_collision_gets_numeric_suffix(self, tmp_path):
        (tmp_path / "Investing").mkdir()
        (tmp_path / "Investing" / "REITs.md").write_text("existing")
        path = vault.write_note(
            tmp_path,
            folder="Investing",
            title="REITs",
            body="x",
            source="https://example.com/b",
            captured="2026-07-17",
            triaged="2026-07-18",
            tags=[],
        )
        assert path == "Investing/REITs 2.md"
