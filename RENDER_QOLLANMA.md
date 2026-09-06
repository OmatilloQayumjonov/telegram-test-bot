# 🌐 Botni Render.com da 24/7 (Doimiy) Ishga Tushirish Qo'llanmasi

Kompyuteringiz o'chiq bo'lsa ham, CMD yopiq bo'lsa ham botingiz to'xtovsiz ishlashi uchun barcha sozlamalar tayyorlandi.

---

## 1-qadam: Kodlarni GitHub ga yuklash

1. [github.com](https://github.com/) saytiga kiring.
2. **"New"** (Yangi repository) tugmasini bosing.
3. Repository nomi: `telegram-test-bot` deb nomlang va **"Create repository"** tugmasini bosing.
4. Ushbu papkadagi fayllarni GitHub ga yuklang:
   - **Oddiy yo'l:** GitHub sahifasida **"uploading an existing file"** tugmasini bosib, barcha fayllarni yuklang.
   - **Yoki Git orqali:**
     ```bash
     git init
     git add .
     git commit -m "Telegram bot ready for render"
     git branch -M main
     git remote add origin https://github.com/SIZNING_PROFILINGIZ/telegram-test-bot.git
     git push -u origin main
     ```

---

## 2-qadam: Render.com da bepul Web Service yaratish

1. [render.com](https://render.com/) saytiga kiring va **"Sign In"** -> **"GitHub"** orqali kiring.
2. Sahifaning tepasidagi ko'k rangli **"New +"** tugmasini bosing va **"Web Service"** ni tanlang.
3. GitHub dagi `telegram-test-bot` loyihangiz yonidagi **"Connect"** tugmasini bosing.

---

## 3-qadam: Sozlamalarni kiritish

Quyidagi maydonlarni to'ldiring:
- **Name:** `test-bot-24-7` (xohlagan nom)
- **Region:** `Frankfurt (EU Central)`
- **Branch:** `main`
- **Runtime:** `Python 3`
- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `python main.py`
- **Instance Type:** `Free` ($0/month)

---

## 4-qadam: Maxfiy Kalitlar (Environment Variables)

Pastdagi **"Environment Variables"** bo'limida quyidagi o'zgaruvchilarni kiriting:
1. `BOT_TOKEN` = `@BotFather bergan maxfiy bot tokeningiz`
2. `ADMIN_IDS` = `1184083915`
3. `DATABASE_PATH` = `data/bot.db`
4. `PYTHON_VERSION` = `3.11.9`

---

## 5-qadam: Ishga tushirish

Pastdagi **"Deploy Web Service"** tugmasini bosing.
- Render barcha kutubxonalarni o'rnatadi.
- Bot uchun maxsus kiritilgan port serveri tufayli Render uni muvaffaqiyatli qabul qiladi: `Your service is live 🎉`.
- Endi kompyuterni bemalol o'chirib qo'yishingiz mumkin, botingiz serverda uzluksiz ishlayveradi!

---

## 💡 Botni hech qachon uxlatmaslik (Keep-Alive):
Render bepul xizmatlari 15 daqiqa hech kim kirmasa uxlab qolmasligi uchun:
1. Render bergan havolani oling (masalan: `https://test-bot-24-7.onrender.com`).
2. [cron-job.org](https://cron-job.org/) saytiga bepul a'zo bo'lib, ushbu havolani har 10 daqiqada bir marta chaqirib (ping) turadigan qilib qo'ysangiz, botingiz 365 kun 24/7 rejimda uyg'oq turadi!
