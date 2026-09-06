from aiogram import Router, F, Bot
from aiogram.types import (
    Message, CallbackQuery, FSInputFile,
    InlineKeyboardMarkup, InlineKeyboardButton,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from config import ADMIN_IDS
from database import db
from services.docx_parser import parse_docx_test, DocxParseError
from services.excel_exporter import export_results_to_excel
from utils.sample_doc import create_sample_docx
import os
import io
import html
import urllib.parse

router = Router()


class AdminState(StatesGroup):
    waiting_for_docx = State()
    waiting_for_month_price = State()
    waiting_for_year_price = State()
    waiting_for_click_details = State()
    waiting_for_grant_uid = State()
    waiting_for_grant_days = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or len(ADMIN_IDS) == 0


from keyboards import get_admin_reply_keyboard, get_student_reply_keyboard, get_admin_inline_keyboard




@router.message(Command("admin"))
@router.message(F.text == "👑 Admin Paneli")
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("Kechirasiz, siz bot administratori emassiz.")
        return

    await state.clear()
    await message.answer(
        "👋 <b>O'qituvchi / Admin Paneli</b>\n\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=get_admin_inline_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "admin_menu")
async def cb_admin_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat berilmagan", show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(
        "👋 <b>O'qituvchi / Admin Paneli</b>\n\n"
        "Quyidagi amallardan birini tanlang:",
        reply_markup=get_admin_inline_keyboard(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_upload_test")
async def cb_upload_test(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    can_upload, reason, info = await db.can_teacher_create_test(user_id)

    if not can_upload:
        price_m = await db.get_setting("price_month", "30000")
        price_y = await db.get_setting("price_year", "250000")
        await callback.message.edit_text(
            "⚠️ <b>3 ta bepul test yuklash limitingiz tugadi!</b>\n\n"
            "Yangi testlar yuklash uchun obuna bo'ling:\n\n"
            f"💳 <b>1 oylik obuna:</b> {price_m} so'm\n"
            f"💳 <b>1 yillik obuna:</b> {price_y} so'm",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Obuna sotib olish", callback_data="buy_subscription")],
                [InlineKeyboardButton(text="🔙 Orqaga", callback_data="admin_menu" if is_admin(user_id) else "teacher_cabinet")]
            ]),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    await state.set_state(AdminState.waiting_for_docx)
    await callback.message.edit_text(
        "📥 <b>Word (.docx) formatdagi test faylini yuboring</b>\n\n"
        "<b>Eslatma:</b>\n"
        "• Har bir savol raqam bilan boshlanishi (1. ...)\n"
        "• Variantlar A) B) C) D) ko'rinishida bo'lishi\n"
        "• Har bir savol ostida to'g'ri javob ko'rsatilishi (masalan: <code>Javob: B</code> yoki <code>*B)</code>)\n"
        "• Izoh ko'rsatilishi mumkin (<code>Izoh: ...</code>)\n\n"
        "Faylni yuboring:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Namuna faylni olish", callback_data="admin_get_sample")],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_menu" if is_admin(user_id) else "teacher_cabinet")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "admin_get_sample")
async def cb_get_sample(callback: CallbackQuery):
    sample_path = "data/namuna.docx"
    create_sample_docx(sample_path)
    file = FSInputFile(sample_path, filename="namunaviy_test.docx")
    await callback.message.answer_document(
        document=file,
        caption="📄 <b>Namunaviy Word (.docx) test fayli</b>\n\n"
                "Ushbu fayldagi formatga qarab o'z savollaringizni tayyorlashingiz va botga yuborishingiz mumkin.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(F.document, AdminState.waiting_for_docx)
@router.message(F.document)
async def handle_docx_upload(message: Message, state: FSMContext):
    user_id = message.from_user.id
    doc = message.document

    if not doc.file_name.lower().endswith(".docx"):
        await message.answer("❌ Iltimos, faqat <b>.docx</b> (Microsoft Word) formatidagi fayl yuboring!", parse_mode="HTML")
        return

    # Obuna va ruxsatni tekshirish
    can_upload, reason, t_info = await db.can_teacher_create_test(user_id)
    if not can_upload:
        price_m = await db.get_setting("price_month", "30000")
        price_y = await db.get_setting("price_year", "250000")
        await message.answer(
            "⚠️ <b>Bepul limit tugadi!</b>\n\n"
            "Siz 3 ta bepul test yuklash imkoniyatidan to'liq foydalandingiz.\n"
            "Yangi testlar yuklash uchun obuna bo'ling:\n\n"
            f"💳 <b>1 oylik obuna:</b> {price_m} so'm\n"
            f"💳 <b>1 yillik obuna:</b> {price_y} so'm\n\n"
            "Quyidagi tugma orqali Click obunasini rasmiylashtirishingiz mumkin:",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="💳 Obuna sotib olish", callback_data="buy_subscription")]
            ]),
            parse_mode="HTML"
        )
        await state.clear()
        return

    status_msg = await message.answer("⏳ Fayl yuklab olinmoqda va tahlil qilinmoqda...")

    try:
        file_io = io.BytesIO()
        await message.bot.download(doc, destination=file_io)
        file_io.seek(0)

        default_title = doc.file_name.rsplit(".", 1)[0].replace("_", " ")
        parsed = parse_docx_test(file_io, default_title=default_title)
        title = parsed["title"]
        questions = parsed["questions"]

        test_id = await db.add_test(title=title, author_id=user_id, questions=questions, time_limit_minutes=15)

        img_count = sum(1 for q in questions if q.get("image_path") or q.get("image_bytes"))
        img_info = f"\n🖼 <b>Rasmli savollar:</b> {img_count} ta" if img_count > 0 else ""

        safe_title = html.escape(title)
        bot_user = await message.bot.get_me()
        bot_username = bot_user.username
        test_link = f"https://t.me/{bot_username}?start=test_{test_id}"
        share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{title}' testini ishlash uchun havola:")

        await status_msg.edit_text(
            f"✅ <b>Test muvaffaqiyatli saqlandi!</b>\n\n"
            f"📌 <b>Test nomi:</b> {safe_title}\n"
            f"🔢 <b>Savollar soni:</b> {len(questions)} ta{img_info}\n"
            f"⏱ <b>Standart vaqt:</b> 15 daqiqa (sozlamalardan o'zgartira olasiz)\n"
            f"🆔 <b>Test ID:</b> #{test_id}\n\n"
            f"🔗 <b>Talabalarga yuborish uchun maxsus havola:</b>\n"
            f"<code>{test_link}</code>\n\n"
            f"<i>💡 Maxfiylik: Ushbu test boshqa o'qituvchi va talabalarga ko'rinmaydi. Faqat siz havola yuborgan talabalar ishlay oladi!</i>",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📤 Havolani guruhga ulashish (Share)", url=share_url)],
                [InlineKeyboardButton(text="⏱ Vaqtni sozlash", callback_data=f"admin_time_{test_id}")],
                [InlineKeyboardButton(text="📋 Mening testlarim", callback_data="admin_list_tests")],
                [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")]
            ]),
            parse_mode="HTML"
        )
        await state.clear()

    except DocxParseError as e:
        safe_err = html.escape(str(e))
        await status_msg.edit_text(
            f"❌ <b>Faylni o'qishda xatolik yuz berdi:</b>\n\n"
            f"{safe_err}\n\n"
            f"Iltimos, faylni tekshirib, qayta yuboring.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📄 Namuna faylni olish", callback_data="admin_get_sample")],
                [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        safe_err = html.escape(str(e))
        await status_msg.edit_text(f"❌ Xatolik: {safe_err}", parse_mode="HTML")


@router.callback_query(F.data == "admin_list_tests")
async def cb_list_tests(callback: CallbackQuery):
    user_id = callback.from_user.id
    tests = await db.get_tests_by_author(user_id)

    if not tests:
        await callback.message.edit_text(
            "📋 Hozirda siz yuklagan testlar mavjud emas.\n"
            "Yangi test yuklab, talabalaringizga maxsus havola yuborishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📥 Yangi test yuklash", callback_data="admin_upload_test")],
                [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")]
            ]),
            parse_mode="HTML"
        )
        await callback.answer()
        return

    kb_rows = []
    for t in tests:
        status_icon = "🟢" if t["is_active"] == 1 else "🔴"
        title_btn = f"{status_icon} {t['title']} ({t['question_count']} ta)"
        kb_rows.append([InlineKeyboardButton(text=title_btn, callback_data=f"admin_test_{t['id']}")])

    if is_admin(user_id):
        kb_rows.append([InlineKeyboardButton(text="🌐 Barcha o'qituvchilar testlari (Admin)", callback_data="superadmin_all_tests")])

    kb_rows.append([InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")])

    await callback.message.edit_text(
        "📋 <b>Siz yaratgan testlar ro'yxati:</b>\n"
        "(🟢 - Faol, 🔴 - Nofaol)\n\n"
        "<i>Eslatma: Bu testlar faqat sizga va siz havola bergan talabalarga ko'rinadi.</i>\n\n"
        "Havolani olish yoki boshqarish uchun testni tanlang:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "superadmin_all_tests")
async def cb_superadmin_all_tests(callback: CallbackQuery):
    user_id = callback.from_user.id
    if not is_admin(user_id):
        await callback.answer("Ruxsat berilmagan", show_alert=True)
        return

    tests = await db.get_all_system_tests()
    if not tests:
        await callback.answer("Tizimda testlar mavjud emas!", show_alert=True)
        return

    kb_rows = []
    for t in tests:
        status_icon = "🟢" if t["is_active"] == 1 else "🔴"
        author_name = t.get("author_name") or f"ID: {t['author_id']}"
        title_btn = f"{status_icon} {t['title']} (Muallif: {author_name})"
        kb_rows.append([InlineKeyboardButton(text=title_btn, callback_data=f"admin_test_{t['id']}")])

    kb_rows.append([InlineKeyboardButton(text="🔙 Mening testlarim", callback_data="admin_list_tests")])

    await callback.message.edit_text(
        "🌐 <b>Tizimdagi barcha testlar (Superadmin nazorati):</b>\n\n"
        "Kerakli test ustiga bosib boshqarishingiz yoki o'chirishingiz mumkin:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("admin_test_"))
async def cb_test_detail(callback: CallbackQuery):
    user_id = callback.from_user.id
    test_id = int(callback.data.replace("admin_test_", ""))
    test = await db.get_test_by_id(test_id)
    if not test:
        await callback.answer("Test topilmadi", show_alert=True)
        return

    if not is_admin(user_id) and test["author_id"] != user_id:
        await callback.answer("Bu test sizga tegishli emas", show_alert=True)
        return

    questions = await db.get_test_questions(test_id)
    results = await db.get_all_test_results(test_id=test_id, author_id=user_id)

    status_str = "🟢 Faol (Talabalar yecha oladi)" if test["is_active"] == 1 else "🔴 Nofaol (Yashiringan)"
    toggle_text = "🔴 Nofaol qilish" if test["is_active"] == 1 else "🟢 Faollashtirish"

    t_limit = test.get("time_limit_minutes", 15) or 15
    time_limit_str = f"{t_limit} daqiqa" if t_limit > 0 else "Cheklovsiz"

    bot_user = await callback.bot.get_me()
    bot_username = bot_user.username
    test_link = f"https://t.me/{bot_username}?start=test_{test_id}"
    share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{test['title']}' testini ishlash uchun havola:")

    is_rand = test.get("is_random", 1)
    if is_rand is None:
        is_rand = 1
    rand_status_str = "🟢 Yoqilgan (Aralashadi)" if is_rand == 1 else "🔴 O'chirilgan (Asl holatda)"
    rand_toggle_btn = "🔀 Random: O'chirish" if is_rand == 1 else "🔀 Random: Yoqish"

    safe_title = html.escape(test['title'])
    text = (
        f"📝 <b>Test tafsilotlari:</b>\n\n"
        f"📌 <b>Nomi:</b> {safe_title}\n"
        f"🔢 <b>Savollar soni:</b> {len(questions)} ta\n"
        f"⏱ <b>Ajratilgan vaqt:</b> {time_limit_str}\n"
        f"🔀 <b>Random rejim:</b> {rand_status_str}\n"
        f"📊 <b>Topshirgan talabalar:</b> {len(results)} kishi\n"
        f"⚙️ <b>Holati:</b> {status_str}\n"
        f"📅 <b>Yaratilgan vaqt:</b> {test['created_at']}\n\n"
        f"🔗 <b>Talabalarga yuborish uchun maxsus havola:</b>\n"
        f"<code>{test_link}</code>\n\n"
        f"<i>(Ushbu havolani nusxalab talabalaringizga yuboring yoki quyidagi ulashish tugmasini bosing)</i>"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Havolani guruhga ulashish (Share)", url=share_url)],
        [
            InlineKeyboardButton(text="⏱ Vaqtni sozlash", callback_data=f"admin_time_{test_id}"),
            InlineKeyboardButton(text=rand_toggle_btn, callback_data=f"admin_random_{test_id}")
        ],
        [InlineKeyboardButton(text=toggle_text, callback_data=f"admin_toggle_{test_id}")],
        [InlineKeyboardButton(text="📊 Excel natijalar", callback_data=f"admin_export_test_{test_id}")],
        [InlineKeyboardButton(text="🗑 O'chirish", callback_data=f"admin_delete_{test_id}")],
        [InlineKeyboardButton(text="🔙 Testlar ro'yxatiga", callback_data="admin_list_tests")]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_random_"))
async def cb_toggle_random(callback: CallbackQuery):
    test_id = int(callback.data.replace("admin_random_", ""))
    new_val = await db.toggle_test_random(test_id)
    status_text = "yoqildi (savollar va variantlar aralashadi)" if new_val == 1 else "o'chirildi (asl tartibda beriladi)"
    await callback.answer(f"🔀 Random rejim {status_text}!", show_alert=True)
    callback.data = f"admin_test_{test_id}"
    await cb_test_detail(callback)


@router.callback_query(F.data.startswith("admin_time_"))
async def cb_select_time_limit(callback: CallbackQuery):
    test_id = int(callback.data.replace("admin_time_", ""))
    test = await db.get_test_by_id(test_id)
    if not test:
        await callback.answer("Test topilmadi", show_alert=True)
        return

    safe_title = html.escape(test['title'])
    curr_limit = test.get("time_limit_minutes", 15) or 15
    curr_str = f"{curr_limit} daqiqa" if curr_limit > 0 else "Cheklovsiz"

    text = (
        f"⏱ <b>Test vaqtini sozlash:</b>\n\n"
        f"📌 <b>Test:</b> {safe_title}\n"
        f"⏳ <b>Hozirgi vaqt:</b> {curr_str}\n\n"
        f"Ushbu test uchun talabalarga qancha umumiy vaqt berilsin?"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="5 daq", callback_data=f"settime_{test_id}_5"),
            InlineKeyboardButton(text="10 daq", callback_data=f"settime_{test_id}_10"),
            InlineKeyboardButton(text="15 daq", callback_data=f"settime_{test_id}_15")
        ],
        [
            InlineKeyboardButton(text="20 daq", callback_data=f"settime_{test_id}_20"),
            InlineKeyboardButton(text="30 daq", callback_data=f"settime_{test_id}_30"),
            InlineKeyboardButton(text="45 daq", callback_data=f"settime_{test_id}_45")
        ],
        [
            InlineKeyboardButton(text="60 daq", callback_data=f"settime_{test_id}_60"),
            InlineKeyboardButton(text="♾ Cheklovsiz", callback_data=f"settime_{test_id}_0")
        ],
        [
            InlineKeyboardButton(text="🔙 Orqaga", callback_data=f"admin_test_{test_id}")
        ]
    ])

    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("settime_"))
async def cb_save_time_limit(callback: CallbackQuery):
    parts = callback.data.split("_")
    test_id = int(parts[1])
    minutes = int(parts[2])

    await db.update_test_time_limit(test_id, minutes)
    msg = f"Test vaqti {minutes} daqiqa etib belgilandi! ⏱" if minutes > 0 else "Test vaqti cheklovsiz qilindi! ♾"
    await callback.answer(msg, show_alert=True)

    callback.data = f"admin_test_{test_id}"
    await cb_test_detail(callback)


@router.callback_query(F.data.startswith("admin_toggle_"))
async def cb_toggle_test(callback: CallbackQuery):
    test_id = int(callback.data.replace("admin_toggle_", ""))
    new_status = await db.toggle_test_status(test_id)
    status_text = "faollashtirildi 🟢" if new_status == 1 else "nofaol qilindi 🔴"
    await callback.answer(f"Test {status_text}!")
    callback.data = f"admin_test_{test_id}"
    await cb_test_detail(callback)


@router.callback_query(F.data.startswith("admin_delete_"))
async def cb_delete_test(callback: CallbackQuery):
    test_id = int(callback.data.replace("admin_delete_", ""))
    await db.delete_test(test_id)
    await callback.answer("Test o'chirildi! 🗑", show_alert=True)
    await cb_list_tests(callback)


def get_grade(percent: float) -> str:
    if percent >= 86:
        return "A'lo (5)"
    elif percent >= 71:
        return "Yaxshi (4)"
    elif percent >= 56:
        return "Qoniqarli (3)"
    else:
        return "Qoniqarsiz (2)"


@router.message(F.text == "📊 Excel hisobot")
@router.callback_query(F.data == "admin_export_excel")
async def cb_export_excel_menu(event: Message | CallbackQuery):
    is_cb = isinstance(event, CallbackQuery)
    user_id = event.from_user.id
    target_msg = event.message if is_cb else event

    tests = await db.get_tests_with_stats_by_author(user_id)

    if not tests:
        text = (
            "📊 <b>Testlar hisoboti bo'limi</b>\n\n"
            "Sizda hozircha yaratilgan testlar mavjud emas.\n"
            "Yangi test yuklash uchun <b>👨‍🏫 O'qituvchi bo'limi</b> ➡️ <b>📥 Yangi test yuklash</b> tugmasini bosing."
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📥 Yangi test yuklash", callback_data="teacher_upload_test" if not is_admin(user_id) else "admin_upload_test")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")]
        ])
        if is_cb:
            await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
            await event.answer()
        else:
            await target_msg.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    kb_rows = []
    for idx, t in enumerate(tests, start=1):
        status_icon = "🟢" if t["is_active"] == 1 else "🔴"
        attempts_str = f"{t['attempt_count']} ta talaba" if t.get('attempt_count') else "topshirilmagan"
        btn_text = f"📝 {idx}. {t['title']} ({attempts_str})"
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"test_report_{t['id']}")])

    if len(tests) > 1:
        kb_rows.append([InlineKeyboardButton(text="📁 Barcha testlar jamlanmasi (Umumiy Excel)", callback_data="export_all_excel")])

    kb_rows.append([InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")])

    text = (
        "📊 <b>Testlar hisoboti va Natijalar</b>\n\n"
        "Qaysi testning hisobotini olmoqchisiz? Quyidagi ro'yxatdan tanlang:\n\n"
        "🔹 Talabalar reytingi <b>botning o'zida</b> batafsil ko'rsatiladi\n"
        "🔹 Shu test uchun alohida <b>Excel (.xlsx)</b> fayli yuboriladi\n"
        "🔹 Testga kirish uchun <b>maxsus havola</b> beriladi"
    )

    if is_cb:
        await event.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
        await event.answer()
    else:
        await target_msg.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")


@router.callback_query(F.data.startswith("test_report_"))
@router.callback_query(F.data.startswith("admin_export_test_"))
async def cb_single_test_report(callback: CallbackQuery):
    user_id = callback.from_user.id
    raw_data = callback.data
    if raw_data.startswith("test_report_"):
        test_id = int(raw_data.replace("test_report_", ""))
    else:
        test_id = int(raw_data.replace("admin_export_test_", ""))

    test, results = await db.get_test_results_summary(test_id, author_id=user_id)
    if not test:
        await callback.answer("Test topilmadi yoki unga ruxsatingiz yo'q.", show_alert=True)
        return

    bot_user = await callback.bot.get_me()
    bot_username = bot_user.username
    test_link = f"https://t.me/{bot_username}?start=test_{test_id}"
    share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{test['title']}' testini ishlash uchun havola:")

    safe_title = html.escape(test['title'])
    t_limit = test.get("time_limit_minutes", 15) or 15
    time_limit_str = f"{t_limit} daqiqa" if t_limit > 0 else "Cheklovsiz"

    kb_nav = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Havolani guruhga ulashish (Share)", url=share_url)],
        [InlineKeyboardButton(text="🔄 Natijalarni yangilash", callback_data=f"test_report_{test_id}")],
        [InlineKeyboardButton(text="🔙 Boshqa testlar hisoboti", callback_data="admin_export_excel")]
    ])

    if not results:
        text = (
            f"📊 <b>Test hisoboti: «{safe_title}»</b>\n\n"
            f"🔢 <b>Savollar soni:</b> {test.get('question_count', 0)} ta\n"
            f"⏱ <b>Ajratilgan vaqt:</b> {time_limit_str}\n"
            f"👥 <b>Jami topshirganlar:</b> 0 nafar (Hozircha hech kim topshirmagan)\n\n"
            f"🔗 <b>Talabalarga yuborish uchun maxsus havola:</b>\n"
            f"<code>{test_link}</code>\n\n"
            f"<i>💡 Talabalaringiz ushbu havola orqali kirib test topshirganlaridan so'ng, ularning reytingi va ballari shu yerda ko'rinadi hamda Excel (.xlsx) hisoboti yuklab olinadi.</i>"
        )
        try:
            await callback.message.edit_text(text, reply_markup=kb_nav, parse_mode="HTML")
        except Exception:
            await callback.message.answer(text, reply_markup=kb_nav, parse_mode="HTML")
        await callback.answer()
        return

    # Natijalar mavjud bo'lsa - reytingni hisoblash
    c5 = c4 = c3 = c2 = 0
    total_pct = 0.0
    leaderboard_lines = []

    for idx, r in enumerate(results, start=1):
        score = r.get("score", 0)
        total = r.get("total", 1) or 1
        pct = round((score / total) * 100, 1)
        total_pct += pct

        if pct >= 86:
            grade = "A'lo (5)"
            c5 += 1
        elif pct >= 71:
            grade = "Yaxshi (4)"
            c4 += 1
        elif pct >= 56:
            grade = "Qoniqarli (3)"
            c3 += 1
        else:
            grade = "Qoniqarsiz (2)"
            c2 += 1

        medal = "🥇" if idx == 1 else "🥈" if idx == 2 else "🥉" if idx == 3 else f"{idx}."
        safe_st_name = html.escape(r.get("full_name", "Noma'lum"))
        uname = f" (@{r['username']})" if r.get("username") else ""

        if idx <= 20:
            leaderboard_lines.append(f"{medal} <b>{safe_st_name}</b>{uname} — <b>{score}/{total}</b> ({pct}%) | {grade}")

    avg_pct = round(total_pct / len(results), 1)

    text = (
        f"📊 <b>Test hisoboti: «{safe_title}»</b>\n\n"
        f"🔢 <b>Savollar soni:</b> {test.get('question_count', 0)} ta | ⏱ <b>Vaqt:</b> {time_limit_str}\n"
        f"👥 <b>Jami topshirganlar:</b> {len(results)} nafar\n\n"
        f"🔗 <b>Talabalar uchun test havolasi:</b>\n"
        f"<code>{test_link}</code>\n\n"
        f"🏆 <b>TALABALAR REYTINGI (NATIJALAR):</b>\n"
        + "\n".join(leaderboard_lines) + "\n\n"
    )

    if len(results) > 20:
        text += f"<i>... va yana {len(results) - 20} nafar talaba natijalari Excel faylda keltirilgan.</i>\n\n"

    text += (
        f"📈 <b>O'rtacha o'zlashtirish:</b> {avg_pct}%\n"
        f"🟢 A'lo (5): {c5} ta | 🔵 Yaxshi (4): {c4} ta | 🟡 Qoniqarli (3): {c3} ta | 🔴 Qoniqarsiz (2): {c2} ta\n\n"
        f"📎 <i>Quyida ushbu test bo'yicha to'liq Excel (.xlsx) hisoboti yuborilmoqda ⬇️</i>"
    )

    try:
        await callback.message.edit_text(text, reply_markup=kb_nav, parse_mode="HTML")
    except Exception:
        await callback.message.answer(text, reply_markup=kb_nav, parse_mode="HTML")

    await callback.answer()

    # Alohida test uchun Excel faylini yaratish va yuborish
    try:
        excel_path = export_results_to_excel(results, test_title=test['title'])
        file = FSInputFile(excel_path, filename=os.path.basename(excel_path))
        await callback.message.answer_document(
            document=file,
            caption=f"📊 <b>«{safe_title}»</b> testi bo'yicha alohida Excel hisoboti.\n"
                    f"Jami talabalar soni: {len(results)} nafar.",
            reply_markup=kb_nav,
            parse_mode="HTML"
        )
    except Exception as e:
        await callback.message.answer(f"⚠️ Excel fayl tayyorlashda xatolik: {e}")


