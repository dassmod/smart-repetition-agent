"""
CLI interface for the Smart Repetition Agent.

Usage:
    python -m agent.src.scheduler.cli status
    python -m agent.src.scheduler.cli review
    python -m agent.src.scheduler.cli stats
"""

import sys
from agent.src.scheduler.review import (
    SchedulerManager, ReviewSession, Rating,
    save_review_state, load_review_state
)
from agent.src.course_parser.models import load_courses_from_json


COURSES_PATH = "data/courses.json"
REVIEW_STATE_PATH = "data/review_state.json"


def setup():
    """Load courses, restore saved state, return ready manager."""
    courses = load_courses_from_json(COURSES_PATH)
    manager = SchedulerManager()
    load_review_state(manager, REVIEW_STATE_PATH)
    manager.create_items_from_courses(courses)
    return manager


def cmd_status():
    """Show how many items are total, due, and new."""
    manager = setup()
    total = len(manager.items)
    due = len(manager.get_due_items())
    new = len(manager.get_new_items())
    print(f"Total items: {total}")
    print(f"Due today:   {due}")
    print(f"New:         {new}")


def cmd_review():
    """Run an interactive review session."""
    manager = setup()
    session = ReviewSession(manager)

    if session.is_complete:
        print("Nothing due! Come back later.")
        return

    rating_map = {
        '1': Rating.Again,
        '2': Rating.Hard,
        '3': Rating.Good,
        '4': Rating.Easy,
    }

    while not session.is_complete:
        item = session.current_item()
        print(f"\n--- Card {session.stats.total_reviewed + 1} of {len(session.queue)} ---")
        print(f"  Lesson:  {item.lesson_name}")
        print(f"  Chapter: {item.chapter}")
        print(f"  Course:  {item.course}")
        print(f"  Remaining: {session.remaining}")

        while True:
            answer = input("\nRate (1=Again, 2=Hard, 3=Good, 4=Easy): ")
            if answer in rating_map:
                break
            print("Invalid. Enter 1-4.")

        session.submit_rating(rating_map[answer])

    save_review_state(manager, REVIEW_STATE_PATH)

    summary = session.summary()
    print(f"\n--- Session Complete ---")
    print(f"  Reviewed:  {summary['total_reviewed']}")
    print(f"  Duration:  {summary['duration_seconds']}s")
    print(f"  Ratings:   {summary['ratings']}")


def cmd_stats():
    """Show overall review statistics."""
    manager = setup()
    reviewed = [item for item in manager.items.values() if not item.is_new()]
    new = [item for item in manager.items.values() if item.is_new()]
    print(f"Reviewed: {len(reviewed)}")
    print(f"New:      {len(new)}")


def main():
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