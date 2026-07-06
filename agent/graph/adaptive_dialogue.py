"""Adaptive dialogue: ask, answer, diagnose - and if the answer is fuzzy, go down a level and ask again."""

import os
import re
import sys
from pathlib import Path
from typing import TypedDict

import anthropic

from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt, Command
from langgraph.checkpoint.memory import InMemorySaver

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

# --- recognizing "I don't know" and "I'm ready to move on", in plain language ---
DONT_KNOW_PHRASES = (
    "i don't know", "i dont know", "idk", "no idea", "not sure",
    "no clue", "i have no idea", "not really sure", "teach me",
)
READY_TO_CONTINUE_PHRASES = (
    "ok", "okay", "got it", "understood", "understand now", "makes sense",
    "clear now", "i get it", "i understand", "thanks", "thank you",
    "let's continue", "lets continue", "continue", "next", "proceed",
    "ready", "good", "im good", "i'm good", "move on", "yes",
)

EXPLAIN_SYSTEM_PROMPT = """You are tutoring using these exact learning principles, not generic teaching advice:
foundation before altitude (never skip the groundwork a concept rests on), connected stories over isolated
facts, analogy-first using physical or tangible metaphors, full depth in simple language (not less deep, just
more simple), stay on this one point until it is genuinely solid before moving on, invite deep "why" questions
rather than just stating facts, and narrate ideas back in a way the learner could repeat themselves.

The learner said they don't know the answer to this question, from the lesson "{lesson_name}":

Question: {question}

Here is the lesson's real content, to ground your explanation in - do not invent facts beyond it:
{content}

Explain the concept behind this question properly, from the ground up if needed. This is a conversation, not a
monologue: don't try to cover everything in one message, leave room for them to ask a follow-up or say what's
still unclear. Keep going for as long as they need. When they eventually say something that signals they're
ready to move on, that's your cue this explanation is done - but until then, keep teaching."""


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
    explain_history: list[dict]  # the teaching back-and-forth, when the learner says they don't know
    wants_explanation: bool


def _looks_like_dont_know(answer: str) -> bool:
    """Fast, free pre-check for the obvious cases ('idk') - not the full decision."""
    normalized = answer.strip().lower()
    return any(phrase in normalized for phrase in DONT_KNOW_PHRASES)


STILL_ASKING_WORDS = ("?", "why", "what", "how", "explain", "mean", "again")


def ready_to_continue(reply: str) -> bool:
    """Heuristic: is the learner signaling they're ready to move on from the explanation?"""
    normalized = reply.strip().lower()
    if any(w in normalized for w in STILL_ASKING_WORDS):
        return False  # still probing the concept, not ready yet, regardless of stray words like "ok"
    return any(re.search(rf"\b{re.escape(phrase)}\b", normalized) for phrase in READY_TO_CONTINUE_PHRASES)


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
    """
    Pause the graph and wait for a real answer from whichever interface is
    driving it (CLI or Telegram). interrupt() hands the question out to the
    caller and, on resume, returns exactly what the caller passed to
    Command(resume=...) - this is what lets the same graph survive a
    real-world gap (a human typing in Telegram, maybe hours later) instead
    of blocking Python's own input().
    """
    answer = interrupt({
        "kind": "question",
        "level": state["level"],
        "question": state["question"]["question"],
        "hint": state["question"].get("hint", ""),
    })
    return {"answer": answer}


def classify_answer(state: State) -> dict:
    """
    Decide whether this looks like a genuine attempt, or a request to be
    taught. The fast phrase check catches obvious cases ("idk") for free;
    anything else gets a real classification, since natural phrasing and
    typos ("not so sure about it, expalin to me") slip straight past a fixed
    keyword list - that's not a hypothetical, it's what a real answer did.
    """
    answer = state["answer"]
    if _looks_like_dont_know(answer):
        return {"wants_explanation": True}

    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=8,
        system=(
            "Reply with exactly one word: YES if the learner's message means they don't know "
            "the answer and want it explained (however it's phrased, including typos or "
            "indirect wording), or NO if it's a genuine attempt at answering the question, "
            "even a wrong one."
        ),
        messages=[{
            "role": "user",
            "content": f"Question: {state['question']['question']}\n\nLearner's message: {answer}",
        }],
    )
    text = next(block.text for block in response.content if block.type == "text")
    return {"wants_explanation": "yes" in text.strip().lower()}


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


