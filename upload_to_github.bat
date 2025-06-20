@echo off
echo.
echo ======================================
echo   OCR Translator GitHub Upload Script
echo ======================================
echo.

set "CLEAN_DIR=D:\Crypto\CCXT\Claude\OCR_Translator_GitHub_RELEASE"
set "REPO_URL=https://github.com/tomkam1702/OCR-Translator.git"

echo This script will:
echo 1. Initialize git repository in clean directory
echo 2. Add all files
echo 3. Set up remote repository
echo 4. Push to GitHub
echo.
echo Make sure you have:
echo - Git installed on your computer
echo - GitHub authentication set up
echo.
pause

cd /d "%CLEAN_DIR%"

echo.
echo Initializing git repository...
git init

echo.
echo Adding all files...
git add .

echo.
echo Creating initial commit...
git commit -m "Initial release of OCR Translator v1.0.0

Complete OCR and translation tool featuring:
- Support for Google Translate, DeepL, and MarianMT
- Real-time floating overlay windows
- Multi-language OCR with Tesseract
- Comprehensive documentation and examples
- Easy installation and compilation tools"

echo.
echo Setting up remote repository...
git branch -M main
git remote add origin %REPO_URL%

echo.
echo Pushing to GitHub...
git push -u origin main

echo.
echo ======================================
echo   Upload Complete!
echo ======================================
echo.
echo Your OCR Translator is now live on GitHub!
echo Repository: %REPO_URL%
echo.
pause
