"""
Prompt Builder — constructs dynamic prompts based on card state.
"""

from agent.src.scheduler.review import ReviewItem


# Question types by consolidation level
QUESTION_TYPES = {
    1: [
        "Ask a direct recall question about a key concept from this lesson.",
        "Ask a 'what is' or 'what does' question about a specific term or mechanism.",
        "Ask the student to explain one specific process described in the lesson.",
    ],
    2: [
        "Ask a 'why' question that requires understanding the reasoning behind a concept.",
        "Ask the student to compare two related concepts from this lesson.",
        "Ask the student to explain what would happen if a key component were removed or changed.",
    ],
    3: [
        "Ask a question that connects this lesson to broader themes in the chapter.",
        "Ask the student to design a simple system using concepts from this lesson.",
        "Ask the student to identify trade-offs in an approach described in this lesson.",
    ],
    4: [
        "Ask a question that requires synthesizing knowledge across multiple topics.",
        "Ask the student to evaluate a proposed solution using principles from this lesson.",
        "Present a novel scenario and ask how concepts from this lesson would apply.",
    ],
}


def get_consolidation_level(item: ReviewItem) -> int:
    """Determine question difficulty based on card stability."""
    stability = item.card.stability

    if stability is None or stability < 5:
        return 1
    elif stability < 20:
        return 2
    elif stability < 60:
        return 3
    else:
        return 4


def build_question_prompt(item: ReviewItem) -> str:
    """Build a dynamic system prompt based on the card's state."""
    level = get_consolidation_level(item)
    question_types = QUESTION_TYPES[level]

    import random
    question_style = random.choice(question_types)

    return f"""You are a tutor generating quiz questions from course notes.

Consolidation Level: {level}/4
Question Style: {question_style}

Rules:
- Generate exactly ONE question
- Match the difficulty to consolidation level {level}
- Level 1 = basic recall, Level 4 = deep synthesis
- Return your response as JSON with this exact format:

{{
    "question": "Your question here",
    "hint": "A brief hint that guides without giving the answer",
    "key_concepts": ["concept1", "concept2"],
    "difficulty": {level}
}}

Return ONLY the JSON, no other text."""


def build_assessment_prompt(level: int) -> str:
    """Build a dynamic assessment prompt based on difficulty level."""
    strictness = {
        1: "Be lenient — accept any answer that shows basic understanding of the concept.",
        2: "Be moderate — the answer should show understanding of WHY, not just WHAT.",
        3: "Be thorough — the answer should demonstrate connections between concepts.",
        4: "Be strict — the answer should show deep synthesis and original thinking.",
    }

    return f"""You are a tutor assessing a student's answer to a quiz question.

Difficulty Level: {level}/4
Assessment Style: {strictness[level]}

Score the answer on this scale:
1 = Again — completely wrong or no understanding shown
2 = Hard — partially correct but major gaps
3 = Good — mostly correct with minor gaps
4 = Easy — fully correct with clear understanding

Return your response as JSON with this exact format:

{{
    "score": 3,
    "explanation": "Brief explanation of what was correct and what was missing",
    "correct_answer": "What the ideal answer would include"
}}

Return ONLY the JSON, no other text."""