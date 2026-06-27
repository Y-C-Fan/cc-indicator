@echo off
REM Create a venv in D:\aaa4claude\cc-indicator\venv, install PySide6 into it,
REM register hooks. Everything stays on D: drive (no C-drive package install).
setlocal
cd /d "%~dp0"

echo === 1/3  Creating venv (D-drive) ===
if not exist "venv\Scripts\python.exe" (
    python -m venv venv
    if errorlevel 1 (
        echo [!] venv 创建失败。确保 PATH 里有 python。
        pause
        exit /b 1
    )
)

echo.
echo === 2/3  Installing PySide6 into venv ===
"venv\Scripts\python.exe" -m pip install --upgrade pip -i https://pypi.tuna.tsinghua.edu.cn/simple >nul 2>&1
"venv\Scripts\python.exe" -m pip install PySide6 -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [!] PySide6 安装失败。手动跑：
    echo     venv\Scripts\python.exe -m pip install PySide6
    pause
    exit /b 1
)

echo.
echo === 3/3  Registering hooks in %%USERPROFILE%%\.claude\settings.json ===
"venv\Scripts\python.exe" install_hooks.py
if errorlevel 1 (
    pause
    exit /b 1
)

echo.
echo 装好了。运行 start.bat 启动悬浮窗（无黑窗口）。
echo （要卸 hooks: venv\Scripts\python.exe install_hooks.py --remove）
pause
