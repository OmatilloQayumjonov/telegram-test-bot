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
git commit -m "Rasmli va jadvalli savollarni qabul qilish va Telegramda korsatish toliq qoshildi"
git push origin main

echo.
echo ======================================================
echo    Muvaffaqiyatli yuklandi!
echo    Render.com avtomatik ravishda yangilanmoqda (1-2 daqiqa).
echo ======================================================
pause
