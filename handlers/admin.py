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
import config
from database import db
from services.docx_parser import parse_docx_test, DocxParseError
from services.pdf_parser import parse_pdf_test, parse_single_question_text, PdfParseError
from services.ai_generator import (
    generate_test_from_content,
    generate_test_from_image,
    generate_test_from_pdf_file,
    generate_test_from_docx_file,
    AIGeneratorError
)
from services.excel_exporter import export_results_to_excel
from utils.sample_doc import create_sample_docx
import os
import io
import html
import urllib.parse

from keyboards import get_admin_reply_keyboard, get_student_reply_keyboard, get_admin_inline_keyboard, get_test_creation_keyboard

router = Router()


class AdminState(StatesGroup):
    waiting_for_docx = State()
    waiting_for_pdf = State()
    waiting_for_month_price = State()
    waiting_for_year_price = State()
    waiting_for_click_details = State()
    waiting_for_grant_uid = State()
    waiting_for_grant_days = State()
    waiting_for_gemini_key = State()


class ManualTestState(StatesGroup):
    waiting_for_title = State()
    waiting_for_question = State()


class AITestState(StatesGroup):
    waiting_for_material = State()
    waiting_for_count = State()
    waiting_for_confirm = State()


class TeacherMessageState(StatesGroup):
    waiting_for_message = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS or len(ADMIN_IDS) == 0




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

    back_cb = "admin_menu" if is_admin(user_id) else "teacher_cabinet"
    await callback.message.edit_text(
        "📥 <b>Yangi test yaratish / yuklash usulini tanlang:</b>\n\n"
        "1️⃣ <b>Word (.docx) fayl</b> — Tayyor Word test faylini yuklash\n"
        "2️⃣ <b>PDF (.pdf) fayl</b> — PDF formatidagi test faylini yuklash (rasmlari bilan)\n"
        "3️⃣ <b>✍️ Botda qo'lda kiritish</b> — Savol matni yoki rasmini bittalab botga yuborish\n"
        "4️⃣ <b>🤖 AI Test Yaratuvchi</b> — Darslik matni, fotosurat, Word yoki PDF konspekt asosida AI ga test tuzdirish\n\n"
        "Qaysi usuldan foydalanasiz?",
        reply_markup=get_test_creation_keyboard(back_cb),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "create_test_docx")
