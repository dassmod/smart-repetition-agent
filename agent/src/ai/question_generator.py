"""
Question Generator - uses Claude API to create quiz questions from lesson content.
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

    def generate(self, lesson_name: str, content: str, system_prompt: str = None) -> dict:
        """
        Generate a question from lesson content.

        Args:
            lesson_name: Name of the lesson
            content: Full markdown content of the lesson
            system_prompt: Optional dynamic prompt (overrides default)

        Returns:
            Dictionary with 'question', 'hint', and 'key_concepts'
        """
        prompt = system_prompt or SYSTEM_PROMPT

        user_message = f"""Generate a quiz question from this lesson.

Lesson: {lesson_name}

Content:
{content}"""

        text = self._call_api(prompt, user_message)

        if text is None:
            return {"question": "Failed to generate question", "hint": "", "key_concepts": []}

        text = text.strip().strip('`').strip()
        if text.startswith('json'):
            text = text[4:].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {
                "question": text,
                "hint": "",
                "key_concepts": []
            }

        return result

    def _call_api(self, system_prompt: str, user_message: str, max_retries: int = 1) -> str | None:
        """Call Claude API with retry logic."""
        for attempt in range(max_retries + 1):
            try:
                response = self.client.messages.create(
                    model=self.model,
                    max_tokens=1024,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_message}]
                )
                return response.content[0].text
            except anthropic.APITimeoutError:
                if attempt < max_retries:
                    print("  ⚠ API timeout, retrying...")
                    continue
                print("  ⚠ API timeout, skipping.")
                return None
            except anthropic.APIError as e:
                print(f"  ⚠ API error: {e}")
                return None
        return None