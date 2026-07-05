"""Ask node: pick a due lesson, pull its real content, generate one real question."""

import sys
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

# --- plumbing: let this file find your existing code under agent/src ---
ROOT = Path(__file__).resolve().parents[2]          # the obsidian-knowledge-agent folder
sys.path.insert(0, str(ROOT))
from agent.src.course_parser.models import load_courses_from_json
from agent.src.scheduler.review import SchedulerManager, load_review_state
from agent.src.ai.question_generator import QuestionGenerator
from agent.src.ai.prompt_builder import build_question_prompt_for_level, get_consolidation_level
from agent.src.retrieval.store import load_or_build

INDEX_DIR = str(ROOT / "data" / "vault_index")
COURSES_JSON = str(ROOT / "data" / "courses.json")
REVIEW_STATE_JSON = str(ROOT / "data" / "review_state.json")


# --- the tools: real FSRS scheduling, real vault content, real Claude ---
def pick_due_item():
    """Grab one real due lesson (deterministic: lowest lesson_id) and its FSRS-derived level."""
    courses = load_courses_from_json(COURSES_JSON)
    manager = SchedulerManager()
    load_review_state(manager, REVIEW_STATE_JSON)
    manager.create_items_from_courses(courses)

    due = sorted(manager.get_due_items(), key=lambda item: item.lesson_id)
    item = due[0]
    return item.lesson_id, item.lesson_name, get_consolidation_level(item)


def load_lesson_content(lesson_name: str) -> str:
    index = load_or_build(INDEX_DIR, COURSES_JSON)
    return index.get_lesson_content(lesson_name)


def generate_question(lesson_name: str, content: str, level: int) -> dict:
    generator = QuestionGenerator()
    prompt = build_question_prompt_for_level(level)
    return generator.generate(lesson_name, content, system_prompt=prompt)


# --- state: the notebook carries the chosen lesson through to a question ---
class State(TypedDict):
    lesson_id: str
    lesson_name: str
    level: int
    content: str
    question: dict


# --- nodes: each one does exactly one step of the pipeline ---
def pick_lesson(state: State) -> dict:
    lesson_id, lesson_name, level = pick_due_item()
    return {"lesson_id": lesson_id, "lesson_name": lesson_name, "level": level}


def load_content(state: State) -> dict:
    return {"content": load_lesson_content(state["lesson_name"])}


def ask(state: State) -> dict:
    question = generate_question(state["lesson_name"], state["content"], state["level"])
    return {"question": question}


# --- wiring: START -> pick_lesson -> load_content -> ask -> END ---
builder = StateGraph(State)
builder.add_node("pick_lesson", pick_lesson)
builder.add_node("load_content", load_content)
builder.add_node("ask", ask)
builder.add_edge(START, "pick_lesson")
builder.add_edge("pick_lesson", "load_content")
builder.add_edge("load_content", "ask")
builder.add_edge("ask", END)
graph = builder.compile()


if __name__ == "__main__":
    result = graph.invoke({
        "lesson_id": "", "lesson_name": "", "level": 0, "content": "", "question": {},
    })
    print(f"Lesson:   {result['lesson_name']}  (level {result['level']}/4)")
    print(f"Question: {result['question']['question']}")
    print(f"Hint:     {result['question']['hint']}")
