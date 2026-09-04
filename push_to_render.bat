@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo [1] Git repozitoriyni tekshirish...
if not exist .git (
    echo [.git yaratilmoqda...]
    git init
)

git config user.name "OmatilloQayumjonov"
git config user.email "omatillo@example.com"
git branch -M main

echo [2] Remote URL ni ulash...
git remote remove origin 2>nul
git remote add origin https://github.com/OmatilloQayumjonov/telegram-test-bot.git

echo [3] O'zgarishlarni qo'shish va commit qilish...
git add .
git commit -m "Har bir test uchun alohida Excel hisoboti, jonli reyting va maxsus havolalar to'liq yangilandi"

echo [4] GitHub ga yuklash (push)...
git push -u origin main

if %ERRORLEVEL% NEQ 0 (
    echo [Eslatma: Agar push rad etilgan bo'lsa, force push qilinmoqda...]
    git push -u origin main --force
)

echo.
echo ======================================================
echo    YUKLASH YAKUNLANDI!
echo ======================================================
