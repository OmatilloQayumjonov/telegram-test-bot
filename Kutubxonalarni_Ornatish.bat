@echo off
chcp 65001 > nul
title Kutubxonalarni o'rnatish
color 0B

echo ======================================================
echo    BOG'LIQ KUTUBXONALAR O'RNATILMOQDA...
echo ======================================================
echo.

py -3 -m pip install -r requirements.txt

echo.
echo ======================================================
echo       O'RNATISH YAKUNLANDI!
echo ======================================================
echo Endi Ishga_Tushirish.bat ni bosib botni yoqishingiz mumkin.
echo.
pause
