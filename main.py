import asyncio
import logging
import sys
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

from config import BOT_TOKEN
from database.db import init_db
from handlers import admin, student

# Loglashni sozlash
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)


async def health_check(request):
    return web.Response(text="Telegram Bot is running 24/7 on Render!")


async def start_web_server():
    """Render.com da bot bepul veb-servis sifatida ishlashi uchun port tinglovchi server"""
    port_str = os.getenv("PORT", "").strip()
    if port_str and port_str.isdigit():
        port = int(port_str)
        app = web.Application()
        app.router.add_get("/", health_check)
        app.router.add_get("/health", health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Render veb-serveri {port}-portda muvaffaqiyatli ishga tushirildi.")


async def main():
    if not BOT_TOKEN or BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error(
            "\n" + "=" * 60 + "\n"
            "DIQQAT: BOT_TOKEN o'rnatilmagan!\n"
            "Iltimos, '.env' faylida BOT_TOKEN ni o'zingizning Telegram bot tokeningizga almashtiring.\n"
            "Tokenni @BotFather orqali olishingiz mumkin.\n"
            + "=" * 60
        )
        return

    # Ma'lumotlar bazasini ishga tushirish
    await init_db()
    logger.info("Ma'lumotlar bazasi tayyorlandi.")

    # Render serverini ishga tushirish (agar PORT berilgan bo'lsa)
    await start_web_server()

    # Bot va Dispatcherni yaratish
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Handler routerlarini ulash
    dp.include_router(admin.router)
    dp.include_router(student.router)

    logger.info("Bot ishga tushdi va xabarlarni kutmoqda...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
