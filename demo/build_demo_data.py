"""
Build a courses.json from the bundled demo/ course, for anyone trying this
repo without their own Obsidian vault.

Usage:
    python demo/build_demo_data.py

Writes to data/demo_courses.json - it never touches your real data/courses.json.
To actually try the demo:
    cp data/demo_courses.json data/courses.json
    rm -rf data/vault_index   # force a fresh embed over the demo lessons
    python agent/graph/ask_question.py
"""

import json
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DEMO_DIR = Path(__file__).resolve().parent
OUTPUT_PATH = ROOT / "data" / "demo_courses.json"


def read_lesson(lesson_path: Path, lesson_name: str, chapter_name: str) -> dict:
    raw = lesson_path.read_text(encoding="utf-8")

    frontmatter, body = {}, raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) >= 3:
            body = parts[2].strip()
            try:
                frontmatter = yaml.safe_load(parts[1].strip()) or {}
            except yaml.YAMLError:
                frontmatter = {}

    headings = [
        {"level": len(m.group(1)), "text": m.group(2).strip()}
        for line in body.split("\n")
        if (m := re.match(r"^(#{1,6})\s+(.+)$", line))
    ]

    return {
        "name": lesson_name,
        "chapter": chapter_name,
        "file_path": str(lesson_path),
        "word_count": len(body.split()),
        "difficulty": frontmatter.get("difficulty"),
        "tags": frontmatter.get("tags", []),
        "estimated_review_minutes": frontmatter.get("estimated_review_minutes"),
        "consolidation_level": 1,
        "headings": headings,
    }


def build_demo_course(course_dir: Path) -> dict:
    config = yaml.safe_load((course_dir / "_course.yaml").read_text(encoding="utf-8"))

    chapters = []
    for chapter_data in config["chapters"]:
        lessons = []
        for lesson_name in chapter_data["lessons"]:
            lesson_path = course_dir / f"{lesson_name}.md"
            lessons.append(read_lesson(lesson_path, lesson_name, chapter_data["name"]))

        chapters.append({
            "name": chapter_data["name"],
            "lesson_count": len(lessons),
            "total_words": sum(l["word_count"] for l in lessons),
            "lessons": lessons,
        })

    return {
        "title": config["title"],
        "path": str(course_dir),
        "description": config.get("description", ""),
        "total_lessons": sum(c["lesson_count"] for c in chapters),
        "total_words": sum(c["total_words"] for c in chapters),
        "chapters": chapters,
    }


if __name__ == "__main__":
    course = build_demo_course(DEMO_DIR / "Coffee Science")

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump([course], f, indent=2, ensure_ascii=False)

    print(f"Wrote {course['total_lessons']} demo lessons to {OUTPUT_PATH}")
    print("To try it: cp data/demo_courses.json data/courses.json && rm -rf data/vault_index")
