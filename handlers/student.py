import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command, CommandStart, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.exceptions import TelegramBadRequest

from config import ADMIN_IDS
from database import db
from keyboards import get_admin_reply_keyboard, get_student_reply_keyboard
from datetime import datetime
import time
import html
import urllib.parse

router = Router()

# Har bir talaba uchun faol jonli taymerlar: user_id -> asyncio.Task
active_timers: dict[int, asyncio.Task] = {}

# Aylanuvchi soat emojilari ketma-ketligi
CLOCK_ICONS = ["🕛", "🕐", "🕑", "🕒", "🕓", "🕔", "🕕", "🕖", "🕗", "🕘", "🕙", "🕚"]


def stop_timer(chat_id: int):
    task = active_timers.pop(chat_id, None)
    if task and not task.done():
        task.cancel()


class StudentRegistrationState(StatesGroup):
    waiting_for_name = State()
    editing_name = State()


class TeacherPaymentState(StatesGroup):
    waiting_for_receipt = State()


class TestSessionState(StatesGroup):
    in_test = State()
    confirm_finish = State()


def get_grade(percent: float) -> str:
    if percent >= 86:
        return "A'lo (5)"
    elif percent >= 71:
        return "Yaxshi (4)"
    elif percent >= 56:
        return "Qoniqarli (3)"
    else:
        return "Qoniqarsiz (2)"


async def show_test_welcome(message: Message, test: dict, user_id: int):
    """Maxsus havola orqali kirgan talabaga testni tanishtirish va boshlash oynasi"""
    test_id = test["id"]
    questions = await db.get_test_questions(test_id)
    t_limit = test.get("time_limit_minutes", 15) or 15
    time_limit_str = f"{t_limit} daqiqa" if t_limit > 0 else "Cheklovsiz"

    safe_title = html.escape(test['title'])
    text = (
        f"🎯 <b>Testga taklif etildingiz!</b>\n\n"
        f"📝 <b>Test:</b> {safe_title}\n"
        f"🔢 <b>Savollar soni:</b> {len(questions)} ta\n"
        f"⏱ <b>Ajratilgan vaqt:</b> {time_limit_str}\n\n"
        f"🔒 <b>Himoya va Qoidalar:</b>\n"
        f"• Savollardan nusxa ko'chirish va ulashish taqiqlanadi (Telegram himoyasi yoqilgan).\n"
        f"• Oldingi va keyingi savollarga bemalol qaytishingiz va javobni o'zgartirishingiz mumkin.\n"
        f"• Vaqt jonli aylanuvchi soat bilan ko'rsatiladi.\n\n"
        f"Testni boshlashga tayyormisiz?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Testni boshlash", callback_data=f"launch_test_{test_id}")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="student_menu")]
    ])

    reply_kb = get_admin_reply_keyboard() if (user_id in ADMIN_IDS) else get_student_reply_keyboard()
    await message.answer("Test ma'lumotlari:", reply_markup=reply_kb)
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    stop_timer(message.from_user.id)
    await state.clear()
    user_id = message.from_user.id

    user = await db.get_user(user_id)
    if not user:
        full_name = message.from_user.full_name or "Foydalanuvchi"
        await db.save_or_update_user(user_id, full_name, message.from_user.username)
        user = {"full_name": full_name, "user_id": user_id}

    # Maxsus havola orqali kelinganmi? (Masalan: /start test_5)
    args = command.args
    if args and args.startswith("test_"):
        try:
            target_test_id = int(args.replace("test_", ""))
            test = await db.get_test_by_id(target_test_id)
            if test and test.get("is_active") == 1:
                # Talabaga ushbu testga kirish ruxsatini berish
                await db.grant_student_access_to_test(user_id, target_test_id)

                # Agar talabaning ismi to'liq bo'lmasa yoki "Foydalanuvchi" bo'lsa
                name_parts = user["full_name"].strip().split()
                if len(name_parts) < 2 or user["full_name"] == "Foydalanuvchi":
                    await state.set_state(StudentRegistrationState.waiting_for_name)
                    await state.update_data(pending_test_id=target_test_id)
                    safe_test_title = html.escape(test['title'])
                    await message.answer(
                        f"👋 Assalomu alaykum!\n\n"
                        f"Siz <b>«{safe_test_title}»</b> testiga kirdingiz.\n\n"
                        f"Natijangiz o'qituvchiga to'liq va to'g'ri ko'rinishi uchun, iltimos, <b>ism va familiyangizni</b> kiriting:\n"
                        f"<i>(Masalan: Karimov Jasur)</i>",
                        parse_mode="HTML"
                    )
                    return
                else:
                    await show_test_welcome(message, test, user_id)
                    return
            else:
                await message.answer(
                    "⚠️ Ushbu test mavjud emas yoki o'qituvchi tomonidan to'xtatilgan.",
                    reply_markup=get_student_reply_keyboard()
                )
        except Exception:
            pass

    await show_main_menu(message, user["full_name"], user_id)


@router.message(StudentRegistrationState.waiting_for_name)
async def process_name(message: Message, state: FSMContext):
    full_name = message.text.strip() if message.text else ""
    parts = full_name.split()

    if len(parts) < 2 or len(full_name) < 4:
        await message.answer(
            "⚠️ Iltimos, ism va familiyangizni to'liq kiriting!\n"
            "Masalan: <i>Karimov Jasur</i>",
            parse_mode="HTML"
        )
        return

    username = message.from_user.username
    await db.save_or_update_user(
        user_id=message.from_user.id,
        full_name=full_name,
        username=username
    )

    data = await state.get_data()
    pending_test_id = data.get("pending_test_id")
    await state.clear()

    safe_name = html.escape(full_name)
    await message.answer(f"✅ Rahmat, <b>{safe_name}</b>! Ma'lumotlaringiz saqlandi.", parse_mode="HTML")

    if pending_test_id:
        test = await db.get_test_by_id(pending_test_id)
        if test and test.get("is_active") == 1:
            await show_test_welcome(message, test, message.from_user.id)
            return

    await show_main_menu(message, full_name, message.from_user.id)


