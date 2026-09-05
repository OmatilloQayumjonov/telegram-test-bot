@echo off
cd /d "%~dp0"
git add -A
git commit -m "24/7 Keep-Alive self ping va uzluksiz avto-qayta ulanish loopi qoshildi"
git push origin main
