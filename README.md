# 🎓 Telegram Test Boti (O'qituvchi va Talabalar uchun)

Ushbu bot o'qituvchilarga Word (`.docx`) formatidagi testlarni izohi bilan yuklash, talabalarga esa ism-familiyasini kiritib testlarni yechish imkonini beradi. Barcha savollar nusxalash va skrinshot qilishdan himoyalangan (`protect_content=True`), natijalar esa real vaqtda o'qituvchiga yuboriladi va Excel jadvalida saqlanadi.

---

## 🚀 Asosiy Imkoniyatlari

1. **Word (`.docx`) fayldan avtomatik test yaratish**:
   - O'qituvchi botga Word faylni yuboradi.
   - Bot har bir savol, A, B, C, D variantlari, to'g'ri javob kaliti va izohlarni avtomatik ajratib oladi.
2. **Talabalar ro'yxatdan o'tishi**:
   - Talaba birinchi marta kirganda Ism va Familiyasini kiritadi.
   - Keyingi safar avtomatik taniydi.
3. **🔒 Nusxa olish va Skrinshotdan himoya**:
   - Telegramning rasmiy `protect_content=True` mexanizmi qo'llangan.
   - Savollarni boshqa shaxslarga uzatish (Forward) bloklangan.
   - Matndan nusxa olish (Copy) taqiqlangan.
   - Mobil qurilmalarda (Android) Telegram ilovasida skrinshot olish to'liq cheklangan (qora ekran yoki xavfsizlik cheklovi).
4. **📊 Natijalar va O'qituvchi nazorati**:
   - Talaba testni yakunlagach, natijasi darhol o'qituvchiga Telegram orqali xabar qilinadi.
   - Talaba xato qilgan savollari va ularning izohlarini ko'rishi mumkin.
   - O'qituvchi istalgan vaqtda barcha natijalarni Excel (.xlsx) formatida yuklab oladi.

---

## 🛠 O'rnatish va Ishga tushirish

### 1. Bog'liqliklarni o'rnatish
Buyruqlar qatorida (Terminal yoki CMD) quyidagi buyruqni bajaring:

```bash
pip install -r requirements.txt
```

### 2. Sozlamalarni kiritish (.env fayli)
Loyiha papkasida `.env` faylini yarating (yoki `.env.example` dan nusxa oling) va quyidagi ma'lumotlarni kiriting:

```env
# Telegram Bot Token (@BotFather dan olinadi)
BOT_TOKEN=7777777777:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# O'qituvchi (admin) Telegram ID raqami (masalan: 123456789)
# ID raqamingizni Telegramdagi @userinfobot orqali bilishingiz mumkin
ADMIN_IDS=123456789

# Ma'lumotlar bazasi
DATABASE_PATH=data/bot.db
```

### 3. Tizimni sinab ko'rish
Dastur to'g'ri ishlashini tekshirish uchun test skriptini ishga tushiring:

```bash
python verify_system.py
```

### 4. Botni ishga tushirish
```bash
python main.py
```

---

## 📄 Word (.docx) Fayl Formati

Word faylida savollarni quyidagi qulay ko'rinishda yozishingiz mumkin:

```text
1. O'zbekiston poytaxti qaysi shahar?
A) Samarqand
B) Toshkent
C) Buxoro
D) Xiva
Javob: B
Izoh: Toshkent shahri O'zbekiston Respublikasining poytaxti hisoblanadi.

2. 2 + 2 = ?
A) 3
*B) 4
C) 5
D) 6
Izoh: 2 ga 2 ni qo'shganda 4 bo'ladi.
```

> **Eslatma:** To'g'ri javobni `Javob: B` deb yozishingiz yoki to'g'ri variant harfi oldiga `*` yoki `+` qo'yishingiz mumkin (masalan: `*B)`). Izoh yozish ixtiyoriy (`Izoh: ...`).

Namunaviy faylni botning o'zidan `/admin` -> "Namunaviy Word fayl" tugmasi orqali ham yuklab olishingiz mumkin.

---

## 📱 Botdan Foydalanish

### O'qituvchi uchun:
- Botga `/admin` buyrug'ini yuboring.
- **Yangi test yuklash**: `.docx` faylingizni botga yuboring.
- **Natijalar**: "Natijalarni yuklab olish (Excel)" tugmasini bosib, barcha talabalar ballari yozilgan chiroyli jadvalni oling.
- **Testlarni boshqarish**: Testlarni faol/nofaol qilish yoki o'chirish.

### Talaba uchun:
- Botga kirib `/start` tugmasini bosadi.
- Ism va familiyasini kiritadi (masalan: *Aliyev Vali*).
- Mavjud testlardan birini tanlaydi va bittalab javob beradi.
- Test yakunida o'z balli va foizini ko'radi, xatolari bo'yicha izohlarni tahlil qiladi.