# ==============================================================================
# 🔘 PASTKI DOIMIY TUGMALAR HANDLERLARI (REPLY KEYBOARD)
# ==============================================================================

@router.message(F.text == "📝 Mavjud Testlar")
async def msg_available_tests(message: Message, state: FSMContext):
    stop_timer(message.from_user.id)
    await state.clear()
    user = await db.get_user(message.from_user.id)
    name = user["full_name"] if user else message.from_user.full_name
    await show_main_menu(message, name, message.from_user.id)


@router.message(F.text == "🔗 Test havolalari")
async def msg_test_links(message: Message, state: FSMContext, bot: Bot):
    await state.clear()
    user_id = message.from_user.id
    tests = await db.get_tests_by_author(user_id)

    if not tests:
        await message.answer(
            "📋 <b>Sizda hozircha yaratilgan testlar mavjud emas.</b>\n\n"
            "Yangi test yuklash uchun quyidagi <b>👨‍🏫 O'qituvchi bo'limi</b> ➡️ <b>📥 Yangi test yuklash</b> tugmasini bosing.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Yangi test yuklash (.docx)", callback_data="teacher_upload_test")]
            ]),
            parse_mode="HTML"
        )
        return

    bot_user = await bot.get_me()
    bot_username = bot_user.username

    text = "🔗 <b>Siz yaratgan testlar va ularning talabalar uchun maxsus havolalari:</b>\n\n"
    kb_rows = []

    for idx, t in enumerate(tests, start=1):
        t_id = t["id"]
        safe_title = html.escape(t["title"])
        test_link = f"https://t.me/{bot_username}?start=test_{t_id}"
        share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{t['title']}' testini ishlash uchun havola:")

        text += (
            f"📌 <b>{idx}. {safe_title}</b> ({t['question_count']} ta savol)\n"
            f"🔗 <b>Maxsus havola:</b>\n"
            f"<code>{test_link}</code>\n\n"
        )
        kb_rows.append([
            InlineKeyboardButton(text=f"📤 {idx}-testni ulashish (Share)", url=share_url)
        ])
        kb_rows.append([
            InlineKeyboardButton(text=f"📊 {idx}-test natijalari va Excel", callback_data=f"test_report_{t_id}"),
            InlineKeyboardButton(text=f"⚙️ Sozlamalar", callback_data=f"admin_test_{t_id}")
        ])

    text += "<i>💡 Havolani nusxalab talabalaringizga yuboring yoki 'Ulashish' tugmasi orqali to'g'ridan-to'g'ri Telegram guruhiga tashlang!</i>"

    await message.answer(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        parse_mode="HTML",
        disable_web_page_preview=True
    )


@router.message(Command("teacher"))
@router.message(F.text == "👨‍🏫 O'qituvchi bo'limi")
async def msg_teacher_cabinet(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    t_info = await db.get_teacher(user_id)
    can_upload, reason, info = await db.can_teacher_create_test(user_id)

    created = t_info.get("tests_created", 0)
    sub_until = t_info.get("subscription_until")

    if user_id in ADMIN_IDS or t_info.get("is_unlimited") == 1:
        status_line = "👑 <b>Superadmin:</b> Cheklovsiz test yuklash imkoniyati"
    elif sub_until and datetime.strptime(sub_until, "%Y-%m-%d %H:%M:%S") > datetime.now():
        status_line = f"🟢 <b>Faol obuna:</b> <b>{sub_until}</b> gacha cheklovsiz"
    else:
        status_line = f"📊 <b>Bepul urinishlar:</b> {created} / 3 ta ishlatildi"

    text = (
        "👨‍🏫 <b>O'qituvchi Kabineti</b>\n\n"
        f"{status_line}\n\n"
        "Ushbu bo'lim orqali siz o'z testlaringizni Word (.docx) formatda botga yuklashingiz, "
        "natijalarni Excel formatida yuklab olishingiz va talabalaringizni baholashingiz mumkin."
    )

    kb_rows = [
        [InlineKeyboardButton(text="📥 Yangi test yuklash (.docx)", callback_data="teacher_upload_test")],
        [InlineKeyboardButton(text="📋 Mening testlarim va Natijalar", callback_data="admin_list_tests")],
        [InlineKeyboardButton(text="🔗 Barcha testlarim havolalari", callback_data="teacher_all_links")],
        [InlineKeyboardButton(text="💳 Obuna sotib olish / uzaytirish", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="📄 Namunaviy Word fayl", callback_data="admin_get_sample")]
    ]

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@router.message(F.text == "💳 Obuna sotib olish")
async def msg_buy_subscription(message: Message, state: FSMContext):
    await state.clear()
    price_m = await db.get_setting("price_month", "30000")
    price_y = await db.get_setting("price_year", "250000")

    text = (
        "💳 <b>Obuna tarifini tanlang:</b>\n\n"
        "Obuna sizga barcha imkoniyatlarni cheklovsiz ochib beradi:\n"
        "• Xohlagancha testlar yuklash\n"
        "• Cheklovsiz talabalardan test qabul qilish\n"
        "• Nusxa ko'chirish va skrinshotdan to'liq himoya\n"
        "• Barcha natijalarni Excel jadvalida yuklab olish\n\n"
        f"1️⃣ <b>1 oylik obuna:</b> <b>{price_m} so'm</b>\n"
        f"2️⃣ <b>1 yillik obuna:</b> <b>{price_y} so'm</b>\n\n"
        "Qaysi tarifni tanlaysiz?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 1 oylik obuna ({price_m} so'm)", callback_data="subplan_month")],
        [InlineKeyboardButton(text=f"💳 1 yillik obuna ({price_y} so'm)", callback_data="subplan_year")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="teacher_cabinet")]
    ])

    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(F.text == "✏️ Ismni o'zgartirish")
