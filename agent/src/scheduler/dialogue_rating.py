"""
Dialogue rating - Rung 7.

Collapses a whole adaptive_dialogue transcript (one or more attempts, since a
fuzzy answer drops the difficulty and tries again) into a single FSRS rating
and a single (score, level) pair for the on-chain proof.
"""

from agent.src.scheduler.review import Rating

SCORE_TO_RATING = {
    1: Rating.Again,
    2: Rating.Hard,
    3: Rating.Good,
    4: Rating.Easy,
}


def rate_dialogue(transcript: list[dict]) -> dict:
    """
    Decide what to actually record for a finished dialogue.

    Uses the FIRST attempt only, deliberately: it is the honest signal of how
    well the learner recalled the material at the level FSRS believed they
    were at. Later, easier retries after a downgrade are a teaching aid for
    the moment - they help the learner leave with something solid - but they
    should not inflate what gets scheduled or proven on-chain, or FSRS would
    conclude the learner has mastered a level they actually needed help on.
    """
    first_attempt = transcript[0]
    score = first_attempt["score"]
    level = first_attempt["level"]

    return {
        "rating": SCORE_TO_RATING[score],
        "score": score,
        "level": level,
        "attempts": len(transcript),
    }