async def cb_create_test_docx(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    can_upload, _, _ = await db.can_teacher_create_test(user_id)
    if not can_upload:
        await callback.answer("Obuna talab qilinadi", show_alert=True)
        return
    await state.set_state(AdminState.waiting_for_docx)
    back_cb = "admin_upload_test" if is_admin(user_id) else "teacher_upload_test"
    await callback.message.edit_text(
        "📥 <b>Word (.docx) formatdagi test faylini yuboring:</b>\n\n"
        "<b>Eslatma:</b>\n"
        "• Har bir savol raqam bilan boshlanishi (1. ...)\n"
        "• Variantlar A) B) C) D) ko'rinishida bo'lishi\n"
        "• Har bir savol ostida to'g'ri javob ko'rsatilishi (masalan: <code>Javob: B</code> yoki <code>*B)</code>)\n"
        "• Savol ichida rasm yoki jadval bo'lsa, avtomatik saqlanadi!\n\n"
        "Word (.docx) faylni kutyapman...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📄 Namuna faylni olish", callback_data="admin_get_sample")],
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=back_cb)]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.callback_query(F.data == "create_test_pdf")
async def cb_create_test_pdf(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    can_upload, _, _ = await db.can_teacher_create_test(user_id)
    if not can_upload:
        await callback.answer("Obuna talab qilinadi", show_alert=True)
        return
    await state.set_state(AdminState.waiting_for_pdf)
    back_cb = "admin_upload_test" if is_admin(user_id) else "teacher_upload_test"
    await callback.message.edit_text(
        "📑 <b>PDF (.pdf) formatdagi test faylini yuboring:</b>\n\n"
        "<b>Eslatma:</b>\n"
        "• PDF ichida savollar 1., 2. tarzida, variantlar A), B), C), D) bo'lishi lozim\n"
        "• To'g'ri javoblar savol ostida <code>Javob: A</code> yoki variant oldida <code>*A)</code> shaklida bo'lishi kerak\n"
        "• PDF sahifasidagi rasmlar avtomatik tarzda savollarga biriktiriladi!\n\n"
        "PDF (.pdf) faylni kutyapman...",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Orqaga", callback_data=back_cb)]
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
@router.message(F.document, AdminState.waiting_for_pdf)
@router.message(F.document)
async def handle_document_upload(message: Message, state: FSMContext):
    current_state = await state.get_state()
    # Agar AI rejimida fayl kutayotgan bo'lsa, bu handler uni o'zlashtirib olmasin
    if current_state == AITestState.waiting_for_material.state:
        return

    user_id = message.from_user.id
    doc = message.document
    file_name = (doc.file_name or "").lower()
    is_docx = file_name.endswith(".docx")
    is_pdf = file_name.endswith(".pdf")

    if not (is_docx or is_pdf):
        await message.answer("❌ Iltimos, faqat <b>.docx</b> (Word) yoki <b>.pdf</b> (PDF) formatidagi test faylini yuboring!", parse_mode="HTML")
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
        if is_docx:
            parsed = parse_docx_test(file_io, default_title=default_title)
        else:
            parsed = parse_pdf_test(file_io, default_title=default_title)

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

    except (DocxParseError, PdfParseError) as e:
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


# ==============================================================================
# ✍️ BOTDA QO'LDA TEST TUZISH (MATN VA RASM)
# ==============================================================================

@router.callback_query(F.data == "create_test_manual")
async def cb_create_test_manual(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    can_upload, _, _ = await db.can_teacher_create_test(user_id)
    if not can_upload:
        await callback.answer("Obuna talab qilinadi", show_alert=True)
        return
    await state.set_state(ManualTestState.waiting_for_title)
    back_cb = "admin_upload_test" if is_admin(user_id) else "teacher_upload_test"
    await callback.message.edit_text(
        "✍️ <b>Botda qo'lda yangi test tuzish</b>\n\n"
        "Dastlab test nomini (sarlavhasini) kiriting:\n"
        "Masalan: <i>Biologiya 8-sinf Genetika</i>\n\n"
        "Nomni yuboring:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data=back_cb)]
        ]),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(ManualTestState.waiting_for_title)
async def process_manual_test_title(message: Message, state: FSMContext):
    title = message.text.strip()
    if len(title) < 3:
        await message.answer("⚠️ Test nomi juda qisqa. Kamida 3 ta harfdan iborat nom kiriting:")
        return

    await state.update_data(manual_title=title, manual_questions=[])
    await state.set_state(ManualTestState.waiting_for_question)

    safe_title = html.escape(title)
    text = (
        f"📝 <b>Test nomi:</b> {safe_title}\n"
        f"🔢 <b>Kiritilgan savollar:</b> 0 ta\n\n"
        "<b>Savolni quyidagi usullardan birida yuborishingiz mumkin:</b>\n\n"
        "1️⃣ <b>Matnli savol:</b> Savol matni, variantlar va to'g'ri javobni bitta xabarda yozing;\n"
        "2️⃣ <b>Rasmli savol:</b> Avval rasmni (foto) yuboring, so'ng unga tegishli savol matnini yuboring (yoki rasmni izohi bilan yuboring)!\n\n"
        "<i>💡 Eslatma: Rasmda savol yozilgan bo'lishi shart emas. Rasm shunchaki sxema, formula yoki tasvir bo'ladi, savol esa rasm bilan bog'liq bo'lib uning tagida beriladi.</i>\n\n"
        "<i>Namuna:\n"
        "O'zbekiston poytaxti qaysi shahar?\n"
        "A) Samarqand\n"
        "B) Buxoro\n"
        "C) Toshkent\n"
        "D) Xiva\n"
        "Javob: C\n"
        "Izoh: 1930-yildan buyon poytaxt.</i>\n\n"
        "Savol yoki rasmni yuboring:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="manual_cancel_test")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.message(ManualTestState.waiting_for_question, F.photo)
@router.message(ManualTestState.waiting_for_question, F.text)
async def process_manual_question(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    pending_img_bytes = data.get("pending_photo_bytes")

    img_bytes = None
    raw_text = ""

    # 1. Agar foydalanuvchi faqat rasmni (izohsiz) yuborgan bo'lsa:
    if message.photo and not message.caption:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        img_bytes = file_io.getvalue()
        await state.update_data(pending_photo_bytes=img_bytes)

        text = (
            "🖼 <b>Savol rasmi muvaffaqiyatli qabul qilindi!</b>\n\n"
            "<i>(Eslatma: Rasmda savol yozilgan bo'lishi shart emas, savol rasm tagida joylashadi).</i>\n\n"
            "Endi ushbu rasm bilan bog'liq <b>savol matni, variantlari (A, B, C, D) va to'g'ri javobini</b> yuboring:\n\n"
            "<i>💡 Namuna:\n"
            "Rasmda tasvirlangan shaklning yuzini toping:\n"
            "A) 12 sm²\n"
            "B) 16 sm²\n"
            "C) 20 sm²\n"
            "D) 24 sm²\n"
            "Javob: B\n"
            "Izoh: Kvadrat yuzi tomoni kvadratiga teng.</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manual_cancel_test")]
        ])
        await message.answer(text, reply_markup=kb, parse_mode="HTML")
        return

    # 2. Agar rasm bilan birga izoh yuborilgan bo'lsa:
    if message.photo and message.caption:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        img_bytes = file_io.getvalue()
        raw_text = message.caption

    # 3. Agar faqat matn yuborilgan bo'lsa:
    elif message.text:
        raw_text = message.text
        # Agar avvalroq rasm yuborilgan bo'lsa, uni ushbu savolga biriktiramiz
        img_bytes = pending_img_bytes

    try:
        parsed_q = parse_single_question_text(raw_text, image_bytes=img_bytes)
    except PdfParseError as e:
        await message.answer(
            f"❌ <b>Savolni qabul qilib bo'lmadi:</b>\n\n"
            f"{html.escape(str(e))}\n\n"
            "Iltimos, namunaga qarab savol, variantlar (A, B, C, D) va to'g'ri javobni qayta yuboring:",
            parse_mode="HTML"
        )
        return

    questions = data.get("manual_questions", [])
    questions.append(parsed_q)
    # Savol muvaffaqiyatli saqlandi, kutayotgan rasmni tozalaymiz
    await state.update_data(manual_questions=questions, pending_photo_bytes=None)

    q_count = len(questions)
    img_tag = "🖼 Rasm: Biriktirildi ✅\n" if img_bytes else ""
    safe_q_preview = html.escape(parsed_q['question_text'][:70])

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Testni yakunlash va saqlash ({q_count} ta savol)", callback_data="manual_finish_test")],
        [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="manual_cancel_test")]
    ])

    await message.answer(
        f"✅ <b>{q_count}-savol muvaffaqiyatli qabul qilindi!</b>\n\n"
        f"❓ {safe_q_preview}...\n"
        f"{img_tag}"
        f"👉 To'g'ri javob: <b>{parsed_q['correct_option']}</b>\n\n"
        f"<i>Keyingi savolni (yoki rasmni) yuborishingiz, yoxud testni saqlashingiz mumkin:</i>",
        reply_markup=kb,
        parse_mode="HTML"
    )


