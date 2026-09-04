@echo off
chcp 65001 > nul
title Telegram Test Boti
color 0A

echo ======================================================
echo       TELEGRAM TEST BOTI ISHGA TUSHMOQDA...
echo ======================================================
echo.

cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
    py -3 main.py
) else (
    python main.py
)

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ------------------------------------------------------
    echo DIQQAT: Agar 'Conflict: terminated by other getUpdates'
    echo xatosi chiqsa, bot Render.com da ishlab turgan bo'ladi.
    echo Ikkita joyda bir vaqtda ishlatish mumkin emas.
    echo Render dagi yangilanish uchun 'Githubga_Yuklash.bat' ni bosing!
    echo ------------------------------------------------------
)

echo.
pause
