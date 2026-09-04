@echo off
chcp 65001 >nul
title GitHub ga yuklash
color 0B

echo ======================================================
echo    Telegram Bot fayllarini GitHub ga yuklash
echo ======================================================
echo.

cd /d "%~dp0"

git add .
git commit -m "Har bir test uchun alohida Excel hisoboti, jonli reyting va maxsus havolalar yangilandi"
git push origin main || git push origin master

echo.
echo ======================================================
echo    Agar 'Muvaffaqiyatli' yozuvi chiqqan bo'lsa, Render
echo    avtomatik ravishda yangilanadi (1-2 daqiqa kuting)!
echo ======================================================
pause
