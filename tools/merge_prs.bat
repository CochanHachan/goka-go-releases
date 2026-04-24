@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if not exist "%~dp0merge_prs.py" (
    echo merge_prs.py が見つかりません。
    echo merge_prs.bat と merge_prs.py を同じフォルダに置いてください。
    pause
    exit /b 1
)

echo merge_prs.py を起動中...
python "%~dp0merge_prs.py"
if errorlevel 1 (
    echo.
    echo エラーが発生しました。
    pause
)