@router.callback_query(F.data == "edit_my_name")
async def cb_edit_my_name(event: Message | CallbackQuery, state: FSMContext):
    await state.set_state(StudentRegistrationState.editing_name)
    target = event.message if isinstance(event, CallbackQuery) else event

    text = (
        "✏️ <b>Yangi ism va familiyangizni kiriting:</b>\n"
        "(Masalan: <i>Aliyev Vali</i>)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="student_menu")]
    ])

    if isinstance(event, CallbackQuery):
        await target.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await target.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(StudentRegistrationState.editing_name)
async def process_edit_name(message: Message, state: FSMContext):
    new_name = message.text.strip() if message.text else ""
    parts = new_name.split()

    if len(parts) < 2 or len(new_name) < 4:
        await message.answer(
            "⚠️ Iltimos, ism va familiyangizni to'liq kiriting!\n"
            "Masalan: <i>Karimov Jasur</i>",
            parse_mode="HTML"
        )
        return

    await db.update_user_name(message.from_user.id, new_name)
    await state.clear()
    safe_name = html.escape(new_name)
    await message.answer(f"✅ Ismingiz muvaffaqiyatli o'zgartirildi: <b>{safe_name}</b>", parse_mode="HTML")
    await show_main_menu(message, new_name, message.from_user.id)


