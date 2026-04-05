@echo off
cd /d "%~dp0"
python "%~dp0merge_prs.py"
if errorlevel 1 (
    echo.
    echo エラーが発生しました。上のメッセージを確認してください。
    pause
)
