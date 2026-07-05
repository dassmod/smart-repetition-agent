"""Adaptive dialogue: ask, answer, diagnose - and if the answer is fuzzy, go down a level and ask again."""

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
from agent.src.ai.answer_assessor import AnswerAssessor
from agent.src.ai.prompt_builder import (
    build_question_prompt_for_level, build_assessment_prompt, get_consolidation_level
)
from agent.src.retrieval.store import load_or_build

INDEX_DIR = str(ROOT / "data" / "vault_index")
COURSES_JSON = str(ROOT / "data" / "courses.json")
REVIEW_STATE_JSON = str(ROOT / "data" / "review_state.json")

SOLID_SCORE_THRESHOLD = 3   # score >= this counts as "solid"; below it counts as "fuzzy"


# --- the tools: same real machines as ask_question.py, plus the real assessor ---
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


# --- state: the notebook now carries a whole dialogue, not one question ---
class State(TypedDict):
    lesson_id: str
    lesson_name: str
    content: str
    level: int                 # can go DOWN mid-dialogue - this is the rung
    question: dict
    answer: str
    assessment: dict
    transcript: list[dict]      # one entry per attempt: level, question, answer, score
    outcome: str


# --- nodes ---
def pick_lesson(state: State) -> dict:
    lesson_id, lesson_name, level = pick_due_item()
    return {"lesson_id": lesson_id, "lesson_name": lesson_name, "level": level}


def load_content(state: State) -> dict:
    return {"content": load_lesson_content(state["lesson_name"])}


def ask(state: State) -> dict:
    generator = QuestionGenerator()
    prompt = build_question_prompt_for_level(state["level"])
    question = generator.generate(state["lesson_name"], state["content"], system_prompt=prompt)
    return {"question": question}


def get_answer(state: State) -> dict:
    print(f"\n  [level {state['level']}/4] {state['question']['question']}")
    if state["question"].get("hint"):
        print(f"  hint: {state['question']['hint']}")
    answer = input("  your answer: ")
    return {"answer": answer}


def diagnose(state: State) -> dict:
    assessor = AnswerAssessor()
    prompt = build_assessment_prompt(state["level"])
    assessment = assessor.assess(
        state["question"]["question"], state["answer"], state["content"], system_prompt=prompt
    )

    entry = {
        "level": state["level"],
        "question": state["question"]["question"],
        "answer": state["answer"],
        "score": assessment.get("score"),
        "explanation": assessment.get("explanation"),
    }
    return {"assessment": assessment, "transcript": state["transcript"] + [entry]}


def downgrade(state: State) -> dict:
    return {"level": state["level"] - 1}


def record(state: State) -> dict:
    score = state["assessment"].get("score", 1)
    outcome = "solid" if score >= SOLID_SCORE_THRESHOLD else "bottomed_out"
    print(f"\n  --- {outcome} at level {state['level']}/4, score {score}/4 ---")
    return {"outcome": outcome}


# --- the heart: the one condition that decides where the line goes next ---
def route_after_diagnose(state: State) -> str:
    score = state["assessment"].get("score", 1)
    if score >= SOLID_SCORE_THRESHOLD:
        return "record"
    if state["level"] > 1:
        return "downgrade"      # fuzzy, and there is a rung below - go down it
    return "record"             # fuzzy, but already at the floor - nowhere lower to go


# --- wiring ---
builder = StateGraph(State)
builder.add_node("pick_lesson", pick_lesson)
builder.add_node("load_content", load_content)
builder.add_node("ask", ask)
builder.add_node("get_answer", get_answer)
builder.add_node("diagnose", diagnose)
builder.add_node("downgrade", downgrade)
builder.add_node("record", record)

builder.add_edge(START, "pick_lesson")
builder.add_edge("pick_lesson", "load_content")
builder.add_edge("load_content", "ask")
builder.add_edge("ask", "get_answer")
builder.add_edge("get_answer", "diagnose")
builder.add_conditional_edges("diagnose", route_after_diagnose, {
    "downgrade": "downgrade",
    "record": "record",
})
builder.add_edge("downgrade", "ask")     # the loop: back up to ask, now at a lower level
builder.add_edge("record", END)

graph = builder.compile()


if __name__ == "__main__":
    result = graph.invoke({
        "lesson_id": "", "lesson_name": "", "content": "", "level": 0,
        "question": {}, "assessment": {}, "transcript": [], "outcome": "",
    })
    print(f"\nLesson: {result['lesson_name']}")
    print(f"Attempts: {len(result['transcript'])}")
    for entry in result["transcript"]:
        print(f"  level {entry['level']}: score {entry['score']}/4")
