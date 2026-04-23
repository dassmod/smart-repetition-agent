"""
Telegram Bot for the Smart Repetition Agent.

Usage:
    python -m bot.telegram_bot
"""

import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, CallbackQueryHandler

from agent.src.scheduler.review import (
    SchedulerManager, ReviewSession, Rating,
    save_review_state, load_review_state
)
from agent.src.course_parser.models import load_courses_from_json
from agent.src.ai.question_generator import QuestionGenerator
from agent.src.ai.answer_assessor import AnswerAssessor
from agent.src.ai.prompt_builder import (
    build_question_prompt, build_assessment_prompt, get_consolidation_level
)
from pathlib import Path
from blockchain.chain import BlockchainBridge


# --- Logging ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


# --- Paths ---
COURSES_PATH = "data/courses.json"
REVIEW_STATE_PATH = "data/review_state.json"
VAULT_COURSES_PATH = Path(
    "/Users/dasmod/Library/Mobile Documents"
    "/iCloud~md~obsidian/Documents/dasmod"
    "/04 Resources/Courses"
)


# --- Shared State ---
user_sessions = {}
generator = None
assessor = None
bridge = None


def setup() -> SchedulerManager:
    """Load courses, restore saved state, return ready manager."""
    courses = load_courses_from_json(COURSES_PATH)
    manager = SchedulerManager()
    load_review_state(manager, REVIEW_STATE_PATH)
    manager.create_items_from_courses(courses)
    return manager


def load_lesson_content(lesson_name: str) -> str:
    """Find and read lesson content from the Obsidian vault."""
    for course_dir in VAULT_COURSES_PATH.iterdir():
        if not course_dir.is_dir():
            continue
        for file in course_dir.iterdir():
            if file.suffix == ".md" and lesson_name.lower() in file.stem.lower():
                return file.read_text(encoding="utf-8")
    return ""


# --- Command Handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to Smart Repetition Agent!\n\n"
        "Commands:\n"
        "/review - Start a review session\n"
        "/status - Show what's due\n"
        "/skip - Skip current question\n"
        "/stop - End session early"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /status command."""
    manager = setup()
    total = len(manager.items)
    due = len(manager.get_due_items())
    new = len(manager.get_new_items())

    await update.message.reply_text(
        f"📊 Status\n\n"
        f"Total cards: {total}\n"
        f"Due today: {due}\n"
        f"New: {new}"
    )


async def cmd_review(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /review command — start a new review session."""
    user_id = update.effective_user.id

    if user_id in user_sessions:
        await update.message.reply_text("You already have an active session. Use /stop to end it first.")
        return

    manager = setup()
    session = ReviewSession(manager)

    if session.is_complete:
        await update.message.reply_text("Nothing due! Come back later. 🎉")
        return

    user_sessions[user_id] = {
        "session": session,
        "manager": manager,
        "question": None,
        "content": None,
        "level": None,
        "proposed_score": None,
        "results": [],
        "questions": [],
        "asked_questions": [],
    }

    await update.message.reply_text(
        f"📚 Review session started!\n"
        f"Cards to review: {len(session.queue)}\n\n"
        f"Generating first question..."
    )

    await send_next_question(update, context)


async def send_next_question(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Generate and send the next question to the user."""
    user_id = update.effective_user.id
    state = user_sessions.get(user_id)

    if state is None:
        return

    session = state["session"]

    if session.is_complete:
        await end_session(update, context)
        return

    item = session.current_item()

    content = load_lesson_content(item.lesson_name)
    if content == "":
        await send_message(update, f"⚠️ Empty content for {item.lesson_name}, skipping...")
        session.submit_rating(Rating.Again)
        await send_next_question(update, context)
        return

    question_prompt = build_question_prompt(item)
    asked = state.get("asked_questions", [])
    # Only avoid questions about the SAME lesson
    same_lesson_questions = [q for q in asked if q["lesson"] == item.lesson_name]
    if same_lesson_questions:
        avoid_text = "\n".join([f"- {q['question']}" for q in same_lesson_questions])
        question_prompt += f"\n\nDo NOT ask about these topics (already asked this session for this lesson):\n{avoid_text}"

    level = get_consolidation_level(item)
    question_data = generator.generate(item.lesson_name, content, system_prompt=question_prompt)

    if question_data['question'] == "Failed to generate question":
        await send_message(update, "⚠️ API error, skipping this card...")
        session.submit_rating(Rating.Again)
        await send_next_question(update, context)
        return

    state["question"] = question_data
    state["content"] = content
    state["level"] = level
    state["asked_questions"] = asked + [{"lesson": item.lesson_name, "question": question_data['question']}]

    card_num = session.stats.total_reviewed + 1
    total = len(session.queue)

    keyboard = [[InlineKeyboardButton("⏭️ Skip", callback_data="skip")]]
    markup = InlineKeyboardMarkup(keyboard)

    await send_message(
        update,
        f"📝 Card {card_num}/{total} — Level {level}/4\n"
        f"📖 {item.lesson_name}\n"
        f"📂 {item.chapter}\n\n"
        f"❓ {question_data['question']}\n\n"
        f"💡 Hint: {question_data['hint']}\n\n"
        f"Type your answer, or tap Skip below",
        reply_markup=markup
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a text message as an answer to the current question."""
    user_id = update.effective_user.id
    state = user_sessions.get(user_id)

    if state is None or state["question"] is None:
        await update.message.reply_text("No active question. Use /review to start a session.")
        return

    answer = update.message.text
    question_data = state["question"]
    content = state["content"]
    level = state["level"]

    await update.message.reply_text("🔍 Assessing your answer...")

    assessment_prompt = build_assessment_prompt(level)
    assessment = assessor.assess(
        question_data["question"], answer, content, system_prompt=assessment_prompt
    )

    score = assessment.get('score', 2)
    if not isinstance(score, int) or score < 1 or score > 4:
        score = 2

    state["proposed_score"] = score

    score_emoji = {1: "🔴", 2: "🟠", 3: "🟢", 4: "⭐"}

    keyboard = [
        [
            InlineKeyboardButton(f"✅ Accept ({score})", callback_data="accept"),
            InlineKeyboardButton("1: Again", callback_data="override_1"),
        ],
        [
            InlineKeyboardButton("2: Hard", callback_data="override_2"),
            InlineKeyboardButton("3: Good", callback_data="override_3"),
            InlineKeyboardButton("4: Easy", callback_data="override_4"),
        ]
    ]
    markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        f"{score_emoji[score]} Score: {score}/4\n\n"
        f"📋 {assessment.get('explanation', 'No explanation')}\n\n"
        f"✅ Ideal answer: {assessment.get('correct_answer', 'Not available')}\n\n"
        f"Tap to confirm or override:",
        reply_markup=markup
    )


