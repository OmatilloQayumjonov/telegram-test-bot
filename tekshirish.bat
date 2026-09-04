@echo off
cd /d "%~dp0"
echo === GIT TEKSHIRISH ===
if exist .git (
    echo [.git mavjud]
    git remote -v
    git status -s
) else (
    echo [.git TOPILMADI - Repozitoriy ulanmagan]
)