@router.callback_query(F.data == "export_all_excel")
async def cb_export_all_excel(callback: CallbackQuery):
    user_id = callback.from_user.id
    results = await db.get_all_test_results(author_id=user_id)
    if not results:
        await callback.answer("Hozircha hech qaysi test bo'yicha natijalar mavjud emas!", show_alert=True)
        return

    excel_path = export_results_to_excel(results, test_title=None)
    file = FSInputFile(excel_path, filename=os.path.basename(excel_path))
    await callback.message.answer_document(
        document=file,
        caption=f"📁 <b>Barcha testlaringiz bo'yicha umumiy Excel hisoboti</b>\n"
                f"Jami topshirilgan natijalar: {len(results)} ta.",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Testlar hisobotiga qaytish", callback_data="admin_export_excel")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


# ==============================================================================
# ⚙️ SOZLAMALAR VA TO'LOV BOSHQARUVI (PASTKI TUGMA + ADMIN)
# ==============================================================================

@router.message(F.text == "⚙️ Obuna va To'lovlar")
@router.callback_query(F.data == "admin_settings")
async def cb_admin_settings(event: Message | CallbackQuery, state: FSMContext):
    user_id = event.from_user.id
    if not is_admin(user_id):
        if isinstance(event, CallbackQuery):
            await event.answer("Ruxsat berilmagan", show_alert=True)
        else:
            await event.answer("Kechirasiz, siz bot administratori emassiz.")
        return

    await state.clear()
    price_m = await db.get_setting("price_month", "30000")
    price_y = await db.get_setting("price_year", "250000")
    click_det = await db.get_setting("click_details", "8600 0000 0000 0000 (Click)")

    text = (
        "⚙️ <b>Obuna va To'lov Sozlamalari (Superadmin):</b>\n\n"
        f"💳 <b>1 oylik narx:</b> {price_m} so'm\n"
        f"💳 <b>1 yillik narx:</b> {price_y} so'm\n"
        f"📲 <b>Click rekvizit:</b> <code>{click_det}</code>\n\n"
        "O'zgartirish yoki qo'lda obuna berish uchun tanlang:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ 1 oylik narxni o'zgartirish", callback_data="set_price_month")],
        [InlineKeyboardButton(text="✏️ 1 yillik narxni o'zgartirish", callback_data="set_price_year")],
        [InlineKeyboardButton(text="✏️ Click kartani o'zgartirish", callback_data="set_click_card")],
        [InlineKeyboardButton(text="🎁 Qo'lda obuna berish (ID orqali)", callback_data="grant_sub_manual")],
        [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu")]
    ])

    if isinstance(event, CallbackQuery):
        await event.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
        await event.answer()
    else:
        await event.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "set_price_month")
