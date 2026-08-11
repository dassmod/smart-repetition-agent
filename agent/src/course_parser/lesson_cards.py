"""
Lesson cards: turn a lesson's Retrieval prompts section into review cards.

The seed deck for the card-identity rework (see STRATA.md, "Engine rework").
Every lesson ends with five retrieval prompts written at authoring time, when
the material was fresh and its author knew what mattered. One prompt becomes
one card, so FSRS schedules a specific question instead of a whole lesson.

Card ids are content-addressed: the id is derived from the prompt's own text,
not from its position in the list. Reordering, inserting and deleting prompts
are therefore free, and rewording an existing prompt orphans that card's FSRS
history. That trade was chosen deliberately, and the matching editing rule for
the vault lives in 06 System/Maintenance/Audit Flags.md (2026-08-11).
"""

import hashlib
import re
from pathlib import Path

from agent.src.scheduler.review import make_lesson_id


# The exact H2 that opens the prompt section in every lesson. Compared with ==,
# so case and spacing are significant; a mismatch here yields zero cards silently.
PROMPT_HEADING = "## Retrieval prompts"

# A numbered list item: leading digits, a literal dot, whitespace, then the text.
# The capture group holds the prompt itself, without its "3. " marker.
PROMPT_ITEM = re.compile(r"\d+\.\s+(.*)")


# --- parsing: walk the file once, collecting only what sits under the heading ---

def extract_prompt_texts(lesson_text: str) -> list[str]:
    """
    Pull the numbered prompts out of one lesson's Retrieval prompts section.

    A line cannot tell you its own context: "3. What are the three checks..."
    looks identical under Retrieval prompts and under Sources used. Only the
    walk knows the difference, so `inside` carries that knowledge forward.

    Args:
        lesson_text: The full text of one lesson file.

    Returns:
        The prompts in document order. Empty when the lesson has no such
        section, which is a real answer rather than a failure.
    """
    prompts = []
    inside = False

    for line in lesson_text.split("\n"):
        # The heading opens the section but is not itself a prompt.
        if line.strip() == PROMPT_HEADING:
            inside = True
            continue

        # Everything before the heading, which is most of the file.
        if not inside:
            continue

        # The next H2 ends the section. Without this the walk would run to the
        # end of the file and collect the numbered lines in Sources used too.
        # The trailing space means an H3 inside the section does not stop us.
        if line.startswith("## "):
            break

        match = PROMPT_ITEM.match(line.strip())
        if match:
            prompts.append(match.group(1).strip())

    return prompts


# --- identity: name a card by what it says, not by where it sits ---

def make_card_id(source_path: Path, prompt_text: str) -> str:
    """
    Build a stable id for one card.

    Readable prefix from the lesson filename, identity from the prompt's text.
    The prefix is for humans reading review_state.json; the hash is what makes
    the card the same card tomorrow.

    Eight hex characters is 32 bits, which collides at roughly 65,000 cards.
    The deck is in the hundreds, so the truncation is comfortable.

    Args:
        source_path: Path of the lesson file the prompt came from.
        prompt_text: The prompt itself, exactly as written in the lesson.

    Returns:
        An id of the form "lesson-slug-a1b2c3d4".
    """
    # sha256 works on bytes, not characters, so the encoding is stated rather
    # than guessed. Same reason read_text() takes an encoding below.
    text_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()[:8]
    return f"{make_lesson_id(source_path.stem)}-{text_hash}"


# --- assembly: one lesson file in, its cards out ---

def extract_cards(path: Path) -> list[dict]:
    """
    Read one lesson file and return one card per retrieval prompt.

    No existence guard on purpose: a missing lesson should crash loudly rather
    than return a plausible nothing. A silent empty result is what let a missing
    file be recorded as a memory failure in cmd_review.

    Args:
        path: Path to a lesson markdown file.

    Returns:
        One dict per prompt, with id, prompt, source_path and heading.
        Empty when the lesson carries no Retrieval prompts section.
    """
    text = path.read_text(encoding="utf-8")
    prompts = extract_prompt_texts(text)

    cards = []
    for prompt in prompts:
        cards.append({
            "id": make_card_id(path, prompt),
            "prompt": prompt,
            # str(), not the Path itself: a Path is not JSON serializable, and
            # these dicts are headed for review_state.json.
            "source_path": str(path),
            # Constant today, because every card comes from the same section.
            # It earns its place when session and narration cards arrive and
            # a card has to say where inside its source it lives.
            "heading": PROMPT_HEADING,
        })

    return cards