async def show_main_menu(message: Message, full_name: str, user_id: int):
    # Faqat foydalanuvchiga tegishli testlar (o'zi yaratgan yoki havola orqali biriktirilgan)
    tests = await db.get_student_accessible_tests(user_id)
    safe_name = html.escape(full_name)

    is_adm = user_id in ADMIN_IDS or len(ADMIN_IDS) == 0
    reply_kb = get_admin_reply_keyboard() if is_adm else get_student_reply_keyboard()

    bot_username = "TestIshlaTest_bot"
    try:
        bot_user = await message.bot.get_me()
        bot_username = bot_user.username
    except Exception:
        pass

    kb_rows = []
    if tests:
        tests_intro = "📋 <b>Sizning faol testlaringiz va havolalari:</b>\n\n"
        for idx, t in enumerate(tests, start=1):
            t_limit = t.get("time_limit_minutes", 15) or 15
            time_tag = f"{t_limit} daq" if t_limit > 0 else "Cheklovsiz"
            btn_text = f"📝 {t['title']} ({t['question_count']} ta, {time_tag})"
            kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"start_test_{t['id']}")])

            test_link = f"https://t.me/{bot_username}?start=test_{t['id']}"
            if t.get("author_id") == user_id or is_adm:
                tests_intro += (
                    f"📌 <b>{idx}. {t['title']}</b> ({t['question_count']} ta savol)\n"
                    f"🔗 <b>Talabalarga havola:</b> <code>{test_link}</code>\n\n"
                )
            else:
                tests_intro += f"📌 <b>{idx}. {t['title']}</b> ({t['question_count']} ta savol, {time_tag})\n\n"

        tests_intro += "<i>💡 Test ustiga bosib uni boshqarishingiz yoki havolani nusxalab talabalarga yuborishingiz mumkin.</i>"
    else:
        tests_intro = (
            "ℹ️ <b>Sizda hozircha biriktirilgan testlar yo'q.</b>\n\n"
            "• Yangi test yaratish uchun: <b>👨‍🏫 O'qituvchi bo'limi</b> tugmasini bosing.\n"
            "• Test topshirish uchun: O'qituvchingiz yuborgan <b>maxsus havola</b> orqali kiring."
        )

    kb_rows.append([InlineKeyboardButton(text="📊 Excel hisobotlar va Reyting", callback_data="admin_export_excel")])
    kb_rows.append([InlineKeyboardButton(text="🔗 Barcha testlarim havolalari", callback_data="teacher_all_links")])
    kb_rows.append([InlineKeyboardButton(text="👨‍🏫 O'qituvchi bo'limi (Test yaratish)", callback_data="teacher_cabinet")])
    kb_rows.append([InlineKeyboardButton(text="✏️ Ism-familiyani o'zgartirish", callback_data="edit_my_name")])

    inline_kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)

    await message.answer(
        f"👤 Profil: <b>{safe_name}</b>\n\n{tests_intro}",
        reply_markup=reply_kb,
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await message.answer(
        "📋 <b>Menyu va Testlar:</b>",
        reply_markup=inline_kb,
        parse_mode="HTML"
    )


# ==============================================================================
# 👨‍🏫 O'QITUVCHI BO'LIMI CALLBACKLARI
# ==============================================================================

@router.callback_query(F.data == "teacher_cabinet")
async def cb_teacher_cabinet(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    t_info = await db.get_teacher(user_id)

    created = t_info.get("tests_created", 0)
    sub_until = t_info.get("subscription_until")

    if user_id in ADMIN_IDS or t_info.get("is_unlimited") == 1:
        status_line = "👑 <b>Superadmin:</b> Cheklovsiz test yuklash imkoniyati"
    elif sub_until and datetime.strptime(sub_until, "%Y-%m-%d %H:%M:%S") > datetime.now():
        status_line = f"🟢 <b>Faol obuna:</b> <b>{sub_until}</b> gacha cheklovsiz"
    else:
        status_line = f"📊 <b>Bepul urinishlar:</b> {created} / 3 ta ishlatildi"

    text = (
        "👨‍🏫 <b>O'qituvchi Kabineti</b>\n\n"
        f"{status_line}\n\n"
        "Ushbu bo'lim orqali siz o'z testlaringizni Word (.docx) formatda botga yuklashingiz, "
        "natijalarni Excel formatida yuklab olishingiz va talabalaringizni baholashingiz mumkin."
    )

    kb_rows = [
        [InlineKeyboardButton(text="📥 Yangi test yuklash (.docx)", callback_data="teacher_upload_test")],
        [InlineKeyboardButton(text="📋 Mening testlarim va Natijalar", callback_data="admin_list_tests")],
        [InlineKeyboardButton(text="📊 Excel hisobotlar va Reyting", callback_data="admin_export_excel")],
        [InlineKeyboardButton(text="🔗 Barcha testlarim havolalari", callback_data="teacher_all_links")],
        [InlineKeyboardButton(text="💳 Obuna sotib olish / uzaytirish", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="📄 Namunaviy Word fayl", callback_data="admin_get_sample")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="student_menu")]
    ]

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "teacher_all_links")
async def cb_teacher_all_links(callback: CallbackQuery):
    user_id = callback.from_user.id
    tests = await db.get_tests_by_author(user_id)

    if not tests:
        await callback.message.edit_text(
            "📋 Hozirda siz yaratgan testlar mavjud emas.\n\n"
            "Yangi test yuklaganingizdan so'ng, uning talabalar uchun maxsus havolasi shu yerda chiqadi.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Yangi test yuklash", callback_data="teacher_upload_test")],
                [InlineKeyboardButton(text="🔙 Orqaga", callback_data="teacher_cabinet")]
            ]),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    bot_user = await callback.bot.get_me()
    bot_username = bot_user.username

    text = "🔗 <b>Sizning barcha testlaringiz uchun maxsus havolalar:</b>\n\n"
    kb_rows = []

    for idx, t in enumerate(tests, start=1):
        t_id = t["id"]
        safe_title = html.escape(t["title"])
        test_link = f"https://t.me/{bot_username}?start=test_{t_id}"
        share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{t['title']}' testini ishlash uchun havola:")

        text += (
            f"📌 <b>{idx}. {safe_title}</b> ({t['question_count']} ta savol)\n"
            f"🔗 Havola: <code>{test_link}</code>\n\n"
        )
        kb_rows.append([
            InlineKeyboardButton(text=f"📤 {idx}-testni ulashish (Share)", url=share_url)
        ])
        kb_rows.append([
            InlineKeyboardButton(text=f"📊 {idx}-test natijalari va Excel", callback_data=f"test_report_{t_id}"),
            InlineKeyboardButton(text=f"⚙️ Sozlamalar", callback_data=f"admin_test_{t_id}")
        ])

    kb_rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data="teacher_cabinet")])

    await callback.message.edit_text(
        text + "<i>💡 Talabalarga yuborish uchun havola ustiga bosib nusxalang yoki 'Ulashish' tugmasi orqali to'g'ridan-to'g'ri guruhga yuboring.</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()


@router.callback_query(F.data == "teacher_upload_test")
async def cb_teacher_upload_test(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    can_upload, reason, info = await db.can_teacher_create_test(user_id)

    if not can_upload:
        price_m = await db.get_setting("price_month", "30000")
        price_y = await db.get_setting("price_year", "250000")
        await callback.message.edit_text(
            "⚠️ <b>3 ta bepul test yuklash limitingiz tugadi!</b>\n\n"
            "Yangi testlar yuklash va o'quvchilaringizdan test olishni davom ettirish uchun obuna bo'ling:\n\n"
            f"💳 <b>1 oylik cheklovsiz:</b> {price_m} so'm\n"
            f"💳 <b>1 yillik cheklovsiz:</b> {price_y} so'm\n\n"
            "To'lov Click orqali juda oson va tezkor amalga oshiriladi:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Obunani rasmiylashtirish", callback_data="buy_subscription")],
                [InlineKeyboardButton(text="🔙 Orqaga", callback_data="teacher_cabinet")]
            ]),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    from handlers.admin import AdminState
    await state.set_state(AdminState.waiting_for_docx)
    await callback.message.edit_text(
        "📥 <b>Word (.docx) formatdagi test faylini yuboring:</b>\n\n"
        "• Har bir savol raqam bilan boshlanishi (1. ...)\n"
        "• Variantlar A) B) C) D) ko'rinishida bo'lishi\n"
        "• Har bir savol ostida to'g'ri javob ko'rsatilishi (masalan: <code>Javob: B</code> yoki <code>*B)</code>)\n"
        "• Izoh ko'rsatilishi mumkin (<code>Izoh: ...</code>)\n\n"
        "Faylni yuborishni kutyapman...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Namuna faylni olish", callback_data="admin_get_sample")],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="teacher_cabinet")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


# ==============================================================================
# 💳 CLICK ORQALI OBUNA SOTIB OLISH (1 OYLIK / 1 YILLIK)
# ==============================================================================