@router.callback_query(F.data == "manual_finish_test")
async def cb_finish_manual_test(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    questions = data.get("manual_questions", [])
    title = data.get("manual_title", "Qo'lda kiritilgan test")

    if not questions:
        await callback.answer("Kamida 1 ta savol kiritilishi kerak!", show_alert=True)
        return

    user_id = callback.from_user.id
    test_id = await db.add_test(title=title, author_id=user_id, questions=questions, time_limit_minutes=15)

    img_count = sum(1 for q in questions if q.get("image_path") or q.get("image_bytes"))
    img_info = f"\n🖼 <b>Rasmli savollar:</b> {img_count} ta" if img_count > 0 else ""

    safe_title = html.escape(title)
    bot_user = await callback.bot.get_me()
    bot_username = bot_user.username
    test_link = f"https://t.me/{bot_username}?start=test_{test_id}"
    share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{title}' testini ishlash uchun havola:")

    await callback.message.edit_text(
        f"🎉 <b>Test muvaffaqiyatli saqlandi!</b>\n\n"
        f"📌 <b>Test nomi:</b> {safe_title}\n"
        f"🔢 <b>Savollar soni:</b> {len(questions)} ta{img_info}\n"
        f"⏱ <b>Standart vaqt:</b> 15 daqiqa\n"
        f"🆔 <b>Test ID:</b> #{test_id}\n\n"
        f"🔗 <b>Talabalarga yuborish uchun havola:</b>\n"
        f"<code>{test_link}</code>\n\n"
        f"<i>💡 Maxfiylik: Ushbu test faqat siz havola yuborgan talabalarga ko'rinadi!</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Guruhga ulashish (Share)", url=share_url)],
            [InlineKeyboardButton(text="⏱ Vaqtni sozlash", callback_data=f"admin_time_{test_id}")],
            [InlineKeyboardButton(text="📋 Mening testlarim", callback_data="admin_list_tests")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")]
        ]),
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(F.data == "manual_cancel_test")
async def cb_cancel_manual_test(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    user_id = callback.from_user.id
    await callback.message.edit_text("❌ Test tuzish bekor qilindi.", parse_mode="HTML")
    await callback.answer()


# ==============================================================================
# 🤖 AI TEST GENERATOR (GEMINI 2.5 FLASH)
# ==============================================================================

@router.callback_query(F.data == "create_test_ai")
async def cb_create_test_ai(callback: CallbackQuery, state: FSMContext):
    user_id = callback.from_user.id
    can_upload, _, _ = await db.can_teacher_create_test(user_id)
    if not can_upload:
        await callback.answer("Obuna talab qilinadi", show_alert=True)
        return

    gemini_key = await db.get_setting("gemini_api_key", "") or config.GEMINI_API_KEY
    back_cb = "admin_upload_test" if is_admin(user_id) else "teacher_upload_test"

    if not gemini_key:
        text = (
            "🤖 <b>AI Test Yaratuvchi</b>\n\n"
            "⚠️ Ushbu funksiyadan foydalanish uchun <b>AI API kaliti</b> kiritilishi kerak!\n\n"
            "AI Studio'dan mutlaqo bepul API kalit olishingiz mumkin:\n"
            "1. <a href='https://aistudio.google.com/app/apikey'>aistudio.google.com</a> ga kiring;\n"
            "2. 'Create API key' tugmasini bosing va kalitni nusxalang;\n"
            "3. Botda <b>👑 Admin Paneli ➡️ ⚙️ Sozlamalar ➡️ 🔑 AI API kalitini sozlash</b> tugmasi orqali kiriting.\n\n"
            "<i>Kalit kiritilishi bilanoq AI test tuzish to'liq ishlaydi!</i>"
        )
        kb_rows = []
        if is_admin(user_id):
            kb_rows.append([InlineKeyboardButton(text="🔑 Kalitni kiritish", callback_data="set_gemini_key")])
        kb_rows.append([InlineKeyboardButton(text="🔙 Orqaga", callback_data=back_cb)])
        await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML", disable_web_page_preview=True)
        await callback.answer()
        return

    await state.set_state(AITestState.waiting_for_material)
    text = (
        "🤖 <b>Aqlli AI Test Yaratuvchi</b>\n\n"
        "AI qanday material asosida test tuzsin? Quyidagilardan birini yuboring:\n\n"
        "1️⃣ <b>Mavzu yoki matn:</b> Masalan: <i>'Amir Temur davlati mavzusida 5 ta qiyin test tuz'</i> yoki dars konspekti matni;\n"
        "2️⃣ <b>Rasm (Foto):</b> Darslik sahifasi yoki konspekt daftari fotosuratini yuboring;\n"
        "3️⃣ <b>Word (.docx):</b> Konspekt yoki kitob bo'limi faylini yuboring;\n"
        "4️⃣ <b>PDF (.pdf):</b> Darslik yoki ma'ruza PDF faylini yuboring.\n\n"
        "Materialni yuboring:"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data=back_cb)]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML")
    await callback.answer()


