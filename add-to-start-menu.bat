@echo off
REM Create a Start Menu shortcut for cc-indicator so it shows up in
REM Windows search, "All apps", and can be right-click → "Pin to Start".
setlocal
cd /d "%~dp0"

set "VBS=%TEMP%\cc-indicator-mklnk.vbs"
> "%VBS%" echo Set s = CreateObject("WScript.Shell")
>> "%VBS%" echo target = s.SpecialFolders("Programs") ^& "\cc-indicator.lnk"
>> "%VBS%" echo Set lnk = s.CreateShortcut(target)
>> "%VBS%" echo lnk.TargetPath = "%~dp0cc-indicator.bat"
>> "%VBS%" echo lnk.WorkingDirectory = "%~dp0"
>> "%VBS%" echo lnk.Description = "Claude Code session indicator (floating dots)"
>> "%VBS%" echo lnk.WindowStyle = 7
>> "%VBS%" echo lnk.Save
>> "%VBS%" echo WScript.Echo "shortcut: " ^& target

cscript //nologo "%VBS%"
del "%VBS%"

echo.
echo 完事。打开开始菜单搜 cc-indicator 就能找到。
echo 想要在开始屏幕磁贴里看到：搜到后右键 → 固定到 "开始" 屏幕。
pause
