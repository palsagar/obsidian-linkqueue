"""LLM judgment via Pydantic AI: two structured calls per Link.

Call 1 (classify): note content + folder + tags + section, given the fetched
page and the Taxonomy. Call 2 (rewrite_index): full rewrite of the chosen
folder's Index Note (guarded by the caller, ADR 0004). New folders skip the
rewrite. The model only ever returns data — no tools, no file access.
"""

from pydantic import BaseModel, field_validator
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openrouter import OpenRouterProvider

from agent.vault import safe_filename


class Classification(BaseModel):
    note_title: str
    # the title becomes both the filename and the wikilink target — sanitize
    # once here so they can never diverge (Obsidian forbids \ / : etc.)

    @field_validator("note_title")
    @classmethod
    def _filename_safe(cls, v: str) -> str:
        return safe_filename(v)

    note_body: str
    tags: list[str]
    folder: str
    is_new_folder: bool = False
    folder_description: str = ""  # root Index Note entry text when is_new_folder
    section: str  # section heading inside the folder's Index Note
    root_section: str = ""  # root Index Note section when is_new_folder


CLASSIFY_INSTRUCTIONS = """\
You triage captured links into an Obsidian knowledge base.

Write one note for the link: a descriptive title and a faithful summary in
markdown. Depth follows the material — a real summary when readable text was
fetched; when only thin metadata is available (X posts, YouTube videos,
paywalled pages), write a brief note grounded ONLY in the URL and metadata.
Never invent content that was not fetched.

Choose the destination folder from the given taxonomy. Strongly prefer an
existing folder; propose a new one (is_new_folder=true, with a short
folder_description and a root_section from the root index) only when the
topic genuinely fits nowhere. Pick the section heading of the folder's index
the note belongs under (an existing section name when one fits). Tags:
a few lowercase topical tags, no '#'.
"""

REWRITE_INSTRUCTIONS = """\
You maintain the index note of one folder in an Obsidian knowledge base.
Return the complete rewritten index markdown: integrate the new note's
wikilink under the most fitting section, keeping the document coherent —
you may reorder and re-section, but every existing wikilink MUST be kept.
Return only the markdown, no commentary or code fences.
"""


def build_model(api_key: str, primary: str, fallback: str) -> Model:
    def openrouter(name: str) -> OpenAIChatModel:
        return OpenAIChatModel(name, provider=OpenRouterProvider(api_key=api_key))

    return FallbackModel(openrouter(primary), openrouter(fallback))


def classify(
    model: Model,
    url: str,
    note: str | None,
    page,  # fetch.Page
    taxonomy: list[str],
    root_index: str,
) -> Classification:
    agent = Agent(model, output_type=Classification, instructions=CLASSIFY_INSTRUCTIONS)
    prompt = (
        f"URL: {url}\n"
        f"User note: {note or '(none)'}\n"
        f"Page title: {page.title or '(none)'}\n"
        f"Page description: {page.description or '(none)'}\n\n"
        f"Taxonomy folders: {', '.join(taxonomy)}\n\n"
        f"Root index:\n{root_index}\n\n"
        f"Fetched text:\n{page.text or '(none — thin metadata only)'}"
    )
    return agent.run_sync(prompt).output


def rewrite_index(
    model: Model,
    folder: str,
    current_index: str,
    note_title: str,
) -> str:
    agent = Agent(model, output_type=str, instructions=REWRITE_INSTRUCTIONS)
    prompt = (
        f"Folder: {folder}\n"
        f"New note to integrate: [[{note_title}]]\n\n"
        f"Current index:\n{current_index}"
    )
    return agent.run_sync(prompt).output