@router.message(AITestState.waiting_for_material, F.photo)
@router.message(AITestState.waiting_for_material, F.document)
@router.message(AITestState.waiting_for_material, F.text)
async def process_ai_material(message: Message, state: FSMContext, bot: Bot):
    material_type = "text"
    media_bytes = None
    prompt_text = ""

    if message.photo:
        photo = message.photo[-1]
        file_io = io.BytesIO()
        await bot.download(photo, destination=file_io)
        media_bytes = file_io.getvalue()
        material_type = "photo"
        prompt_text = message.caption or ""
    elif message.document:
        doc = message.document
        fname = (doc.file_name or "").lower()
        if fname.endswith(".docx"):
            material_type = "docx"
        elif fname.endswith(".pdf"):
            material_type = "pdf"
        else:
            await message.answer("❌ Iltimos, faqat Word (.docx) yoki PDF (.pdf) formatidagi fayl yuboring!")
            return

        file_io = io.BytesIO()
        await bot.download(doc, destination=file_io)
        media_bytes = file_io.getvalue()
        prompt_text = message.caption or ""
    elif message.text:
        material_type = "text"
        prompt_text = message.text

    await state.update_data(
        ai_material_type=material_type,
        ai_media_bytes=media_bytes,
        ai_prompt_text=prompt_text
    )
    await state.set_state(AITestState.waiting_for_count)

    text = (
        "🔢 <b>Testda nechta savol bo'lishini xohlaysiz?</b>\n\n"
        "Quyidagi variantlardan birini tanlang yoki xohlagan soningizni yozib yuboring (masalan: <code>7</code>):"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="5 ta", callback_data="ai_count_5"),
            InlineKeyboardButton(text="10 ta", callback_data="ai_count_10")
        ],
        [
            InlineKeyboardButton(text="15 ta", callback_data="ai_count_15"),
            InlineKeyboardButton(text="20 ta", callback_data="ai_count_20")
        ],
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="ai_cancel")]
    ])
    await message.answer(text, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data.startswith("ai_count_"), AITestState.waiting_for_count)
