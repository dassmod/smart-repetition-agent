"""
FSRS Review Scheduler

Connects your course lessons to the FSRS spaced repetition system.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from fsrs import Scheduler, Card, Rating
import json
import re


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
    
    def __init__(self, desired_retention: float = 0.9):
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
    