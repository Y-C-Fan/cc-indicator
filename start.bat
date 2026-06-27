@echo off
REM Launch the indicator from the bundled venv (no console window).
cd /d "%~dp0"
start "" "venv\Scripts\pythonw.exe" indicator.py
