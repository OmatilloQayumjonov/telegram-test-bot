from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton


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
        [InlineKeyboardButton(text="📥 Yangi test yuklash (.docx)", callback_data="admin_upload_test")],
        [InlineKeyboardButton(text="📋 Barcha testlar ro'yxati", callback_data="admin_list_tests")],
        [InlineKeyboardButton(text="📊 Natijalarni yuklab olish (Excel)", callback_data="admin_export_excel")],
        [InlineKeyboardButton(text="⚙️ Obuna va To'lov sozlamalari", callback_data="admin_settings")],
        [InlineKeyboardButton(text="📄 Namunaviy Word fayl", callback_data="admin_get_sample")]
    ])
