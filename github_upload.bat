@echo off
echo ======================================
echo   OCR Translator GitHub Upload
echo ======================================
echo.

cd /d "D:\Crypto\CCXT\Claude\OCR_Translator_GitHub_RELEASE"
echo Current directory: %CD%
echo.

echo Step 1: Initializing Git repository...
git init
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to initialize Git repository
    pause
    exit /b 1
)

echo.
echo Step 2: Configuring Git user (if needed)...
git config user.name "tomkam1702" 2>nul
git config user.email "tomkam1702@users.noreply.github.com" 2>nul

echo.
echo Step 3: Adding all files...
git add .
if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to add files
    pause
    exit /b 1
)

echo.
echo Step 4: Creating initial commit...
git commit -m "Initial release of OCR Translator v1.0.0

Complete OCR and translation tool featuring:
- Support for Google Translate, DeepL, and MarianMT
- Real-time floating overlay windows  
- Multi-language OCR with Tesseract
- Comprehensive documentation and examples
- Easy installation and compilation tools

This release includes all core functionality, complete documentation,
language resources, and build tools for easy deployment."

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: Failed to create commit
    pause
    exit /b 1
)

echo.
echo Step 5: Setting up remote repository...
git branch -M main
git remote add origin https://github.com/tomkam1702/OCR-Translator.git
if %ERRORLEVEL% NEQ 0 (
    echo Note: Remote origin may already exist, continuing...
)

echo.
echo Step 6: Pushing to GitHub...
echo This will require GitHub authentication...
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ======================================
    echo   SUCCESS! Upload Complete!
    echo ======================================
    echo.
    echo Your OCR Translator is now live on GitHub!
    echo Repository: https://github.com/tomkam1702/OCR-Translator
    echo.
) else (
    echo.
    echo ======================================
    echo   Authentication Required
    echo ======================================
    echo.
    echo Please authenticate with GitHub and run:
    echo git push -u origin main
    echo.
)

echo Press any key to continue...
pause >nul
