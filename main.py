from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes, JobQueue, CallbackQueryHandler,
)

from config import TELEGRAM_BOT_TOKEN, logger
from services import BotHandler


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"Исключение при обработке обновления: {context.error}", exc_info=context.error)

    if update and hasattr(update, 'effective_chat'):
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="❌ Произошла ошибка. Попробуйте начать заново командой /start"
            )
        except Exception as e:
            logger.error(f"Ошибка отправки: {e}")


def main():
    if not TELEGRAM_BOT_TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN нет в .env ")
        return

    logger.info("🔧 Инициализация bot...")

    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .job_queue(JobQueue())  # <-- ЭТО ВАЖНО
        .build()
    )

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    handler = BotHandler()

    app.add_handler(CallbackQueryHandler(handler.handle_callback))

    app.add_handler(CommandHandler("start", handler.start_command))

    app.add_handler(MessageHandler(
        filters.PHOTO & ~filters.COMMAND,
        handler.handle_photo
    ))

    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handler.handle_text
    ))
    app.add_error_handler(error_handler)

    logger.info("✅ Bot initialized successfully")
    logger.info(f"🔑 Token: {TELEGRAM_BOT_TOKEN[:10]}...")

    app.run_polling(
        allowed_updates=Update.ALL_TYPES,
        drop_pending_updates=True,
        timeout=30,
        read_timeout=30,
        write_timeout=30,
        connect_timeout=30,
        pool_timeout=30,
    )


if __name__ == "__main__":
    main()