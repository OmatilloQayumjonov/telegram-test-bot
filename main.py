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
    return web.Response(text="Telegram Bot is running 24/7 on Render! OK")


async def start_web_server():
    """Render.com da bot bepul veb-servis sifatida ishlashi uchun port tinglovchi server"""
    port_str = os.getenv("PORT", "10000").strip()
    port = int(port_str) if port_str.isdigit() else 10000
    try:
        app = web.Application()
        app.router.add_get("/", health_check)
        app.router.add_get("/health", health_check)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", port)
        await site.start()
        logger.info(f"Render veb-serveri 0.0.0.0:{port} da muvaffaqiyatli ishga tushirildi.")
    except Exception as e:
        logger.warning(f"Veb-serverni ishga tushirishda xatolik (mahalliy rejim bo'lishi mumkin): {e}")


async def keep_alive_worker():
    """Render.com 15 daqiqada uxlab qolmasligi uchun o'ziga har 8 daqiqada ping yuboradi"""
    await asyncio.sleep(20)  # Server to'liq ko'tarilishini kutish
    external_url = os.getenv("RENDER_EXTERNAL_URL", "").strip()
    if not external_url:
        logger.info("RENDER_EXTERNAL_URL topilmadi. Mahalliy rejimda keep-alive kerak emas.")
        return

    ping_url = f"{external_url.rstrip('/')}/health"
    logger.info(f"Avtomatik 24/7 Keep-Alive yoqildi: {ping_url}")

    import aiohttp
    while True:
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(ping_url) as resp:
                    logger.info(f"Keep-Alive ping muvaffaqiyatli: Status {resp.status}")
        except Exception as e:
            logger.warning(f"Keep-Alive ping ogohlantirishi: {e}")
        # Render 15 daqiqa (900 soniya) harakatsizlikdan so'ng uxlaydi. Biz har 8 daqiqada (480 s) uyg'otib turamiz:
        await asyncio.sleep(480)


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

    # Render serverini birinchi bo'lib ochish (Render kutib qolmasligi uchun)
    await start_web_server()

    # Ma'lumotlar bazasini ishga tushirish
    await init_db()
    logger.info("Ma'lumotlar bazasi tayyorlandi.")

    # 24/7 Keep-Alive fon jarayonini boshlash
    asyncio.create_task(keep_alive_worker())

    # Bot va Dispatcherni yaratish
    bot = Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML)
    )
    dp = Dispatcher(storage=MemoryStorage())

    # Test vaqtida pastki tugmalar bosilganda testni kelgan joyidan davom ettiruvchi himoya
    dp.message.outer_middleware(student.InTestProtectionMiddleware())

    # Handler routerlarini ulash
    dp.include_router(admin.router)
    dp.include_router(student.router)

    try:
        bot_user = await bot.get_me()
        logger.info(f"Bot muvaffaqiyatli ishga tushdi: @{bot_user.username}")
    except Exception as e:
        logger.warning(f"Bot ma'lumotlarini olishda ogohlantirish: {e}")

    logger.info("Bot xabarlarni qabul qilishga tayyor...")

    # Uzluksiz 24/7 tiklanuvchi Polling sikli
    while True:
        try:
            await dp.start_polling(bot, drop_pending_updates=True, handle_signals=False)
        except (KeyboardInterrupt, SystemExit):
            logger.info("Bot qo'lda to'xtatildi.")
            break
        except Exception as e:
            logger.error(f"Polling uzilishi yuz berdi: {e}")
            logger.info("5 soniyadan so'ng avtomatik qayta ulanadi...")
            await asyncio.sleep(5)
        finally:
            await asyncio.sleep(1)

    await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot to'xtatildi.")