async def cb_ai_select_count(callback: CallbackQuery, state: FSMContext):
    count = int(callback.data.split("_")[-1])
    await run_ai_test_generation(callback.message, state, count, is_callback=True)
    await callback.answer()


@router.message(AITestState.waiting_for_count)
async def process_ai_custom_count(message: Message, state: FSMContext):
    val = message.text.strip()
    if not val.isdigit() or int(val) < 1 or int(val) > 40:
        await message.answer("⚠️ Iltimos, 1 dan 40 gacha bo'lgan son kiriting (masalan: 10):")
        return
    await run_ai_test_generation(message, state, int(val), is_callback=False)


async def run_ai_test_generation(event: Message, state: FSMContext, count: int, is_callback: bool = False):
    data = await state.get_data()
    mat_type = data.get("ai_material_type", "text")
    media_bytes = data.get("ai_media_bytes")
    prompt_text = data.get("ai_prompt_text", "")

    api_key = await db.get_setting("gemini_api_key", "") or config.GEMINI_API_KEY
    if not api_key:
        err_text = "❌ AI API kaliti topilmadi. Admin orqali sozlang."
        if is_callback:
            await event.edit_text(err_text)
        else:
            await event.answer(err_text)
        await state.clear()
        return

    wait_text = (
        f"⏳ <b>Aqlli AI tizimi ma'lumotlarni tahlil qilib, {count} ta test tuzmoqda...</b>\n\n"
        "<i>Iltimos kuting (10-20 soniya)...</i>"
    )
    if is_callback:
        status_msg = await event.edit_text(wait_text, parse_mode="HTML")
    else:
        status_msg = await event.answer(wait_text, parse_mode="HTML")

    try:
        if mat_type == "photo":
            result = await generate_test_from_image(media_bytes, "image/jpeg", api_key, count, prompt_text)
        elif mat_type == "pdf":
            result = await generate_test_from_pdf_file(media_bytes, api_key, count, prompt_text)
        elif mat_type == "docx":
            result = await generate_test_from_docx_file(media_bytes, api_key, count, prompt_text)
        else:
            result = await generate_test_from_content(prompt_text, api_key, count)

        title = result["title"]
        questions = result["questions"]

        await state.update_data(ai_title=title, ai_questions=questions)
        await state.set_state(AITestState.waiting_for_confirm)

        sample_q = questions[0]
        preview_text = (
            f"🤖 <b>AI tomonidan test tayyorlandi!</b>\n\n"
            f"📌 <b>Test nomi:</b> {html.escape(title)}\n"
            f"🔢 <b>Savollar soni:</b> {len(questions)} ta\n\n"
            f"<b>1-savol namunasi:</b>\n"
            f"❓ <b>{html.escape(sample_q['question_text'])}</b>\n"
            f"A) {html.escape(sample_q['option_a'])}\n"
            f"B) {html.escape(sample_q['option_b'])}\n"
            f"C) {html.escape(sample_q['option_c'])}\n"
            f"D) {html.escape(sample_q['option_d'])}\n"
            f"👉 To'g'ri javob: <b>{sample_q['correct_option']}</b>\n"
            f"💡 Izoh: <i>{html.escape(sample_q['explanation'])}</i>\n\n"
            f"<i>Ushbu testni saqlab, talabalar uchun havola yaratilsinmi?</i>"
        )
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="✅ Saqlash va havola olish", callback_data="ai_confirm_save")],
            [InlineKeyboardButton(text="❌ Bekor qilish", callback_data="ai_cancel")]
        ])
        await status_msg.edit_text(preview_text, reply_markup=kb, parse_mode="HTML")

    except AIGeneratorError as ge:
        safe_err = html.escape(str(ge))
        await status_msg.edit_text(
            f"❌ <b>AI xatoligi:</b>\n\n{safe_err}\n\n"
            "Iltimos, qayta urinib ko'ring yoki boshqa material yuboring.",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="student_menu")]
            ]),
            parse_mode="HTML"
        )
    except Exception as e:
        safe_err = html.escape(str(e))
        await status_msg.edit_text(f"❌ Kutilmagan xatolik: {safe_err}", parse_mode="HTML")


