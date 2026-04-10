"""
CLI interface for the Smart Repetition Agent.

Usage:
    python -m agent.src.scheduler.cli status
    python -m agent.src.scheduler.cli review
    python -m agent.src.scheduler.cli stats
"""

import sys
from pathlib import Path

from agent.src.scheduler.review import (
    SchedulerManager, ReviewSession, Rating,
    save_review_state, load_review_state
)
from agent.src.course_parser.models import load_courses_from_json
from agent.src.ai.question_generator import QuestionGenerator
from agent.src.ai.answer_assessor import AnswerAssessor


# --- Paths ---
COURSES_PATH = "data/courses.json"
REVIEW_STATE_PATH = "data/review_state.json"
VAULT_COURSES_PATH = Path(
    "/Users/dasmod/Library/Mobile Documents"
    "/iCloud~md~obsidian/Documents/dasmod"
    "/02 Source Material/Courses"
)


def setup() -> SchedulerManager:
    """Load courses, restore saved state, return ready manager."""
    courses = load_courses_from_json(COURSES_PATH)
    manager = SchedulerManager()
    load_review_state(manager, REVIEW_STATE_PATH)
    manager.create_items_from_courses(courses)
    return manager


def load_lesson_content(lesson_name: str) -> str:
    """Find and read lesson content from the Obsidian vault."""
    for course_dir in VAULT_COURSES_PATH.iterdir():
        if not course_dir.is_dir():
            continue
        for file in course_dir.iterdir():
            if file.suffix == ".md" and lesson_name.lower() in file.stem.lower():
                return file.read_text(encoding="utf-8")
    return ""


def cmd_status() -> None:
    """Show how many items are total, due, and new."""
    manager = setup()
    print(f"Total items: {len(manager.items)}")
    print(f"Due today:   {len(manager.get_due_items())}")
    print(f"New:         {len(manager.get_new_items())}")


def cmd_review() -> None:
    """Run an interactive review session with AI-generated questions."""
    manager = setup()
    session = ReviewSession(manager)

    if session.is_complete:
        print("Nothing due! Come back later.")
        return

    generator = QuestionGenerator()
    assessor = AnswerAssessor()

    score_to_rating = {
        1: Rating.Again,
        2: Rating.Hard,
        3: Rating.Good,
        4: Rating.Easy,
    }

    while not session.is_complete:
        item = session.current_item()

        # --- Card info ---
        print(f"\n--- Card {session.stats.total_reviewed + 1} of {len(session.queue)} ---")
        print(f"  Lesson:    {item.lesson_name}")
        print(f"  Chapter:   {item.chapter}")
        print(f"  Course:    {item.course}")
        print(f"  Remaining: {session.remaining}")

        # --- Load lesson content ---
        content = load_lesson_content(item.lesson_name)
        if content == "":
            print("  ⚠ Empty lesson content — skipping.")
            session.submit_rating(Rating.Again)
            continue

        # --- Generate question ---
        question_data = generator.generate(item.lesson_name, content)
        print(f"\n  Question: {question_data['question']}")
        print(f"  Hint:     {question_data['hint']}")

        # --- Get answer ---
        answer = input("\n  Your answer (or 'skip'): ")
        if answer.lower() == "skip":
            session.submit_rating(Rating.Again)
            continue

        # --- Assess answer ---
        assessment = assessor.assess(question_data["question"], answer, content)
        print(f"\n  Score:          {assessment['score']}/4")
        print(f"  Explanation:    {assessment['explanation']}")
        print(f"  Correct answer: {assessment['correct_answer']}")

        # --- Update FSRS ---
        rating = score_to_rating[assessment["score"]]
        session.submit_rating(rating)

    # --- Save and summarize ---
    save_review_state(manager, REVIEW_STATE_PATH)

    summary = session.summary()
    print(f"\n--- Session Complete ---")
    print(f"  Reviewed: {summary['total_reviewed']}")
    print(f"  Duration: {summary['duration_seconds']}s")
    print(f"  Ratings:  {summary['ratings']}")


def cmd_stats() -> None:
    """Show overall review statistics."""
    manager = setup()
    reviewed = [item for item in manager.items.values() if not item.is_new()]
    new = [item for item in manager.items.values() if item.is_new()]
    print(f"Reviewed: {len(reviewed)}")
    print(f"New:      {len(new)}")


def main() -> None:
    """Parse command and run the right function."""
    if len(sys.argv) < 2:
        print("Usage: python -m agent.src.scheduler.cli [status|review|stats]")
        return

    command = sys.argv[1]

    if command == "status":
        cmd_status()
    elif command == "review":
        cmd_review()
    elif command == "stats":
        cmd_stats()
    else:
        print(f"Unknown command: {command}")
        print("Available: status, review, stats")


if __name__ == "__main__":
    main()