async def handle_button(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle inline button taps."""
    query = update.callback_query
    await query.answer()

    data = query.data
    user_id = query.from_user.id
    state = user_sessions.get(user_id)

    if state is None:
        await query.edit_message_text("No active session")
        return

    session = state["session"]

    if data == "skip":
        score = 1
        rating = Rating.Again
        await query.edit_message_text("⏭️ Skipped")

    elif data == "accept":
        score = state["proposed_score"]
        score_to_rating = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}
        rating = score_to_rating[score]
        await query.edit_message_text(f"✅ Accepted rating: {score}/4")

    elif data.startswith("override_"):
        score = int(data.split("_")[1])
        score_to_rating = {1: Rating.Again, 2: Rating.Hard, 3: Rating.Good, 4: Rating.Easy}
        rating = score_to_rating[score]
        await query.edit_message_text(f"✏️ Overridden to: {score}/4")

    else:
        return

    # Capture current item BEFORE submitting (submit advances the index)
    current = state["session"].current_item()
    if current:
        state["results"].append({
            "lesson_id": current.lesson_id,
            "score": score,
            "level": state["level"] or 1,
        })
    if state["question"]:
        state["questions"].append(state["question"]["question"])

    # Submit rating, save state, clear session fields
    session.submit_rating(rating)
    save_review_state(state["manager"], REVIEW_STATE_PATH)

    state["question"] = None
    state["content"] = None
    state["level"] = None
    state["proposed_score"] = None

    await send_next_question(update, context)


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /skip command — skip current question."""
    user_id = update.effective_user.id
    state = user_sessions.get(user_id)

    if state is None:
        await update.message.reply_text("No active session.")
        return

    session = state["session"]

    # Capture before submitting
    current = session.current_item()
    if current:
        state["results"].append({
            "lesson_id": current.lesson_id,
            "score": 1,
            "level": state["level"] or 1,
        })
    if state["question"]:
        state["questions"].append(state["question"]["question"])

    session.submit_rating(Rating.Again)
    save_review_state(state["manager"], REVIEW_STATE_PATH)

    state["question"] = None
    state["content"] = None
    state["level"] = None
    state["proposed_score"] = None

    await update.message.reply_text("⏭️ Skipped. Rated as Again.")
    await send_next_question(update, context)


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /stop command — end session early."""
    user_id = update.effective_user.id
    state = user_sessions.get(user_id)

    if state is None:
        await update.message.reply_text("No active session.")
        return

    await end_session(update, context)


async def end_session(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """End the current session, save state, show summary."""
    user_id = update.effective_user.id if update.effective_user else update.callback_query.from_user.id
    state = user_sessions.get(user_id)

    if state is None:
        return

    session = state["session"]
    save_review_state(state["manager"], REVIEW_STATE_PATH)

    # Submit proofs to blockchain
    if state["results"]:
        await send_message(update, f"Submitting {len(state['results'])} proofs to Ethereum (this may take a minute)...")
        try:
            tx_hashes = bridge.submit_session_proofs(state["results"], state["questions"])
            proof_word = "proof" if len(tx_hashes) == 1 else "proofs"
            await send_message(update, f"✅ {len(tx_hashes)} {proof_word} recorded on-chain!")
        except Exception as e:
            await send_message(update, f"⚠️ Blockchain submission failed: {e}")

    summary = session.summary()

    await send_message(
        update,
        f"🏁 Session Complete!\n\n"
        f"Reviewed: {summary['total_reviewed']}\n"
        f"Duration: {summary['duration_seconds']}s\n"
        f"Ratings: {summary['ratings']}\n"
        f"On-chain proofs: {len(state.get('results', []))}\n\n"
        f"Use /review to start another session."
    )

    del user_sessions[user_id]


async def send_message(update: Update, text: str, reply_markup=None) -> None:
    """Send a message whether triggered by a message or a button press."""
    if update.message:
        await update.message.reply_text(text, reply_markup=reply_markup)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text, reply_markup=reply_markup)


def main() -> None:
    """Start the Telegram bot."""
    global generator, assessor, bridge

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

    generator = QuestionGenerator()
    assessor = AnswerAssessor()
    bridge = BlockchainBridge()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))
    app.add_handler(CallbackQueryHandler(handle_button))

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()