@router.callback_query(F.data == "ai_confirm_save", AITestState.waiting_for_confirm)
async def cb_ai_confirm_save(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    title = data.get("ai_title", "AI Test")
    questions = data.get("ai_questions", [])

    if not questions:
        await callback.answer("Savollar topilmadi!", show_alert=True)
        return

    user_id = callback.from_user.id
    test_id = await db.add_test(title=title, author_id=user_id, questions=questions, time_limit_minutes=15)

    safe_title = html.escape(title)
    bot_user = await callback.bot.get_me()
    bot_username = bot_user.username
    test_link = f"https://t.me/{bot_username}?start=test_{test_id}"
    share_url = f"https://t.me/share/url?url={test_link}&text=" + urllib.parse.quote(f"'{title}' testini ishlash uchun havola:")

    await callback.message.edit_text(
        f"🎉 <b>AI Test muvaffaqiyatli saqlandi!</b>\n\n"
        f"📌 <b>Test nomi:</b> {safe_title}\n"
        f"🔢 <b>Savollar soni:</b> {len(questions)} ta\n"
        f"⏱ <b>Standart vaqt:</b> 15 daqiqa\n"
        f"🆔 <b>Test ID:</b> #{test_id}\n\n"
        f"🔗 <b>Talabalarga yuborish uchun havola:</b>\n"
        f"<code>{test_link}</code>\n\n"
        f"<i>💡 Havolani talabalaringizga yuboring va ular testni to'g'ridan-to'g'ri topshirishlari mumkin!</i>",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📤 Guruhga ulashish (Share)", url=share_url)],
            [InlineKeyboardButton(text="⏱ Vaqtni sozlash", callback_data=f"admin_time_{test_id}")],
            [InlineKeyboardButton(text="📋 Mening testlarim", callback_data="admin_list_tests")],
            [InlineKeyboardButton(text="🔙 Bosh menyu", callback_data="admin_menu" if is_admin(user_id) else "student_menu")]
        ]),
        parse_mode="HTML"
    )
    await state.clear()


