"""
Question Generator — uses Claude API to create quiz questions from lesson content.
"""

import os
import json
import anthropic


SYSTEM_PROMPT = """You are a tutor that generates quiz questions from course notes.

Rules:
- Generate exactly ONE question per request
- The question should test deep understanding, not surface recall
- Focus on "why" and "how" questions, not "what" definitions
- Return your response as JSON with this exact format:

{
    "question": "Your question here",
    "hint": "A brief hint that guides without giving the answer",
    "key_concepts": ["concept1", "concept2"]
}

Return ONLY the JSON, no other text."""


class QuestionGenerator:
    """Generates quiz questions from lesson content using Claude API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def generate(self, lesson_name: str, lesson_content: str) -> dict:
        """
        Generate a question from lesson content.

        Args:
            lesson_name: Name of the lesson
            lesson_content: Full markdown content of the lesson

        Returns:
            Dictionary with 'question', 'hint', and 'key_concepts'
        """
        user_message = f"""Generate a quiz question from this lesson.

Lesson: {lesson_name}

Content:
{lesson_content}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )

        text = response.content[0].text

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {
                "question": text,
                "hint": "",
                "key_concepts": []
            }

        return result