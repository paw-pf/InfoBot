from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters

from config import TELEGRAM_BOT_TOKEN, logger
from services import BotHandler


def main():
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not set in .env file")
        return

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    handler = BotHandler()

    app.add_handler(CommandHandler("start", handler.start_command))
    app.add_handler(MessageHandler(filters.PHOTO, handler.handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handler.handle_text))

    # Start the bot
    logger.info("🤖 Bot is starting...")
    logger.info(f"📋 Report Chat ID: {TELEGRAM_BOT_TOKEN[:10]}...")
    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=30,
        read_timeout=30,
    )


if __name__ == "__main__":
    main()