@router.callback_query(F.data == "buy_subscription")
async def cb_buy_subscription(callback: CallbackQuery):
    price_m = await db.get_setting("price_month", "30000")
    price_y = await db.get_setting("price_year", "250000")

    text = (
        "💳 <b>Obuna tarifini tanlang:</b>\n\n"
        "Obuna sizga barcha imkoniyatlarni cheklovsiz ochib beradi:\n"
        "• Xohlagancha testlar yuklash\n"
        "• Cheklovsiz talabalardan test qabul qilish\n"
        "• Nusxa ko'chirish va skrinshotdan to'liq himoya\n"
        "• Barcha natijalarni Excel jadvalida yuklab olish\n\n"
        f"1️⃣ <b>1 oylik obuna:</b> <b>{price_m} so'm</b>\n"
        f"2️⃣ <b>1 yillik obuna:</b> <b>{price_y} so'm</b>\n\n"
        "Qaysi tarifni tanlaysiz?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"💳 1 oylik obuna ({price_m} so'm)", callback_data="subplan_month")],
        [InlineKeyboardButton(text=f"💳 1 yillik obuna ({price_y} so'm)", callback_data="subplan_year")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data="teacher_cabinet")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.in_(["subplan_month", "subplan_year"]))
async def cb_select_sub_plan(callback: CallbackQuery, state: FSMContext):
    plan_type = "month" if callback.data == "subplan_month" else "year"
    plan_name = "1 oylik" if plan_type == "month" else "1 yillik"

    price_str = await db.get_setting("price_month" if plan_type == "month" else "price_year", "30000" if plan_type == "month" else "250000")
    amount = int(price_str)
    click_card = await db.get_setting("click_details", "8600 0000 0000 0000 (Click)")

    await state.set_state(TeacherPaymentState.waiting_for_receipt)
    await state.update_data(plan_type=plan_type, amount=amount, plan_name=plan_name)

    text = (
        f"📲 <b>Click orqali to'lov ma'lumotlari:</b>\n\n"
        f"📦 <b>Tarif:</b> <b>{plan_name} cheklovsiz obuna</b>\n"
        f"💰 <b>To'lov summasi:</b> <b>{amount:,} so'm</b>\n"
        f"💳 <b>Click karta / raqam:</b> <code>{click_card}</code>\n\n"
        f"<b>To'lov tartibi:</b>\n"
        f"1. Click ilovangiz orqali yuqoridagi kartaga <b>{amount:,} so'm</b> o'tkazing.\n"
        f"2. To'lov amalga oshirilganini tasdiqlovchi <b>chek rasmini (skrinshot)</b> ushbu botga yuboring.\n\n"
        f"<i>Chek rasmini yuborishingiz bilan u administratorga yuboriladi va obunangiz faollashtiriladi.</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="buy_subscription")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(F.photo, TeacherPaymentState.waiting_for_receipt)
async def process_payment_receipt(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    plan_type = data.get("plan_type", "month")
    amount = data.get("amount", 30000)
    plan_name = data.get("plan_name", "1 oylik")

    photo_id = message.photo[-1].file_id
    user_id = message.from_user.id
    user = await db.get_user(user_id)
    full_name = user["full_name"] if user else message.from_user.full_name
    username = message.from_user.username or "yo'q"

    pay_id = await db.create_payment_request(
        user_id=user_id,
        plan_type=plan_type,
        amount=amount,
        receipt_file_id=photo_id
    )

    await state.clear()

    await message.answer(
        f"✅ <b>To'lov chekingiz muvaffaqiyatli qabul qilindi! (#PAY_{pay_id})</b>\n\n"
        f"📦 <b>Tarif:</b> {plan_name}\n"
        f"💰 <b>Summa:</b> {amount:,} so'm\n\n"
        f"Administrator to'lovni tasdiqlashi bilan obunangiz avtomatik yoqiladi va sizga xabar yuboriladi.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="student_menu")]
        ]),
        parse_mode="HTML"
    )

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    safe_name = html.escape(full_name)
    admin_caption = (
        f"🔔 <b>YANGI TO'LOV SO'ROVI! (#PAY_{pay_id})</b>\n\n"
        f"👤 <b>O'qituvchi:</b> <a href=\"tg://user?id={user_id}\">{safe_name}</a>\n"
        f"📱 <b>Username:</b> @{username}\n"
        f"🆔 <b>Telegram ID:</b> <code>{user_id}</code>\n"
        f"📦 <b>Tarif:</b> <b>{plan_name}</b>\n"
        f"💰 <b>Summa:</b> <b>{amount:,} so'm</b>\n"
        f"📅 <b>Vaqti:</b> {now_str}\n\n"
        f"To'lovni tasdiqlaysizmi?"
    )

    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Tasdiqlash (Obuna berish)", callback_data=f"approve_pay_{pay_id}"),
            InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_pay_{pay_id}")
        ]
    ])

    for admin_id in ADMIN_IDS:
        try:
            await bot.send_photo(
                chat_id=admin_id,
                photo=photo_id,
                caption=admin_caption,
                reply_markup=admin_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass


# ==============================================================================
# 📝 TEST ISHLASH VA AYLANUVCHI SOATLI JONLI TAYMER
# ==============================================================================

@router.callback_query(F.data.startswith("start_test_"))
async def cb_confirm_start_test(callback: CallbackQuery, state: FSMContext):
    user = await db.get_user(callback.from_user.id)
    if not user:
        await callback.message.answer("Avval ro'yxatdan o'tishingiz kerak. /start bosing.")
        await callback.answer()
        return

    test_id = int(callback.data.replace("start_test_", ""))
    test = await db.get_test_by_id(test_id)

    if not test or test["is_active"] != 1:
        await callback.answer("Ushbu test hozirda faol emas.", show_alert=True)
        return

    questions = await db.get_test_questions(test_id)
    if not questions:
        await callback.answer("Ushbu testda savollar mavjud emas.", show_alert=True)
        return

    t_limit = test.get("time_limit_minutes", 15) or 15
    time_limit_str = f"{t_limit} daqiqa" if t_limit > 0 else "Cheklovsiz"
    safe_title = html.escape(test['title'])

    user_id = callback.from_user.id
    bot_user = await callback.bot.get_me()
    bot_username = bot_user.username
    test_link = f"https://t.me/{bot_username}?start=test_{test_id}"
    share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{test['title']}' testini ishlash uchun havola:")

    # Agar ushbu testning muallifi bo'lsa (yoki superadmin) - unga maxsus havola va boshqaruv ko'rsatiladi
    if test["author_id"] == user_id or user_id in ADMIN_IDS:
        text = (
            f"📝 <b>Test:</b> {safe_title}\n"
            f"🔢 <b>Savollar soni:</b> {len(questions)} ta\n"
            f"⏱ <b>Ajratilgan vaqt:</b> {time_limit_str}\n\n"
            f"🔗 <b>Talabalarga yuborish uchun maxsus havola:</b>\n"
            f"<code>{test_link}</code>\n\n"
            f"<i>💡 Talabalar aynan shu havola orqali kirib testni ishlay oladilar. Ushbu havolani nusxalab talabalaringizga yuboring yoki quyidagi ulashish tugmasini bosing:</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Havolani guruhga ulashish (Share)", url=share_url)],
            [InlineKeyboardButton(text="🚀 O'zim sinab ko'rish", callback_data=f"launch_test_{test_id}")],
            [InlineKeyboardButton(text="📊 Excel hisobot va Reyting", callback_data=f"test_report_{test_id}")],
            [InlineKeyboardButton(text="⏱ Vaqtni sozlash", callback_data=f"admin_time_{test_id}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="student_menu")]
        ])
    else:
        # Oddiy talaba uchun testni boshlash oynasi
        text = (
            f"📝 <b>Test:</b> {safe_title}\n"
            f"🔢 <b>Savollar soni:</b> {len(questions)} ta\n"
            f"⏱ <b>Ajratilgan vaqt:</b> {time_limit_str}\n\n"
            f"🔒 <b>Qoidalar va Himoya:</b>\n"
            f"• Savollarni birovga yo'naltirish (forward) va nusxalash taqiqlanadi.\n"
            f"• Skrinshot olish cheklangan.\n"
            f"• Test davomida <b>oldingi va keyingi savollarga qaytishingiz</b> va javoblaringizni o'zgartirishingiz mumkin.\n"
            f"• Vaqt <b>aylanuvchi soat bilan jonli ravishda</b> hisoblab boriladi.\n\n"
            f"Boshlashga tayyormisiz?"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🚀 Testni boshlash", callback_data=f"launch_test_{test_id}")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data="student_menu")]
        ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "student_menu")
