"""
Drives the adaptive dialogue loop for the Telegram bot: one lesson at a time,
paused between messages instead of blocking on terminal input.

Reuses the exact same ask / get_answer / diagnose / downgrade / record nodes
from adaptive_dialogue.py - the tutoring logic is identical. The only real
difference is what starts the chain: adaptive_dialogue.py picks its own due
lesson for a standalone demo; here, the Telegram bot's own review queue
already knows which lesson is current, so the chain starts at "ask" and the
lesson is handed in directly.
"""

from langgraph.graph import StateGraph, START, END
from langgraph.types import Command
from langgraph.checkpoint.memory import InMemorySaver

from agent.graph.adaptive_dialogue import (
    State, ask, get_answer, diagnose, downgrade, record, route_after_diagnose,
    explain, get_learner_reply, finish_explaining, route_after_answer, route_after_reply,
    classify_answer,
)

builder = StateGraph(State)
builder.add_node("ask", ask)
builder.add_node("get_answer", get_answer)
builder.add_node("classify_answer", classify_answer)
builder.add_node("diagnose", diagnose)
builder.add_node("explain", explain)
builder.add_node("get_learner_reply", get_learner_reply)
builder.add_node("finish_explaining", finish_explaining)
builder.add_node("downgrade", downgrade)
builder.add_node("record", record)

builder.add_edge(START, "ask")
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
builder.add_edge("downgrade", "ask")
builder.add_edge("explain", "get_learner_reply")
builder.add_conditional_edges("get_learner_reply", route_after_reply, {
    "explain": "explain",
    "finish_explaining": "finish_explaining",
})
builder.add_edge("finish_explaining", "record")
builder.add_edge("record", END)

graph = builder.compile(checkpointer=InMemorySaver())


def _as_response(result: dict) -> dict:
    """Translate a raw graph result into the shape the bot actually needs."""
    if "__interrupt__" in result:
        return result["__interrupt__"][0].value  # already carries its own "kind": question or explanation

    return {"kind": "done", "outcome": result["outcome"], "transcript": result["transcript"]}


def start_dialogue(thread_id: str, lesson_id: str, lesson_name: str, content: str, level: int) -> dict:
    """Begin a fresh dialogue about one lesson. Returns the first question to show."""
    result = graph.invoke({
        "lesson_id": lesson_id, "lesson_name": lesson_name, "content": content, "level": level,
        "question": {}, "answer": "", "assessment": {}, "transcript": [], "outcome": "",
        "explain_history": [], "wants_explanation": False,
    }, config={"configurable": {"thread_id": thread_id}})
    return _as_response(result)


def submit_answer(thread_id: str, answer: str) -> dict:
    """Resume a paused dialogue with the learner's real answer."""
    result = graph.invoke(Command(resume=answer), config={"configurable": {"thread_id": thread_id}})
    return _as_response(result)
