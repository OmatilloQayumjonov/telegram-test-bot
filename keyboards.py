from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

MAIN_MENU_BUTTONS = [
    "📝 Mavjud Testlar",
    "🔗 Test havolalari",
    "👨‍🏫 O'qituvchi bo'limi",
    "📊 Excel hisobot",
    "👑 Admin Paneli",
    "⚙️ Obuna va To'lovlar",
    "💳 Obuna sotib olish",
    "✏️ Ismni o'zgartirish"
]


def get_admin_reply_keyboard() -> ReplyKeyboardMarkup:
    """Asosiy admin uchun pastki doimiy menyu tugmalari"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Mavjud Testlar"), KeyboardButton(text="🔗 Test havolalari")],
            [KeyboardButton(text="👨‍🏫 O'qituvchi bo'limi"), KeyboardButton(text="📊 Excel hisobot")],
            [KeyboardButton(text="👑 Admin Paneli"), KeyboardButton(text="⚙️ Obuna va To'lovlar")],
            [KeyboardButton(text="✏️ Ismni o'zgartirish")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def get_student_reply_keyboard() -> ReplyKeyboardMarkup:
    """Oddiy talaba va o'qituvchilar uchun pastki doimiy menyu tugmalari"""
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📝 Mavjud Testlar"), KeyboardButton(text="🔗 Test havolalari")],
            [KeyboardButton(text="👨‍🏫 O'qituvchi bo'limi"), KeyboardButton(text="📊 Excel hisobot")],
            [KeyboardButton(text="💳 Obuna sotib olish"), KeyboardButton(text="✏️ Ismni o'zgartirish")]
        ],
        resize_keyboard=True,
        is_persistent=True
    )


def get_admin_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📥 Yangi test yaratish / yuklash", callback_data="teacher_upload_test")],
        [InlineKeyboardButton(text="📋 Barcha testlar ro'yxati", callback_data="admin_list_tests")],
        [InlineKeyboardButton(text="📊 Natijalarni yuklab olish (Excel)", callback_data="admin_export_excel")],
        [InlineKeyboardButton(text="⚙️ Obuna va To'lov sozlamalari", callback_data="admin_settings")],
        [InlineKeyboardButton(text="📄 Namunaviy Word fayl", callback_data="admin_get_sample")]
    ])


def get_test_creation_keyboard(back_callback: str = "teacher_cabinet") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📄 Word (.docx) orqali yuklash", callback_data="create_test_docx")],
        [InlineKeyboardButton(text="📑 PDF (.pdf) orqali yuklash", callback_data="create_test_pdf")],
        [InlineKeyboardButton(text="✍️ Botda qo'lda kiritish (Matn + Rasm)", callback_data="create_test_manual")],
        [InlineKeyboardButton(text="🤖 AI orqali test tuzish (Matn, Rasm, Doc, PDF)", callback_data="create_test_ai")],
        [InlineKeyboardButton(text="🔙 Orqaga", callback_data=back_callback)]
    ])