async def cb_student_menu(callback: CallbackQuery, state: FSMContext):
    stop_timer(callback.from_user.id)
    await state.clear()
    user = await db.get_user(callback.from_user.id)
    if user:
        await callback.message.delete()
        await show_main_menu(callback.message, user["full_name"], callback.from_user.id)
    else:
        await callback.message.answer("Iltimos, /start bosing.")
    await callback.answer()


@router.callback_query(F.data.startswith("launch_test_"))
async def cb_launch_test(callback: CallbackQuery, state: FSMContext, bot: Bot):
    test_id = int(callback.data.replace("launch_test_", ""))
    user_id = callback.from_user.id

    questions = await db.get_test_questions(test_id)
    test = await db.get_test_by_id(test_id)

    if not questions:
        await callback.answer("Savollar topilmadi", show_alert=True)
        return

    attempt_id = await db.create_attempt(user_id=user_id, test_id=test_id, total=len(questions))

    time_limit_minutes = test.get("time_limit_minutes", 15) or 15
    start_ts = time.time()
    deadline_ts = (start_ts + time_limit_minutes * 60) if time_limit_minutes > 0 else 0

    await state.set_state(TestSessionState.in_test)
    await state.update_data(
        test_id=test_id,
        test_title=test["title"],
        author_id=test.get("author_id", 0),
        attempt_id=attempt_id,
        questions=questions,
        current_index=0,
        total=len(questions),
        answers={},
        time_limit_minutes=time_limit_minutes,
        deadline_ts=deadline_ts,
        msg_id=None
    )

    await callback.message.delete()
    await render_and_send_question(callback.message.chat.id, state, bot, is_new=True)

    if deadline_ts > 0:
        stop_timer(user_id)
        active_timers[user_id] = asyncio.create_task(
            run_student_timer(user_id, state, bot, attempt_id, deadline_ts)
        )

    await callback.answer()


