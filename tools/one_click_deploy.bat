@echo off
chcp 65001 >nul 2>&1
cd /d "%~dp0"

if not exist "%~dp0one_click_deploy.py" (
    echo one_click_deploy.py が見つかりません。
    echo one_click_deploy.bat と one_click_deploy.py を同じフォルダに置いてください。
    pause
    exit /b 1
)

echo 碁華 ワンクリックデプロイを起動中...
python "%~dp0one_click_deploy.py"
if errorlevel 1 (
    echo.
    echo エラーが発生しました。
    pause
)