@router.callback_query(F.data == "ai_cancel")
async def cb_ai_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ AI orqali test tuzish bekor qilindi.", parse_mode="HTML")
    await callback.answer()



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
        [InlineKeyboardButton(text="✉️ Talabaga xabar yozish (Bog'lanish)", callback_data=f"test_students_msg_{test_id}")],
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
        st_user_id = r.get("user_id")
        st_uname = r.get("username")

        if st_uname:
            st_link = f'<a href="https://t.me/{st_uname}"><b>{safe_st_name}</b></a> (@{st_uname})'
        elif st_user_id:
            st_link = f'<a href="tg://user?id={st_user_id}"><b>{safe_st_name}</b></a>'
        else:
            st_link = f'<b>{safe_st_name}</b>'

        if idx <= 20:
            leaderboard_lines.append(f"{medal} {st_link} — <b>{score}/{total}</b> ({pct}%) | {grade}")

    avg_pct = round(total_pct / len(results), 1)

    text = (
        f"📊 <b>Test hisoboti: «{safe_title}»</b>\n\n"
        f"🔢 <b>Savollar soni:</b> {test.get('question_count', 0)} ta | ⏱ <b>Vaqt:</b> {time_limit_str}\n"
        f"👥 <b>Jami topshirganlar:</b> {len(results)} nafar\n\n"
        f"🔗 <b>Talabalar uchun test havolasi:</b>\n"
        f"<code>{test_link}</code>\n\n"
        f"🏆 <b>TALABALAR REYTINGI (NATIJALAR):</b>\n"
        + "\n".join(leaderboard_lines) + "\n\n"
        f"<i>💡 Talabaning profiliga kirish uchun uning ismi ustiga bosing yoki '✉️ Talabaga xabar yozish' tugmasidan foydalaning.</i>\n\n"
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


@router.callback_query(F.data.startswith("test_students_msg_"))
@router.callback_query(F.data.startswith("test_students_"))
async def cb_list_students_for_msg(callback: CallbackQuery):
    user_id = callback.from_user.id
    raw = callback.data.replace("test_students_msg_", "").replace("test_students_", "")
    try:
        test_id = int(raw)
    except Exception:
        await callback.answer("Noto'g'ri test ID!", show_alert=True)
        return

    test, results = await db.get_test_results_summary(test_id, author_id=user_id)
    if not test or not results:
        await callback.answer("Hozircha natijalar mavjud emas!", show_alert=True)
        return

    safe_title = html.escape(test["title"])
    text = (
        f"✉️ <b>«{safe_title}» — Talabalarga xabar yuborish</b>\n\n"
        f"Ushbu bo'lim orqali talabangizning Telegramida username bo'lmasa ham, unga bot orqali to'g'ridan-to'g'ri xabar, tushuntirish yoki baho yuborishingiz mumkin.\n\n"
        f"<i>Xabar yozmoqchi bo'lgan talabangizni tanlang:</i>"
    )

    kb_rows = []
    for idx, r in enumerate(results[:25], start=1):
        st_name = r.get("full_name", "Talaba")
        st_uid = r.get("user_id")
        st_uname = r.get("username")
        tag = f" (@{st_uname})" if st_uname else ""
        btn_text = f"👤 {idx}. {st_name[:20]}{tag}"
        kb_rows.append([InlineKeyboardButton(text=btn_text, callback_data=f"msg_student_{st_uid}_{test_id}")])

    kb_rows.append([InlineKeyboardButton(text="🔙 Test hisobotiga qaytish", callback_data=f"test_report_{test_id}")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("msg_student_"))
async def cb_start_msg_to_student(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("_")
    student_id = int(parts[2])
    test_id = int(parts[3]) if len(parts) > 3 else 0

    student = await db.get_user(student_id)
    st_name = html.escape(student.get("full_name", "Talaba") if student else "Talaba")
    st_uname = student.get("username") if student else None

    await state.set_state(TeacherMessageState.waiting_for_message)
    await state.update_data(target_student_id=student_id, target_test_id=test_id, student_name=st_name)

    uname_info = f"@{st_uname}" if st_uname else "<i>(o'rnatilmagan)</i>"

    kb_rows = []
    if st_uname:
        kb_rows.append([InlineKeyboardButton(text="💬 Telegram profili", url=f"https://t.me/{st_uname}")])
    kb_rows.append([InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_teacher_msg")])

    text = (
        f"✉️ <b>Talabaga xabar yuborish</b>\n\n"
        f"👤 <b>Talaba:</b> <b>{st_name}</b>\n"
        f"📱 <b>Username:</b> {uname_info}\n"
        f"🆔 <b>Telegram ID:</b> <code>{student_id}</code>\n\n"
        f"✍️ <i>Ushbu talabaga yubormoqchi bo'lgan xabaringizni yozing yoki fayl/ovoz yuboring:</i>\n"
        f"Xabaringiz bot orqali talabaga zudlik bilan yetkaziladi va u sizga bevosita javob qaytara oladi."
    )
    await callback.message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_rows), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cancel_teacher_msg")
async def cb_cancel_teacher_msg(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("❌ Xabar yuborish bekor qilindi.")
    await callback.answer()


@router.message(TeacherMessageState.waiting_for_message)
async def process_teacher_message_to_student(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    student_id = data.get("target_student_id")
    test_id = data.get("target_test_id", 0)
    student_name = data.get("student_name", "Talaba")
    await state.clear()

    if not student_id:
        await message.answer("⚠️ Talaba topilmadi.")
        return

    teacher_name = html.escape(message.from_user.full_name or "O'qituvchi")

    student_kb_rows = [
        [InlineKeyboardButton(text="✍️ O'qituvchiga javob yozish", callback_data=f"reply_teacher_{message.from_user.id}")]
    ]
    st_kb = InlineKeyboardMarkup(inline_keyboard=student_kb_rows)

    header_text = (
        f"👨‍🏫 <b>O'qituvchingizdan yangi xabar!</b>\n"
        f"👤 <b>O'qituvchi:</b> <b>{teacher_name}</b>\n\n"
        f"💬 <b>Xabar matni:</b>\n"
    )

    try:
        if message.text:
            await bot.send_message(
                chat_id=student_id,
                text=header_text + message.text + "\n\n<i>(Javob yozish uchun quyidagi 'Javob yozish' tugmasini bosing):</i>",
                reply_markup=st_kb,
                parse_mode="HTML"
            )
        else:
            await bot.send_message(chat_id=student_id, text=header_text, parse_mode="HTML")
            await bot.copy_message(
                chat_id=student_id,
                from_chat_id=message.chat.id,
                message_id=message.message_id,
                reply_markup=st_kb
            )

        back_kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Test hisobotiga qaytish", callback_data=f"test_report_{test_id}" if test_id else "admin_export_excel")]
        ])
        await message.answer(
            f"✅ Xabaringiz <b>{student_name}</b> ga muvaffaqiyatli yetkazildi!\n"
            f"Talaba xabarni qabul qildi va javob yozganda bot sizga yetkazadi.",
            reply_markup=back_kb,
            parse_mode="HTML"
        )
    except Exception as e:
        await message.answer(f"⚠️ Xabarni yetkazishda xatolik yuz berdi: {e}")


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
    gemini_key = await db.get_setting("gemini_api_key", "") or config.GEMINI_API_KEY
    gemini_status = "✅ Ulangan" if gemini_key else "❌ Kiritilmagan"
    gemini_preview = f"<code>{gemini_key[:6]}...{gemini_key[-4:]}</code>" if gemini_key else "<i>(yo'q)</i>"

    text = (
        "⚙️ <b>Obuna va Tizim Sozlamalari (Superadmin):</b>\n\n"
        f"💳 <b>1 oylik narx:</b> {price_m} so'm\n"
        f"💳 <b>1 yillik narx:</b> {price_y} so'm\n"
        f"📲 <b>Click rekvizit:</b> <code>{click_det}</code>\n"
        f"🤖 <b>AI API xizmati:</b> {gemini_status} ({gemini_preview})\n\n"
        "O'zgartirish yoki sozlash uchun tanlang:"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ 1 oylik narxni o'zgartirish", callback_data="set_price_month")],
        [InlineKeyboardButton(text="✏️ 1 yillik narxni o'zgartirish", callback_data="set_price_year")],
        [InlineKeyboardButton(text="✏️ Click kartani o'zgartirish", callback_data="set_click_card")],
        [InlineKeyboardButton(text="🔑 AI API kalitini sozlash", callback_data="set_gemini_key")],
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


@router.callback_query(F.data == "set_gemini_key")
async def cb_set_gemini_key(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return
    await state.set_state(AdminState.waiting_for_gemini_key)
    current_key = await db.get_setting("gemini_api_key", "") or config.GEMINI_API_KEY
    key_preview = f"<code>{current_key[:8]}...{current_key[-4:]}</code>" if current_key else "Mavjud emas"

    text = (
        "🔑 <b>AI API Kalitini Sozlash</b>\n\n"
        f"Hozirgi kalit: {key_preview}\n\n"
        "Yangi API kalitni ushbu chatga xabar qilib yuboring:\n"
        "(AI Studio: <a href='https://aistudio.google.com/app/apikey'>aistudio.google.com</a> dan mutlaqo bepul olinadi)"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 Bekor qilish", callback_data="admin_settings")]
    ])
    await callback.message.edit_text(text, reply_markup=kb, parse_mode="HTML", disable_web_page_preview=True)
    await callback.answer()


@router.message(AdminState.waiting_for_gemini_key)
async def process_new_gemini_key(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    key = message.text.strip()
    if len(key) < 15:
        await message.answer("⚠️ API kalit juda qisqa ko'rinmoqda. Iltimos, AI Studio'dan olingan to'liq kalitni yuboring:")
        return

    await db.set_setting("gemini_api_key", key)
    await state.clear()
    await message.answer("✅ <b>AI API kaliti muvaffaqiyatli saqlandi!</b>\nEndi botda AI test yaratuvchi funksiyasi to'liq ishlaydi.", parse_mode="HTML")
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