async def run_student_timer(chat_id: int, state: FSMContext, bot: Bot, attempt_id: int, deadline_ts: float):
    """Orqa fonda har 3 soniyada aylanuvchi soatli vaqtni yangilovchi sikl"""
    try:
        while True:
            await asyncio.sleep(3)
            data = await state.get_data()
            if not data or data.get("attempt_id") != attempt_id:
                break

            current_state = await state.get_state()
            if current_state != TestSessionState.in_test.state:
                if time.time() >= deadline_ts:
                    await auto_finish_test(chat_id, state, bot, reason="time_up")
                    break
                continue

            remaining = int(deadline_ts - time.time())
            if remaining <= 0:
                await auto_finish_test(chat_id, state, bot, reason="time_up")
                break

            msg_id = data.get("msg_id")
            if not msg_id:
                continue

            idx = data["current_index"]
            questions = data["questions"]
            total = data["total"]
            answers = data.get("answers", {})

            mins = remaining // 60
            secs = remaining % 60
            clock_icon = CLOCK_ICONS[(remaining // 3) % len(CLOCK_ICONS)]
            header_time = f"{clock_icon} <b>{mins:02d}:{secs:02d}</b>  |  "

            q = questions[idx]
            q_id = q["id"]
            chosen = answers.get(str(q_id), "")

            safe_q = html.escape(q['question_text'])
            safe_a = html.escape(q['option_a'])
            safe_b = html.escape(q['option_b'])
            safe_c = html.escape(q['option_c'])
            safe_d = html.escape(q['option_d'])
            selected_tag = f"\n👉 <i>Siz tanlagan javob: <b>{chosen}</b></i>" if chosen else ""

            text = (
                f"{header_time}❓ <b>{idx + 1}/{total} - Savol:</b>\n\n"
                f"{safe_q}\n\n"
                f"<b>A)</b> {safe_a}\n"
                f"<b>B)</b> {safe_b}\n"
                f"<b>C)</b> {safe_c}\n"
                f"<b>D)</b> {safe_d}"
                f"{selected_tag}"
            )
            kb = build_question_keyboard(q_id, idx, total, chosen, len(answers))

            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=text,
                    reply_markup=kb,
                    parse_mode="HTML"
                )
            except TelegramBadRequest:
                pass
            except Exception:
                pass

    except asyncio.CancelledError:
        pass
    except Exception:
        pass
    finally:
        active_timers.pop(chat_id, None)


def build_question_keyboard(q_id: int, current_idx: int, total: int, chosen_option: str, answered_count: int):
    opt_buttons = []
    for opt in ['A', 'B', 'C', 'D']:
        if chosen_option and chosen_option.upper() == opt:
            btn_text = f"🔘 {opt}"
        else:
            btn_text = opt
        opt_buttons.append(InlineKeyboardButton(text=btn_text, callback_data=f"opt_{opt}"))

    nav_buttons = []
    if current_idx > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ Oldingi", callback_data="nav_prev"))
    if current_idx < total - 1:
        nav_buttons.append(InlineKeyboardButton(text="Keyingi ➡️", callback_data="nav_next"))

    finish_text = f"🏁 Yakunlash ({answered_count}/{total})"
    finish_button = [InlineKeyboardButton(text=finish_text, callback_data="ask_finish")]

    kb_rows = [opt_buttons]
    if nav_buttons:
        kb_rows.append(nav_buttons)
    kb_rows.append(finish_button)

    return InlineKeyboardMarkup(inline_keyboard=kb_rows)


async def render_and_send_question(chat_id: int, state: FSMContext, bot: Bot, is_new: bool = False):
    data = await state.get_data()
    idx = data["current_index"]
    questions = data["questions"]
    total = data["total"]
    answers = data.get("answers", {})
    deadline_ts = data.get("deadline_ts", 0)

    if deadline_ts > 0:
        remaining = int(deadline_ts - time.time())
        if remaining <= 0:
            await auto_finish_test(chat_id, state, bot, reason="time_up")
            return
        mins = remaining // 60
        secs = remaining % 60
        clock_icon = CLOCK_ICONS[(remaining // 3) % len(CLOCK_ICONS)]
        header_time = f"{clock_icon} <b>{mins:02d}:{secs:02d}</b>  |  "
    else:
        header_time = ""

    q = questions[idx]
    q_id = q["id"]
    chosen = answers.get(str(q_id), "")

    safe_q = html.escape(q['question_text'])
    safe_a = html.escape(q['option_a'])
    safe_b = html.escape(q['option_b'])
    safe_c = html.escape(q['option_c'])
    safe_d = html.escape(q['option_d'])

    selected_tag = f"\n👉 <i>Siz tanlagan javob: <b>{chosen}</b></i>" if chosen else ""

    text = (
        f"{header_time}❓ <b>{idx + 1}/{total} - Savol:</b>\n\n"
        f"{safe_q}\n\n"
        f"<b>A)</b> {safe_a}\n"
        f"<b>B)</b> {safe_b}\n"
        f"<b>C)</b> {safe_c}\n"
        f"<b>D)</b> {safe_d}"
        f"{selected_tag}"
    )

    kb = build_question_keyboard(
        q_id=q_id,
        current_idx=idx,
        total=total,
        chosen_option=chosen,
        answered_count=len(answers)
    )

    msg_id = data.get("msg_id")

    if is_new or not msg_id:
        sent = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=kb,
            protect_content=True,
            parse_mode="HTML"
        )
        await state.update_data(msg_id=sent.message_id)
    else:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=text,
                reply_markup=kb,
                parse_mode="HTML"
            )
        except TelegramBadRequest:
            pass


@router.callback_query(TestSessionState.in_test, F.data.startswith("opt_"))
async def cb_choose_option(callback: CallbackQuery, state: FSMContext, bot: Bot):
    option = callback.data.replace("opt_", "").upper()
    data = await state.get_data()

    deadline_ts = data.get("deadline_ts", 0)
    if deadline_ts > 0 and time.time() >= deadline_ts:
        await auto_finish_test(callback.message.chat.id, state, bot, reason="time_up")
        await callback.answer("Vaqt tugadi!", show_alert=True)
        return

    idx = data["current_index"]
    questions = data["questions"]
    total = data["total"]
    answers = data.get("answers", {})

    current_q_id = str(questions[idx]["id"])
    answers[current_q_id] = option
    await state.update_data(answers=answers)

    if idx < total - 1:
        await state.update_data(current_index=idx + 1)
        await callback.answer(f"{option} tanlandi!")
    else:
        await callback.answer(f"{option} tanlandi!")

    await render_and_send_question(callback.message.chat.id, state, bot)


@router.callback_query(TestSessionState.in_test, F.data == "nav_prev")
async def cb_nav_prev(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    idx = data["current_index"]
    if idx > 0:
        await state.update_data(current_index=idx - 1)
        await render_and_send_question(callback.message.chat.id, state, bot)
    await callback.answer()


@router.callback_query(TestSessionState.in_test, F.data == "nav_next")
async def cb_nav_next(callback: CallbackQuery, state: FSMContext, bot: Bot):
    data = await state.get_data()
    idx = data["current_index"]
    total = data["total"]
    if idx < total - 1:
        await state.update_data(current_index=idx + 1)
        await render_and_send_question(callback.message.chat.id, state, bot)
    await callback.answer()


@router.callback_query(TestSessionState.in_test, F.data == "ask_finish")
async def cb_ask_finish(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    total = data["total"]
    answers = data.get("answers", {})
    answered_count = len(answers)
    unanswered_count = total - answered_count

    warn_text = ""
    if unanswered_count > 0:
        warn_text = f"\n⚠️ <b>Diqqat:</b> {unanswered_count} ta savolga hali javob bermadingiz!\n"

    text = (
        f"🏁 <b>Testni yakunlamoqchimisiz?</b>\n\n"
        f"📊 Javob berilgan: <b>{answered_count} / {total}</b> ta"
        f"{warn_text}\n"
        f"Haqiqatan ham yakunlashni tasdiqlaysizmi?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Ha, yakunlash", callback_data="do_finish")],
        [InlineKeyboardButton(text="🔙 Testga qaytish", callback_data="back_to_test")]
    ])

    await state.set_state(TestSessionState.confirm_finish)
    msg_id = data.get("msg_id")
    if msg_id:
        try:
            await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(TestSessionState.confirm_finish, F.data == "back_to_test")