async def cb_set_price_month(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminState.waiting_for_month_price)
    await callback.message.edit_text(
        "💰 <b>1 oylik obunaning yangi narxini kiriting (so'mda):</b>\n"
        "Masalan: <code>40000</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_settings")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminState.waiting_for_month_price)
async def process_new_month_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqam kiriting! Masalan: <code>35000</code>", parse_mode="HTML")
        return

    await db.set_setting("price_month", text)
    await state.clear()
    await message.answer(f"✅ 1 oylik obuna narxi <b>{text} so'm</b> qilib saqlandi!", parse_mode="HTML")
    await message.answer("Boshqaruv:", reply_markup=get_admin_reply_keyboard())


@router.callback_query(F.data == "set_price_year")
async def cb_set_price_year(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminState.waiting_for_year_price)
    await callback.message.edit_text(
        "💰 <b>1 yillik obunaning yangi narxini kiriting (so'mda):</b>\n"
        "Masalan: <code>300000</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_settings")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminState.waiting_for_year_price)
async def process_new_year_price(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    text = message.text.strip().replace(" ", "")
    if not text.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqam kiriting! Masalan: <code>250000</code>", parse_mode="HTML")
        return

    await db.set_setting("price_year", text)
    await state.clear()
    await message.answer(f"✅ 1 yillik obuna narxi <b>{text} so'm</b> qilib saqlandi!", parse_mode="HTML")
    await message.answer("Boshqaruv:", reply_markup=get_admin_reply_keyboard())


@router.callback_query(F.data == "set_click_card")
async def cb_set_click_card(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminState.waiting_for_click_details)
    await callback.message.edit_text(
        "📲 <b>Click to'lov uchun yangi karta raqami yoki telefonni kiriting:</b>\n"
        "Masalan: <code>8600 1234 5678 9012 (Ism Familiya)</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_settings")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminState.waiting_for_click_details)
