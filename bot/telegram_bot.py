"""
Telegram Bot for the Smart Repetition Agent.

Usage:
    python -m bot.telegram_bot
"""

import os
import logging
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

from agent.src.scheduler.review import (
    SchedulerManager, ReviewSession, Rating,
    save_review_state, load_review_state
)
from agent.src.course_parser.models import load_courses_from_json
from agent.src.ai.prompt_builder import get_consolidation_level
from agent.src.retrieval.store import load_or_build
from agent.src.scheduler.dialogue_rating import rate_dialogue
from agent.graph.telegram_dialogue import start_dialogue, submit_answer
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
VAULT_INDEX_DIR = "data/vault_index"


# --- Shared State ---
user_sessions = {}
bridge = None


def setup() -> SchedulerManager:
    """Load courses, restore saved state, return ready manager."""
    courses = load_courses_from_json(COURSES_PATH)
    manager = SchedulerManager()
    load_review_state(manager, REVIEW_STATE_PATH)
    manager.create_items_from_courses(courses)
    return manager


def load_lesson_content(lesson_name: str) -> str:
    """Find a lesson's real content by exact name, via the vault's semantic index."""
    index = load_or_build(VAULT_INDEX_DIR, COURSES_PATH)
    return index.get_lesson_content(lesson_name)


# --- Command Handlers ---

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    await update.message.reply_text(
        "Welcome to Smart Repetition Agent!\n\n"
        "Commands:\n"
        "/review - Start a review session\n"
        "/status - Show what's due\n"
        "/skip - Skip current question\n"
        "/stop - End session early\n\n"
        "Don't know an answer? Just say so (\"I don't know\") and I'll teach it properly, "
        "for as long as you need - say when you're ready to continue."
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
        "thread_id": None,
        "is_first_question_this_lesson": True,
        "results": [],
        "questions": [],
    }

    await update.message.reply_text(
        f"📚 Review session started!\n"
        f"Cards to review: {len(session.queue)}\n\n"
        f"Generating first question..."
    )

    await start_next_lesson(update, context)


async def start_next_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Begin the adaptive dialogue for the next due lesson in the queue."""
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
        await start_next_lesson(update, context)
        return

    level = get_consolidation_level(item)
    state["thread_id"] = f"{user_id}:{item.lesson_id}"
    state["is_first_question_this_lesson"] = True

    result = start_dialogue(state["thread_id"], item.lesson_id, item.lesson_name, content, level)
    await show_question(update, context, state, item, result)


async def show_question(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, item, result: dict) -> None:
    """Send whichever question the dialogue graph just paused on."""
    card_num = state["session"].stats.total_reviewed + 1
    total = len(state["session"].queue)

    if state["is_first_question_this_lesson"]:
        header = f"📝 Card {card_num}/{total} — Level {result['level']}/4\n📖 {item.lesson_name}\n📂 {item.chapter}\n\n"
    else:
        header = f"🔁 That was a bit fuzzy — let's try an easier angle on the same lesson (Level {result['level']}/4)\n\n"
    state["is_first_question_this_lesson"] = False

    await send_message(
        update,
        f"{header}❓ {result['question']}\n\n💡 Hint: {result['hint']}\n\n"
        f"Type your answer, say you don't know to be taught, or use /skip"
    )


async def show_explanation(update: Update, context: ContextTypes.DEFAULT_TYPE, result: dict) -> None:
    """Send the tutor's explanation and invite a follow-up or a 'ready to continue'."""
    await send_message(
        update,
        f"{result['text']}\n\nAsk anything else about this, or say you're ready to continue."
    )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle a text message as an answer to the current question, or a reply within an explanation."""
    user_id = update.effective_user.id
    state = user_sessions.get(user_id)

    if state is None or state.get("thread_id") is None:
        await update.message.reply_text("No active question. Use /review to start a session.")
        return

    await update.message.reply_text("🔍 One moment...")

    result = submit_answer(state["thread_id"], update.message.text)

    if result["kind"] == "question":
        item = state["session"].current_item()
        await show_question(update, context, state, item, result)
        return

    if result["kind"] == "explanation":
        await show_explanation(update, context, result)
        return

    await finish_lesson(update, context, state, result)


async def finish_lesson(update: Update, context: ContextTypes.DEFAULT_TYPE, state: dict, result: dict) -> None:
    """The dialogue for this lesson is done - rate it, record it, move on."""
    session = state["session"]
    item = session.current_item()

    rated = rate_dialogue(result["transcript"])
    session.submit_rating(rated["rating"])
    save_review_state(state["manager"], REVIEW_STATE_PATH)

    state["results"].append({"lesson_id": item.lesson_id, "score": rated["score"], "level": rated["level"]})
    state["questions"].extend(entry["question"] for entry in result["transcript"])
    state["thread_id"] = None

    outcome_emoji = "✅" if result["outcome"] == "solid" else "🟠"
    attempts_note = f" ({rated['attempts']} attempts)" if rated["attempts"] > 1 else ""
    await send_message(
        update,
        f"{outcome_emoji} {result['outcome']}{attempts_note} — recorded as {rated['score']}/4 at level {rated['level']}/4"
    )

    await start_next_lesson(update, context)


async def cmd_skip(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /skip command — skip current question."""
    user_id = update.effective_user.id
    state = user_sessions.get(user_id)

    if state is None or state.get("thread_id") is None:
        await update.message.reply_text("No active question.")
        return

    session = state["session"]
    item = session.current_item()

    state["results"].append({"lesson_id": item.lesson_id, "score": 1, "level": 1})
    session.submit_rating(Rating.Again)
    save_review_state(state["manager"], REVIEW_STATE_PATH)
    state["thread_id"] = None

    await update.message.reply_text("⏭️ Skipped. Rated as Again.")
    await start_next_lesson(update, context)


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
            # Pass the Telegram user id so each learner's proofs land on their
            # own on-chain identifier rather than all collapsing onto the
            # relayer wallet.
            tx_hashes = bridge.submit_session_proofs(
                state["results"], state["questions"], user_id=str(user_id)
            )
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


async def send_message(update: Update, text: str) -> None:
    """Send a message whether triggered by a message or a button press."""
    if update.message:
        await update.message.reply_text(text)
    elif update.callback_query:
        await update.callback_query.message.reply_text(text)


def main() -> None:
    """Start the Telegram bot."""
    global bridge

    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN environment variable not set")

    bridge = BlockchainBridge()

    app = Application.builder().token(token).build()

    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("review", cmd_review))
    app.add_handler(CommandHandler("skip", cmd_skip))
    app.add_handler(CommandHandler("stop", cmd_stop))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_answer))

    logger.info("Bot started. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