async def cb_back_to_test(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await state.set_state(TestSessionState.in_test)
    await render_and_send_question(callback.message.chat.id, state, bot)
    await callback.answer()


@router.callback_query(TestSessionState.confirm_finish, F.data == "do_finish")
async def cb_do_finish(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await auto_finish_test(callback.message.chat.id, state, bot, reason="manual")
    await callback.answer()


async def auto_finish_test(chat_id: int, state: FSMContext, bot: Bot, reason: str = "manual"):
    stop_timer(chat_id)
    data = await state.get_data()
    if not data or "attempt_id" not in data:
        return

    attempt_id = data["attempt_id"]
    questions = data["questions"]
    total = data["total"]
    answers = data.get("answers", {})
    test_title = data["test_title"]
    author_id = data.get("author_id", 0)

    score = await db.save_attempt_final_answers(attempt_id, questions, answers)
    percent = round((score / total) * 100, 1) if total > 0 else 0
    grade = get_grade(percent)

    user = await db.get_user(chat_id)
    full_name = user["full_name"] if user else "Talaba"
    username_str = f"@{user['username']}" if (user and user.get("username")) else "yo'q"

    time_up_header = "⌛️ <b>VAQT TUGADI!</b>\n\n" if reason == "time_up" else ""
    safe_title = html.escape(test_title)
    safe_name = html.escape(full_name)

    result_text = (
        f"{time_up_header}"
        f"🎉 <b>Test yakunlandi!</b>\n\n"
        f"📋 <b>Test:</b> {safe_title}\n"
        f"👤 <b>Talaba:</b> {safe_name}\n"
        f"✅ <b>To'g'ri javoblar:</b> {score} / {total} ta\n"
        f"📊 <b>Foiz ko'rsatkichi:</b> {percent}%\n"
        f"🎖 <b>Baho:</b> {grade}\n"
    )

    kb_rows = []
    if score < total:
        kb_rows.append([InlineKeyboardButton(text="💡 Xatolar va Izohlarni ko'rish", callback_data=f"review_{attempt_id}")])
    kb_rows.append([InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="student_menu")])

    msg_id = data.get("msg_id")
    if msg_id:
        try:
            await bot.edit_message_text(
                chat_id=chat_id,
                message_id=msg_id,
                text=result_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
                parse_mode="HTML"
            )
        except Exception:
            await bot.send_message(
                chat_id=chat_id,
                text=result_text,
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
                parse_mode="HTML"
            )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=result_text,
            reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
            parse_mode="HTML"
        )

    # O'QITUVCHIGA NATIJANI YUBORISH (BOSILADIGAN TELEGRAM PROFIL HAVOLASI BILAN)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    profile_mention = f'<a href="tg://user?id={chat_id}">{safe_name}</a>'
    admin_notification = (
        f"🔔 <b>Yangi test natijasi!</b>\n\n"
        f"👤 <b>Talaba:</b> {profile_mention}\n"
        f"📱 <b>Username:</b> {username_str}\n"
        f"🆔 <b>Telegram ID:</b> <code>{chat_id}</code>\n"
        f"📝 <b>Test:</b> {safe_title}\n"
        f"🎯 <b>Natija:</b> {score} / {total} ta ({percent}%)\n"
        f"🎖 <b>Baho:</b> {grade}\n"
        f"⏱ <b>Vaqti:</b> {now_str}\n\n"
        f"<i>(Talaba ismi ustiga bosib, uning profiliga to'g'ridan-to'g'ri o'tishingiz mumkin)</i>"
    )

    recipients = set(ADMIN_IDS)
    if author_id:
        recipients.add(author_id)

    test_id = data.get("test_id")
    notif_kb = None
    if test_id:
        notif_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Ushbu test hisoboti (Reyting & Excel)", callback_data=f"test_report_{test_id}")]
        ])

    for rec_id in recipients:
        try:
            await bot.send_message(
                chat_id=rec_id,
                text=admin_notification,
                reply_markup=notif_kb,
                parse_mode="HTML"
            )
        except Exception:
            pass

    await state.clear()


@router.callback_query(F.data.startswith("review_"))
async def cb_review_mistakes(callback: CallbackQuery, bot: Bot):
    attempt_id = int(callback.data.replace("review_", ""))
    mistakes = await db.get_attempt_mistakes(attempt_id)

    if not mistakes:
        await callback.answer("Xatolar topilmadi!", show_alert=True)
        return

    await callback.message.answer(
        "🔍 <b>Xato qilingan savollar va to'g'ri javoblar tahlili:</b>\n"
        "<i>(Savollar nusxa olishdan himoyalangan)</i>",
        parse_mode="HTML"
    )

    for i, m in enumerate(mistakes, start=1):
        safe_q = html.escape(m['question_text'])
        exp = f"\n💡 <b>Izoh:</b> {html.escape(m['explanation'])}" if m.get("explanation") else ""

        q_text = (
            f"❌ <b>{i}-xato savol:</b>\n"
            f"{safe_q}\n\n"
            f"Sizning javobingiz: ❌ <b>{m['selected_option']}</b>\n"
            f"To'g'ri javob: ✅ <b>{m['correct_option']}</b>"
            f"{exp}"
        )

        await bot.send_message(
            chat_id=callback.message.chat.id,
            text=q_text,
            protect_content=True,
            parse_mode="HTML"
        )

    await callback.answer()