async def process_new_click_card(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    card_info = message.text.strip()
    await db.set_setting("click_details", card_info)
    await state.clear()
    await message.answer(f"✅ Click to'lov ma'lumotlari saqlandi:\n<code>{html.escape(card_info)}</code>", parse_mode="HTML")
    await message.answer("Boshqaruv:", reply_markup=get_admin_reply_keyboard())


@router.callback_query(F.data == "grant_sub_manual")
async def cb_grant_sub_manual(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminState.waiting_for_grant_uid)
    await callback.message.edit_text(
        "🎁 <b>Obuna bermoqchi bo'lgan foydalanuvchining Telegram ID raqamini kiriting:</b>\n"
        "Masalan: <code>1184083915</code>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_settings")]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(AdminState.waiting_for_grant_uid)
async def process_grant_uid(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    uid_str = message.text.strip()
    if not uid_str.isdigit():
        await message.answer("⚠️ Iltimos, faqat raqamlardan iborat Telegram ID kiriting!", parse_mode="HTML")
        return

    uid = int(uid_str)
    await state.update_data(grant_uid=uid)
    await state.set_state(AdminState.waiting_for_grant_days)

    await message.answer(
        f"👤 ID: <code>{uid}</code>\n\nUshbu foydalanuvchiga qancha muddatga obuna bermoqchisiz?",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [
                InlineKeyboardButton(text="1 oy (30 kun)", callback_data="manualdays_30"),
                InlineKeyboardButton(text="3 oy (90 kun)", callback_data="manualdays_90")
            ],
            [
                InlineKeyboardButton(text="1 yil (365 kun)", callback_data="manualdays_365"),
                InlineKeyboardButton(text="♾ Umrbod", callback_data="manualdays_9999")
            ],
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_settings")]
        ]),
        parse_mode="HTML"
    )


