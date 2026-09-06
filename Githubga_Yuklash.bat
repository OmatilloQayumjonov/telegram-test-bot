@echo off
chcp 65001 >nul
title GitHub ga yuklash
color 0B

echo ======================================================
echo    Telegram Bot fayllarini GitHub ga yuklash
echo ======================================================
echo.

cd /d "%~dp0"

git add -A
git commit -m "Gemini 3.6-flash/3.7-flash integratsiyasi, rasmli savollarni kiritish va talaba ism-familiyasini natijalarda ko'rsatish to'liq yangilandi"
git push origin main

echo.
echo ======================================================
echo    Muvaffaqiyatli yuklandi!
echo    Render.com avtomatik ravishda yangilanmoqda (1-2 daqiqa).
echo ======================================================
pause
