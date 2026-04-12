"""
Answer Assessor - uses Claude API to score answers against lesson content.
"""

import os
import json
import anthropic


SYSTEM_PROMPT = """You are a tutor assessing a student's answer to a quiz question.

You have the original lesson content, the question, and the student's answer.

Score the answer on this scale:
1 = Again - completely wrong or no understanding shown
2 = Hard - partially correct but major gaps
3 = Good - mostly correct with minor gaps
4 = Easy - fully correct with clear understanding

Return your response as JSON with this exact format:

{
    "score": 3,
    "explanation": "Brief explanation of what was correct and what was missing",
    "correct_answer": "What the ideal answer would include"
}

Return ONLY the JSON, no other text."""


class AnswerAssessor:
    """Scores student answers against lesson content using Claude API."""

    def __init__(self, model: str = "claude-sonnet-4-20250514"):
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def assess(self, question: str, answer: str, lesson_content: str, system_prompt: str = None) -> dict:
        """
        Score an answer against the lesson content.

        Args:
            question: The quiz question that was asked
            answer: The student's answer
            lesson_content: Original lesson content for reference
            system_prompt: Optional dynamic prompt (overrides default)

        Returns:
            Dictionary with 'score', 'explanation', and 'correct_answer'
        """
        prompt = system_prompt or SYSTEM_PROMPT

        user_message = f"""Assess this answer.

Question: {question}

Student's Answer: {answer}

Lesson Content:
{lesson_content}"""

        response = self.client.messages.create(
            model=self.model,
            max_tokens=1024,
            system=prompt,
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        text = response.content[0].text

        text = text.strip().strip('`').strip()
        if text.startswith('json'):
            text = text[4:].strip()

        try:
            result = json.loads(text)
        except json.JSONDecodeError:
            result = {
                "score": 2,
                "explanation": text,
                "correct_answer": ""
            }

        return result