@router.callback_query(F.data.startswith("manualdays_"))
async def cb_save_manual_days(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return

    days = int(callback.data.replace("manualdays_", ""))
    data = await state.get_data()
    uid = data.get("grant_uid")

    if not uid:
        await callback.answer("Xatolik: foydalanuvchi topilmadi", show_alert=True)
        return

    new_date = await db.grant_subscription(uid, days)
    await state.clear()

    await callback.message.edit_text(
        f"✅ <b>Foydalanuvchiga obuna berildi!</b>\n\n"
        f"👤 ID: <code>{uid}</code>\n"
        f"📅 Muddat: <b>{new_date}</b> gacha ({days} kun)",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Sozlamalarga", callback_data="admin_settings")]
        ]),
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=uid,
            text=f"🎁 <b>Xushxabar!</b> Administrator sizga <b>{days} kunlik cheklovsiz obuna</b> berdi!\n"
                 f"Endi bemalol o'z testlaringizni botga yuklashingiz mumkin.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer()


# ==============================================================================
# 💳 TO'LOV CHEKLARINI TASDIQLASH VA RAD ETISH
# ==============================================================================

@router.callback_query(F.data.startswith("approve_pay_"))
async def cb_approve_payment(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat berilmagan", show_alert=True)
        return

    pay_id = int(callback.data.replace("approve_pay_", ""))
    payment = await db.get_payment_by_id(pay_id)
    if not payment or payment["status"] != "pending":
        await callback.answer("Ushbu so'rov allaqachon ko'rib chiqilgan!", show_alert=True)
        return

    user_id = payment["user_id"]
    plan = payment["plan_type"]
    days = 30 if plan == "month" else 365

    await db.update_payment_status(pay_id, "approved")
    new_until = await db.grant_subscription(user_id, days)

    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n"
                f"✅ <b>TO'LOV TASDIQLANDI!</b>\n"
                f"📅 Obuna {new_until} gacha uzaytirildi.",
        parse_mode="HTML"
    )

    plan_name = "1 oylik" if plan == "month" else "1 yillik"
    try:
        await bot.send_message(
            chat_id=user_id,
            text=(
                f"🎉 <b>To'lovingiz muvaffaqiyatli tasdiqlandi!</b>\n\n"
                f"Sizga <b>{plan_name} cheklovsiz obuna</b> faollashtirildi.\n"
                f"📅 Amal qilish muddati: <b>{new_until}</b> gacha.\n\n"
                f"Endi botga xohlagancha Word formatida test yuklashingiz mumkin!"
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer("Obuna faollashtirildi!")


@router.callback_query(F.data.startswith("reject_pay_"))
async def cb_reject_payment(callback: CallbackQuery, bot: Bot):
    if not is_admin(callback.from_user.id):
        await callback.answer("Ruxsat berilmagan", show_alert=True)
        return

    pay_id = int(callback.data.replace("reject_pay_", ""))
    payment = await db.get_payment_by_id(pay_id)
    if not payment or payment["status"] != "pending":
        await callback.answer("Ushbu so'rov allaqachon ko'rib chiqilgan!", show_alert=True)
        return

    user_id = payment["user_id"]
    await db.update_payment_status(pay_id, "rejected")

    await callback.message.edit_caption(
        caption=f"{callback.message.caption}\n\n❌ <b>TO'LOV RAD ETILDI.</b>",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=user_id,
            text="❌ <b>To'lov so'rovingiz rad etildi.</b>\n"
                 "Iltimos, Click to'lov ma'lumotlarini tekshirib, chekni qayta yuboring.",
            parse_mode="HTML"
        )
    except Exception:
        pass

    await callback.answer("To'lov rad etildi.")
