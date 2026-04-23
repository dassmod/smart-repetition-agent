"""
Course Parser for Smart Repetition Agent

This module scans your Obsidian vault for courses, parses their structure
(chapters and lessons), extracts content from markdown files, and prepares
data for the FSRS spaced repetition scheduler.

Usage:
    python parser.py
"""

# =============================================================================
# IMPORTS
# =============================================================================

from pathlib import Path  # For handling file paths across operating systems
import yaml               # For parsing YAML configuration files
import re                 # For regular expressions (finding headings)
from models import Heading, Lesson, Chapter, Course, save_courses_to_json


# =============================================================================
# CONFIGURATION
# =============================================================================

# Your Obsidian vault location - change this to YOUR path
VAULT_PATH = Path("/Users/dasmod/Library/Mobile Documents/iCloud~md~obsidian/Documents/dasmod")

# Where courses live within the vault
COURSES_PATH = VAULT_PATH / "04 Resources" / "Courses"

# Where to save the JSON output
OUTPUT_PATH = Path(__file__).parent.parent.parent.parent / "data" / "courses.json"


# =============================================================================
# LESSON READING FUNCTIONS
# =============================================================================

def read_lesson(lesson_path: Path, lesson_name: str, chapter_name: str) -> Lesson | None:
    """
    Read a lesson markdown file and return a Lesson object.
    """
    if not lesson_path.exists():
        return None
    
    with open(lesson_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse frontmatter
    frontmatter = {}
    body = content
    
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            frontmatter_text = parts[1].strip()
            body = parts[2].strip()
            try:
                frontmatter = yaml.safe_load(frontmatter_text) or {}
            except yaml.YAMLError:
                frontmatter = {}
    
    # Extract headings
    headings = []
    for line in body.split('\n'):
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        if match:
            headings.append(Heading(
                level=len(match.group(1)),
                text=match.group(2).strip()
            ))
    
    # Create and return Lesson object
    return Lesson(
        name=lesson_name,
        chapter=chapter_name,
        file_path=str(lesson_path),
        content=body,
        word_count=len(body.split()),
        headings=headings,
        difficulty=frontmatter.get('difficulty'),
        tags=frontmatter.get('tags', []),
        estimated_review_minutes=frontmatter.get('estimated_review_minutes')
    )


def find_lesson_file(course_path: Path, lesson_name: str) -> Path | None:
    """
    Find the markdown file that matches a lesson name from the config.
    
    The config might say "Lesson 01 - Intro" but the file is
    "Lesson 01 - Intro.md" - this function handles that matching.
    
    Args:
        course_path: Path to the course folder
        lesson_name: Lesson name from _course.yaml
        
    Returns:
        Path to the .md file, or None if not found
    """
    # Try 1: Exact match with .md extension
    exact_path = course_path / f"{lesson_name}.md"
    if exact_path.exists():
        return exact_path
    
    # Try 2: Case-insensitive search
    # (in case "lesson 01" vs "Lesson 01")
    lesson_lower = lesson_name.lower()
    for file in course_path.glob("*.md"):  # *.md = all markdown files
        # file.stem = filename without extension
        if file.stem.lower() == lesson_lower:
            return file
    
    # No match found
    return None


def extract_headings(content: str) -> list:
    """
    Extract all markdown headings from content.
    
    Finds lines like:
        # Heading 1
        ## Heading 2
        ### Heading 3
    
    Args:
        content: The markdown text to scan
        
    Returns:
        List of dicts with 'level' (1-6) and 'text' (heading text)
    """
    headings = []
    
    # Check each line for heading pattern
    for line in content.split('\n'):
        # Regex pattern explained:
        # ^        = start of line
        # (#{1,6}) = capture 1-6 hash symbols
        # \s+      = one or more spaces
        # (.+)     = capture the heading text
        # $        = end of line
        match = re.match(r'^(#{1,6})\s+(.+)$', line)
        
        if match:
            # match.group(1) = the hash symbols (e.g., "##")
            # match.group(2) = the heading text
            level = len(match.group(1))   # "##" -> 2
            text = match.group(2).strip()
            
            headings.append({
                'level': level,
                'text': text
            })
    
    return headings


# =============================================================================
# COURSE CONFIGURATION FUNCTIONS
# =============================================================================

def load_course_config(course_path: Path) -> dict | None:
    """
    Load and validate the _course.yaml configuration file.
    
    Args:
        course_path: Path to the course folder
        
    Returns:
        Parsed config dictionary, or None if invalid
    """
    config_file = course_path / "_course.yaml"
    
    try:
        # Open and parse the YAML file
        with open(config_file, 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
        
        # Validation: check for empty file
        if not config:
            print(f"  Warning: {config_file} is empty")
            return None
        
        # Validation: check for required 'title' field
        if 'title' not in config:
            print(f"  Warning: {config_file} missing 'title'")
            return None
        
        return config
        
    except yaml.YAMLError as e:
        # Handle malformed YAML
        print(f"  Error parsing {config_file}: {e}")
        return None
    
    except FileNotFoundError:
        # Handle missing file
        print(f"  Error: {config_file} not found")
        return None


# =============================================================================
# COURSE DISCOVERY FUNCTIONS
# =============================================================================

def find_courses() -> list:
    """
    Scan the courses folder and find all valid courses.
    
    A valid course is a folder containing a _course.yaml file.
    
    Returns:
        List of dicts, each with 'path' and 'config' keys
    """
    courses = []
    
    # Iterate through all items in the Courses folder
    for item in COURSES_PATH.iterdir():
        # Skip files, we only want folders
        if not item.is_dir():
            continue
        
        # Check if this folder has a _course.yaml
        config_file = item / "_course.yaml"
        if config_file.exists():
            # Try to load the config
            config = load_course_config(item)
            
            # Skip if config is invalid
            if config is None:
                continue
            
            print(f"\nFound: {config['title']}")
            
            # Add to our list
            courses.append({
                'path': item,
                'config': config
            })
    
    return courses

def load_full_course(course_path: Path, config: dict) -> Course:
    """
    Load a complete Course object with all chapters and lessons.
    
    Args:
        course_path: Path to the course folder
        config: Parsed _course.yaml config
        
    Returns:
        Course object with all data populated
    """
    chapters = []
    
    for chapter_data in config.get('chapters', []):
        chapter_name = chapter_data['name']
        lessons = []
        
        for lesson_name in chapter_data.get('lessons', []):
            file_path = find_lesson_file(course_path, lesson_name)
            
            if file_path:
                lesson = read_lesson(file_path, lesson_name, chapter_name)
                if lesson:
                    lessons.append(lesson)
        
        # Create Chapter object
        chapter = Chapter(name=chapter_name, lessons=lessons)
        chapters.append(chapter)
    
    # Create and return Course object
    return Course(
        title=config['title'],
        path=str(course_path),
        description=config.get('description', ''),
        chapters=chapters
    )

# =============================================================================
# MAIN EXECUTION
# =============================================================================

if __name__ == "__main__":
    """
    Main entry point - runs when you execute: python parser.py
    """
    
    print("=" * 50)
    print("Smart Repetition Agent - Course Parser")
    print("=" * 50)
    print(f"\nScanning: {COURSES_PATH}")
    
    # Step 1: Find all courses
    found = find_courses()
    
    # Step 2: Load full course data
    courses = []
    
    for course_data in found:
        course_path = course_data['path']
        config = course_data['config']
        
        # Load complete course with all lessons
        course = load_full_course(course_path, config)
        courses.append(course)
        
        # Print summary
        print(f"\n{'=' * 40}")
        print(f"Course: {course.title}")
        print(f"{'=' * 40}")
        print(f"  Total chapters: {len(course.chapters)}")
        print(f"  Total lessons: {course.total_lessons}")
        print(f"  Total words: {course.total_words}")
        
        for chapter in course.chapters:
            print(f"\n  Chapter: {chapter.name}")
            print(f"    Lessons: {chapter.lesson_count}")
            print(f"    Words: {chapter.total_words}")
            
            for lesson in chapter.lessons:
                print(f"\n      ✓ {lesson.name}")
                print(f"        Words: {lesson.word_count}")
                print(f"        Headings: {len(lesson.headings)}")
                print(f"        Difficulty: {lesson.difficulty or 'not set'}")
    
    # Step 3: Save to JSON
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)  # Create data/ folder if needed
    save_courses_to_json(courses, str(OUTPUT_PATH))
    
    # Summary
    print(f"\n{'=' * 50}")
    print(f"Total courses: {len(courses)}")
    print(f"Output saved to: {OUTPUT_PATH}")
    print("=" * 50)