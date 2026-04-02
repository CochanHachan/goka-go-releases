@echo off
set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set VERSION=1.0.0
set BUILDDIR=%~dp0build
set DISTDIR=%~dp0dist\goka_go

echo [STEP 0] Cleaning old build files...
if exist "%BUILDDIR%" (
    rmdir /s /q "%BUILDDIR%"
    echo [OK] build\ deleted
)
if exist "%DISTDIR%" (
    rmdir /s /q "%DISTDIR%"
    echo [OK] dist\goka_go\ deleted
)

echo [STEP 1] PyInstaller...
pyinstaller goka_go.spec --noconfirm
if errorlevel 1 (
    echo [ERROR] PyInstaller failed
    pause
    exit /b 1
)
echo [OK] dist\goka_go\ created

if not exist "%~dp0dist\installer" mkdir "%~dp0dist\installer"

echo [STEP 2] Inno Setup...
if not exist %ISCC% (
    echo [WARNING] Inno Setup not found: %ISCC%
    pause
    exit /b 1
)
%ISCC% "%~dp0installer\GokaGo_Setup.iss"
if errorlevel 1 (
    echo [ERROR] Inno Setup failed
    pause
    exit /b 1
)

echo.
echo Done: dist\installer\GokaGo_Setup_%VERSION%.exe
pause
