@echo off
REM Force-quit the indicator (kills the pythonw running indicator.py).
taskkill /f /im pythonw.exe >nul 2>&1
echo done.