def explain(state: State) -> dict:
    """
    Teach the concept properly instead of grading a guess. Uses a plain
    multi-turn chat completion (not QuestionGenerator/AnswerAssessor - those
    are locked to a fixed JSON quiz-question or scoring format), carrying the
    whole back-and-forth in explain_history so each turn is grounded in what
    was already said.
    """
    client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
    system_prompt = EXPLAIN_SYSTEM_PROMPT.format(
        lesson_name=state["lesson_name"],
        question=state["question"]["question"],
        content=state["content"],
    )

    history = state.get("explain_history") or [{"role": "user", "content": state["answer"]}]

    response = client.messages.create(
        model="claude-sonnet-5",
        max_tokens=1024,
        system=system_prompt,
        messages=history,
    )
    # content[0] isn't always the text block - this model can return a
    # ThinkingBlock first, which has no .text attribute at all
    explanation_text = next(block.text for block in response.content if block.type == "text")

    return {"explain_history": history + [{"role": "assistant", "content": explanation_text}]}


def get_learner_reply(state: State) -> dict:
    """Pause and wait for the learner's reply to the explanation - a follow-up, or 'ready to continue'."""
    reply = interrupt({
        "kind": "explanation",
        "text": state["explain_history"][-1]["content"],
    })
    return {"explain_history": state["explain_history"] + [{"role": "user", "content": reply}]}


def finish_explaining(state: State) -> dict:
    """
    The learner is ready to move on. This attempt is recorded as score 1
    (Again), on purpose: not attempting is not the same as attempting and
    landing fuzzy, but the FSRS signal should still be honest that they
    didn't know it at this level, matching rate_dialogue's first-attempt
    policy exactly - no separate retry-at-an-easier-level here, since there
    was nothing ambiguous to retry.
    """
    entry = {
        "level": state["level"],
        "question": state["question"]["question"],
        "answer": state["answer"],
        "score": 1,
        "explanation": "learner asked for an explanation instead of attempting an answer",
    }
    return {"assessment": {"score": 1}, "transcript": state["transcript"] + [entry]}


def downgrade(state: State) -> dict:
    return {"level": state["level"] - 1}


def record(state: State) -> dict:
    score = state["assessment"].get("score", 1)
    outcome = "solid" if score >= SOLID_SCORE_THRESHOLD else "bottomed_out"
    print(f"\n  --- {outcome} at level {state['level']}/4, score {score}/4 ---")
    return {"outcome": outcome}


# --- a second decision: did they actually attempt it, or ask to be taught? ---
def route_after_answer(state: State) -> str:
    return "explain" if state["wants_explanation"] else "diagnose"


def route_after_reply(state: State) -> str:
    if ready_to_continue(state["explain_history"][-1]["content"]):
        return "finish_explaining"
    return "explain"


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
builder.add_node("classify_answer", classify_answer)
builder.add_node("diagnose", diagnose)
builder.add_node("explain", explain)
builder.add_node("get_learner_reply", get_learner_reply)
builder.add_node("finish_explaining", finish_explaining)
builder.add_node("downgrade", downgrade)
builder.add_node("record", record)

builder.add_edge(START, "pick_lesson")
builder.add_edge("pick_lesson", "load_content")
builder.add_edge("load_content", "ask")
builder.add_edge("ask", "get_answer")
builder.add_edge("get_answer", "classify_answer")
builder.add_conditional_edges("classify_answer", route_after_answer, {
    "explain": "explain",
    "diagnose": "diagnose",
})
builder.add_conditional_edges("diagnose", route_after_diagnose, {
    "downgrade": "downgrade",
    "record": "record",
})
builder.add_edge("downgrade", "ask")     # the loop: back up to ask, now at a lower level
builder.add_edge("explain", "get_learner_reply")
builder.add_conditional_edges("get_learner_reply", route_after_reply, {
    "explain": "explain",                # still discussing - keep teaching
    "finish_explaining": "finish_explaining",
})
builder.add_edge("finish_explaining", "record")
builder.add_edge("record", END)

graph = builder.compile(checkpointer=InMemorySaver())


if __name__ == "__main__":
    # The graph itself knows nothing about terminals or Telegram - it just
    # pauses at get_answer and hands back a question. This loop is the CLI's
    # own thin wrapper: print the question, read real input, resume with it.
    config = {"configurable": {"thread_id": "cli-demo"}}

    result = graph.invoke({
        "lesson_id": "", "lesson_name": "", "content": "", "level": 0,
        "question": {}, "answer": "", "assessment": {}, "transcript": [], "outcome": "",
        "explain_history": [], "wants_explanation": False,
    }, config=config)

    while "__interrupt__" in result:
        payload = result["__interrupt__"][0].value
        if payload["kind"] == "question":
            print(f"\n  [level {payload['level']}/4] {payload['question']}")
            if payload.get("hint"):
                print(f"  hint: {payload['hint']}")
            reply = input("  your answer (or 'I don't know' to be taught): ")
        else:  # "explanation"
            print(f"\n  {payload['text']}")
            reply = input("  you (ask more, or say you're ready to continue): ")
        result = graph.invoke(Command(resume=reply), config=config)

    print(f"\nLesson: {result['lesson_name']}")
    print(f"Attempts: {len(result['transcript'])}")
    for entry in result["transcript"]:
        print(f"  level {entry['level']}: score {entry['score']}/4")
