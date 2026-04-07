"""
FSRS Review Scheduler

Connects your course lessons to the FSRS spaced repetition system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from fsrs import Scheduler, Card, Rating, State
import json
import re
import os


def make_lesson_id(lesson_name: str) -> str:
    """
    Convert lesson name to a URL-safe slug.
    
    "Lesson 01 - Decentralized Training" → "lesson-01-decentralized-training"
    """
    # Lowercase everything
    slug = lesson_name.lower()
    
    # Replace spaces and underscores with hyphens
    slug = slug.replace(' ', '-').replace('_', '-')
    
    # Remove anything that's not a letter, number, or hyphen
    slug = re.sub(r'[^a-z0-9-]', '', slug)
    
    # Collapse multiple hyphens into one
    slug = re.sub(r'-+', '-', slug)
    
    # Remove leading/trailing hyphens
    slug = slug.strip('-')
    
    return slug


@dataclass
class ReviewItem:
    """
    Bridges a lesson to its FSRS card.
    """
    lesson_id: str
    lesson_name: str
    chapter: str
    course: str
    card: Card = field(default_factory=Card)
    
    def is_due(self, now: datetime = None) -> bool:
        """Check if this item needs review."""
        if now is None:
            now = datetime.now(timezone.utc)
        return self.card.due <= now
    
    def is_new(self) -> bool:
        """Check if this item has never been reviewed."""
        return self.card.stability is None or self.card.stability == 0


class SchedulerManager:
    """
    Manages all review items and FSRS scheduling.
    """
    
    def __init__(self, desired_retention: float = 0.9) -> None:
        self.scheduler = Scheduler(desired_retention=desired_retention)
        self.items: dict[str, ReviewItem] = {}  # lesson_id → ReviewItem
    
    def create_items_from_courses(self, courses: list[dict]) -> int:
        """
        Create ReviewItems from parsed course data.
        
        Args:
            courses: List of course dicts (from courses.json)
            
        Returns:
            Number of items created
        """
        count = 0
        
        for course in courses:
            course_title = course['title']
            
            for chapter in course['chapters']:
                chapter_name = chapter['name']
                
                for lesson in chapter['lessons']:
                    lesson_name = lesson['name']
                    lesson_id = make_lesson_id(lesson_name)
                    
                    # Skip if already exists
                    if lesson_id in self.items:
                        continue
                    
                    # Create new review item
                    self.items[lesson_id] = ReviewItem(
                        lesson_id=lesson_id,
                        lesson_name=lesson_name,
                        chapter=chapter_name,
                        course=course_title,
                    )
                    count += 1
        
        return count
    
    def get_due_items(self, now: datetime = None) -> list[ReviewItem]:
        """Get all items that need review."""
        if now is None:
            now = datetime.now(timezone.utc)
        return [item for item in self.items.values() if item.is_due(now)]
    
    def get_new_items(self) -> list[ReviewItem]:
        """Get all items that have never been reviewed."""
        return [item for item in self.items.values() if item.is_new()]
    
    def review_item(self, lesson_id: str, rating: Rating) -> ReviewItem:
        """
        Record a review for an item.
        
        Args:
            lesson_id: Which item was reviewed
            rating: Rating.Again / Hard / Good / Easy
            
        Returns:
            Updated ReviewItem
        """
        item = self.items[lesson_id]
        item.card, _ = self.scheduler.review_card(item.card, rating)
        return item


@dataclass
class SessionStats:
    """
    Tracks statistics for a single review session.
    
    Accumulates rating counts and timing data as the user
    works through their review queue.
    """
    total_reviewed: int = 0
    ratings_count: dict[str, int] = field(
        default_factory=lambda: {'again': 0, 'hard': 0, 'good': 0, 'easy': 0}
    )
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    ended_at: datetime | None = None

    @property
    def duration_seconds(self) -> float:
        """Calculate session duration. Uses current time if session is still active."""
        end = self.ended_at or datetime.now(timezone.utc)
        return (end - self.started_at).total_seconds()

    def record_rating(self, rating: Rating) -> None:
        """
        Record a single rating into the session stats.
        
        Args:
            rating: The FSRS Rating enum (Again, Hard, Good, Easy)
        """
        # Map Rating enum to string key for the counts dictionary
        rating_names: dict[Rating, str] = {
            Rating.Again: 'again',
            Rating.Hard: 'hard',
            Rating.Good: 'good',
            Rating.Easy: 'easy',
        }

        name = rating_names[rating]
        self.ratings_count[name] += 1
        self.total_reviewed += 1


class ReviewSession:
    """
    Drives a single review session through the due items queue.
    
    Wraps SchedulerManager to present items one at a time,
    collect ratings, and track session-level statistics.
    """

    def __init__(self, manager: SchedulerManager) -> None:
        self.manager: SchedulerManager = manager
        self.queue: list[ReviewItem] = manager.get_due_items()
        self.current_index: int = 0
        self.stats: SessionStats = SessionStats()

    @property
    def remaining(self) -> int:
        """Number of items left to review in this session."""
        return len(self.queue) - self.current_index

    @property
    def is_complete(self) -> bool:
        """Whether all items in the queue have been reviewed."""
        return self.current_index >= len(self.queue)

    def current_item(self) -> ReviewItem | None:
        """
        Get the current item to review.
        
        Returns:
            The current ReviewItem, or None if the session is complete.
        """
        if self.is_complete:
            return None
        return self.queue[self.current_index]

    def submit_rating(self, rating: Rating) -> ReviewItem | None:
        """
        Submit a rating for the current item and advance the queue.
        
        Args:
            rating: The FSRS Rating enum (Again, Hard, Good, Easy)
            
        Returns:
            The reviewed item, or None if session was already complete.
        """
        item = self.current_item()
        if item is None:
            return None

        # Send rating to FSRS through the manager
        self.manager.review_item(item.lesson_id, rating)
        self.stats.record_rating(rating)
        self.current_index += 1

        # Stamp the end time when we finish the last item
        if self.is_complete:
            self.stats.ended_at = datetime.now(timezone.utc)

        return item

    def summary(self) -> dict:
        """
        Generate a summary dict of the session so far.
        
        Returns:
            Dict with total_reviewed, duration, ratings breakdown, and remaining count.
        """
        return {
            'total_reviewed': self.stats.total_reviewed,
            'duration_seconds': round(self.stats.duration_seconds, 1),
            'ratings': self.stats.ratings_count,
            'remaining': self.remaining,
        }

def card_to_dict(card) -> dict:
    """Convert a Card object to a JSON-friendly dictionary."""
    return {
        'due': card.due.isoformat(),
        'stability': card.stability,
        'difficulty': card.difficulty,
        'elapsed_days': card.elapsed_days,
        'scheduled_days': card.scheduled_days,
        'reps': card.reps,
        'lapses': card.lapses,
        'state': card.state.value,
        'last_review': card.last_review.isoformat() if card.last_review else None
    }

def dict_to_card(data) -> Card:
    """Rebuild a Card object from a dictionary."""
    card = Card()

    card.due = datetime.fromisoformat(data["due"])
    card.stability = data["stability"]
    card.difficulty = data["difficulty"]
    card.elapsed_days = data["elapsed_days"]
    card.scheduled_days = data["scheduled_days"]
    card.reps = data["reps"]
    card.lapses = data["lapses"]
    card.state = State(data["state"])
    card.last_review = datetime.fromisoformat(data["last_review"]) if data["last_review"] else None

    return card

def save_review_state(manager, filepath):
    """Save all review items to a JSON file."""
    data = {}
    for lesson_id, item in manager.items.items():
        data[lesson_id] = {
            "lesson_id": item.lesson_id,
            "lesson_name": item.lesson_name,
            "chapter": item.chapter,
            "course": item.course,
            "card": card_to_dict(item.card)
        }
    
    with open(filepath, 'w') as f:
        json.dump(data, f, indent=2)

def load_review_state(manager, filepath):
    """Load review items from a JSON file into the manager."""
    if not os.path.exists(filepath):
        return 0

    with open(filepath, 'r') as f:
        data = json.load(f)

    for lesson_id, item in data.items():
        review_item = ReviewItem(
            lesson_id=item["lesson_id"],
            lesson_name=item["lesson_name"],
            chapter=item["chapter"],
            course=item["course"],
            card=dict_to_card(item["card"])
        )

        manager.items[lesson_id] = review_item

    return len(data)