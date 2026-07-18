from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel

from agent.fetch import Page
from agent.judgment import Classification, classify, rewrite_index

CANNED = {
    "note_title": "Attention Is Overrated",
    "note_body": "A contrarian take.",
    "tags": ["attention"],
    "folder": "ML & Deep Learning",
    "is_new_folder": False,
    "folder_description": "",
    "section": "Architecture & Attention",
    "root_section": "",
}


def canned_classify_model(seen_prompts):
    def respond(messages, info):
        seen_prompts.append(str(messages))
        return ModelResponse(
            parts=[ToolCallPart(info.output_tools[0].name, CANNED)]
        )

    return FunctionModel(respond)


class TestClassify:
    def test_returns_classification_with_context_in_prompt(self):
        seen = []
        result = classify(
            canned_classify_model(seen),
            url="https://example.com/attn",
            note="from that thread",
            page=Page(title="Attention Is Overrated", description="hot take", text="body"),
            taxonomy=["ML & Deep Learning", "Investing"],
            root_index="# Vault Index",
        )
        assert isinstance(result, Classification)
        assert result.folder == "ML & Deep Learning"
        assert result.note_title == "Attention Is Overrated"
        prompt = seen[0]
        assert "https://example.com/attn" in prompt
        assert "Attention Is Overrated" in prompt
        assert "from that thread" in prompt
        assert "Investing" in prompt

    def test_note_title_is_sanitized_to_match_the_filename_it_becomes(self):
        dirty = dict(CANNED, note_title='Goodhart: "Overfitting" [2026] #1')

        def respond(messages, info):
            return ModelResponse(parts=[ToolCallPart(info.output_tools[0].name, dirty)])

        result = classify(
            FunctionModel(respond),
            url="https://example.com/x",
            note=None,
            page=Page(title="t", description=None, text=""),
            taxonomy=["ML & Deep Learning"],
            root_index="# Vault Index",
        )
        assert result.note_title == "Goodhart Overfitting 2026 1"


class TestRewriteIndex:
    def test_returns_rewritten_markdown_and_sends_current_index(self):
        seen = []

        def respond(messages, info):
            seen.append(str(messages))
            return ModelResponse(parts=[TextPart("# New Index\n- [[A]]\n- [[New Note]]\n")])

        result = rewrite_index(
            FunctionModel(respond),
            folder="ML & Deep Learning",
            current_index="# Old Index\n- [[A]]\n",
            note_title="New Note",
        )
        assert result == "# New Index\n- [[A]]\n- [[New Note]]\n"
        assert "# Old Index" in seen[0]
        assert "New Note" in seen[0]
