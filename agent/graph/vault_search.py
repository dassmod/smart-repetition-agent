"""Vault search: a node that finds vault passages by meaning, not by filename."""

import sys
from pathlib import Path
from typing import TypedDict

from langgraph.graph import StateGraph, START, END

# --- plumbing: let this file find your existing code under agent/src ---
ROOT = Path(__file__).resolve().parents[2]          # the obsidian-knowledge-agent folder
sys.path.insert(0, str(ROOT))
from agent.src.retrieval.store import load_or_build

INDEX_DIR = str(ROOT / "data" / "vault_index")
COURSES_JSON = str(ROOT / "data" / "courses.json")


# --- the tool: search the vault index by meaning ---
def search_vault(query: str, k: int = 5) -> list[dict]:
    index = load_or_build(INDEX_DIR, COURSES_JSON)
    return index.search(query, k=k)


# --- state: the notebook carries a query in, and the matching passages out ---
class State(TypedDict):
    query: str
    results: list[dict]


# --- node: call the tool, write the result into the notebook ---
def retrieve(state: State) -> dict:
    return {"results": search_vault(state["query"])}


# --- wiring: START -> retrieve -> END ---
builder = StateGraph(State)
builder.add_node("retrieve", retrieve)
builder.add_edge(START, "retrieve")
builder.add_edge("retrieve", END)
graph = builder.compile()


if __name__ == "__main__":
    query = "why does gradient staleness slow down convergence"
    result = graph.invoke({"query": query, "results": []})
    print(f"query: {query!r}\n")
    for r in result["results"]:
        print(f"  score {r['score']:.3f}  [{r['lesson_name']}]")
        print(f"    {r['text'][:160].replace(chr(10), ' ')}...")
        print()
