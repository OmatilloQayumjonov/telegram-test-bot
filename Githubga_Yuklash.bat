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
git commit -m "Tugmachalar qotib qolishi va ishlamay qolish muammosi to'liq hal qilindi (StateFilter, universal middleware va stale callback himoyasi)"
git push origin main

echo.
echo ======================================================
echo    Muvaffaqiyatli yuklandi!
echo    Render.com avtomatik ravishda yangilanmoqda (1-2 daqiqa).
echo ======================================================
pause
