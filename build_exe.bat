@echo off
pip install pyinstaller --quiet
python -m PyInstaller --noconfirm --onefile --windowed --name "CS2 Robs Farmer" --collect-all customtkinter main.py
echo.
echo EXE criado em: %~dp0dist\CS2 Robs Farmer.exe
pause
