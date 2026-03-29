"""
Data models for the Smart Repetition Agent.

These classes define the structure of courses, chapters, and lessons.
Using dataclasses gives us automatic __init__, type hints, and cleaner code.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
import json


# =============================================================================
# HEADING MODEL
# =============================================================================

@dataclass
class Heading:
    """A section heading within a lesson."""
    level: int   # 1 = h1, 2 = h2, etc.
    text: str    # The heading text


# =============================================================================
# LESSON MODEL
# =============================================================================

@dataclass
class Lesson:
    """A single lesson within a course."""
    
    # Required fields - must provide these
    name: str           # Lesson name from config
    chapter: str        # Which chapter this belongs to
    file_path: str      # Path to the .md file
    content: str        # The markdown body text
    word_count: int     # Number of words in content
    
    # Optional fields - have defaults
    headings: list = field(default_factory=list)      # List of Heading objects
    difficulty: Optional[str] = None                   # beginner/intermediate/advanced
    tags: list = field(default_factory=list)          # Tags from frontmatter
    estimated_review_minutes: Optional[int] = None    # From frontmatter
    
    # FSRS tracking fields (used in Week 2)
    consolidation_level: int = 1  # 1=lesson, 2=chapter, 3=course


# =============================================================================
# CHAPTER MODEL
# =============================================================================

@dataclass
class Chapter:
    """A chapter containing multiple lessons."""
    
    name: str
    lessons: list = field(default_factory=list)  # List of Lesson objects
    
    @property
    def total_words(self) -> int:
        """Calculate total words across all lessons."""
        return sum(lesson.word_count for lesson in self.lessons)
    
    @property
    def lesson_count(self) -> int:
        """Count of lessons in this chapter."""
        return len(self.lessons)


# =============================================================================
# COURSE MODEL
# =============================================================================

@dataclass
class Course:
    """A complete course with chapters and lessons."""
    
    title: str
    path: str
    description: str = ""
    chapters: list = field(default_factory=list)  # List of Chapter objects
    
    @property
    def total_lessons(self) -> int:
        """Count all lessons across all chapters."""
        return sum(ch.lesson_count for ch in self.chapters)
    
    @property
    def total_words(self) -> int:
        """Count all words across all chapters."""
        return sum(ch.total_words for ch in self.chapters)
    
    def get_all_lessons(self) -> list:
        """Flatten all lessons from all chapters into one list."""
        lessons = []
        for chapter in self.chapters:
            lessons.extend(chapter.lessons)
        return lessons


# =============================================================================
# JSON EXPORT FUNCTIONS
# =============================================================================

def course_to_dict(course: Course) -> dict:
    """
    Convert a Course object to a dictionary for JSON export.
    
    We do this manually instead of using asdict() because:
    1. We want to exclude the full content (too large)
    2. We want to convert Heading objects to dicts
    3. We want cleaner output
    """
    return {
        'title': course.title,
        'path': course.path,
        'description': course.description,
        'total_lessons': course.total_lessons,
        'total_words': course.total_words,
        'chapters': [
            {
                'name': chapter.name,
                'lesson_count': chapter.lesson_count,
                'total_words': chapter.total_words,
                'lessons': [
                    {
                        'name': lesson.name,
                        'chapter': lesson.chapter,
                        'file_path': lesson.file_path,
                        'word_count': lesson.word_count,
                        'difficulty': lesson.difficulty,
                        'tags': lesson.tags,
                        'estimated_review_minutes': lesson.estimated_review_minutes,
                        'consolidation_level': lesson.consolidation_level,
                        'headings': [
                            {'level': h.level, 'text': h.text}
                            for h in lesson.headings
                        ]
                        # Note: we exclude 'content' - too large for JSON
                    }
                    for lesson in chapter.lessons
                ]
            }
            for chapter in course.chapters
        ]
    }


def save_courses_to_json(courses: list, output_path: str) -> None:
    """
    Save a list of Course objects to a JSON file.
    
    Args:
        courses: List of Course objects
        output_path: Where to save the JSON file
    """
    # Convert all courses to dictionaries
    data = [course_to_dict(course) for course in courses]
    
    # Write to file with nice formatting
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"\nSaved {len(courses)} courses to {output_path}")


def load_courses_from_json(input_path: str) -> list:
    """
    Load courses from a JSON file.
    
    Note: This returns raw dictionaries, not Course objects.
    For full Course objects, you'd need to reconstruct them.
    
    Args:
        input_path: Path to the JSON file
        
    Returns:
        List of course dictionaries
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        return json.load(f)