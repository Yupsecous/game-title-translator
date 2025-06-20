# OCR Translator
Copyright (C) 2025 Tomasz Kamiński

![OCR Translator Logo](docs/screenshots/readme_screen.jpg)

## Overview

OCR Translator is a powerful desktop application that automatically captures text from any area of your screen, performs optical character recognition (OCR), and translates the text in real-time. It creates floating overlay windows that can be positioned anywhere on your screen, making it perfect for translating games, videos, PDFs, or any application with text that you can't easily copy and paste.

This project was inspired by a family member who was learning French by playing games with French subtitles and needed real-time translation. I hope it will be useful both for gamers and non-gamers alike for casual on-screen translations, whether you're learning a new language through entertainment or simply need to understand content in a foreign language.

This application was developed or rather vibe-coded with the support of the following AI models: Claude 3.7 Sonnet, Claude Sonnet 4 and Gemini 2.5 Pro.


## Key Features

- **Screen Area Selection**: Define custom regions for text capture and translation display
- **Real-time Translation**: Automatically detects and translates text as it changes
- **Multiple Translation Engines**:
  - Google Translate API
  - DeepL API
  - MarianMT (offline neural machine translation) - available as "MarianMT offline and free"
- **Multilingual User Interface**: Full support for English and Polish interface languages
- **Floating Overlays**: Translucent, movable windows that stay on top of other applications
- **Customizable Appearance**: Adjust colours, fonts, and transparency
- **Image Preprocessing**: Various modes to improve OCR accuracy
- **Hotkey Support**: Control the application without switching windows
- **Translation Caching**: Reduce API calls and improve performance
- **Polish Language Support**: Proper alphabetical sorting and language selection for Polish users
- **Improved Organization**: All configuration files and language resources are now organized in the `resources/` directory for better structure and maintainability

## Ready-to-Use Compiled Version

**🎮 Perfect for Gamers and Non-Technical Users!**

If you want to start using OCR Translator immediately without installing Python or dealing with dependencies, we've prepared ready-to-use compiled versions for you:

### Quick Start Options

**📥 [Download from Releases](https://github.com/tomkam1702/OCR-Translator/releases)**

Choose your version:
- **GPU-Enabled Version** (~1.34 GB) - For users with NVIDIA graphics cards, provides faster offline translation
- **CPU-Only Version** (~182 MB) - For all other users, smaller download size

### Simple Installation Steps

1. **Download** the required files for your chosen version from the [Releases page](https://github.com/tomkam1702/OCR-Translator/releases):
   - **GPU Version**: Download ALL 3 files (.7z.001, .7z.002, and .exe)
   - **CPU Version**: Download BOTH files (.7z.001 and .exe)
2. **Run** the .exe installer file
3. **Install Tesseract OCR** (one-time requirement) - [Download here](https://github.com/UB-Mannheim/tesseract/wiki)
4. **Run** `OCRTranslator.exe` from the installed folder
5. **Start translating!** 🚀

### Need Help?

📖 **Installation Guides:**
- [English Installation Guide](https://tomkam1702.github.io/OCR-Translator/docs/installation.html)
- [Polish Installation Guide](https://tomkam1702.github.io/OCR-Translator/docs/installation_pl.html)

The compiled versions include everything you need - no Python installation required!

## Installation

### Prerequisites

- Windows operating system
- [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) installed
- Python 3.7 or newer

### Setup

1. Clone this repository:
   ```
   git clone https://github.com/tomkam1702/OCR-Translator.git
   ```

2. Install required Python packages:
   ```
   pip install -r requirements.txt
   ```

3. Run the application:
   ```
   python main.py
   ```

For detailed installation instructions, see the [Installation Guide](https://tomkam1702.github.io/OCR-Translator/docs/installation.html).

## Quick Start

1. Launch the application
2. Click "Select Source Area (OCR)" and drag to select the text area you want to translate
3. Click "Select Target Area (Translation)" and drag to select where you want the translation to appear
4. Configure your preferred translation method in the Settings tab
5. Click "Start" to begin translation
6. Press the `~` key to toggle translation on/off

For more detailed usage instructions, see the [User Manual](https://tomkam1702.github.io/OCR-Translator/docs/user-manual.html).

## Documentation

- **User Manual** 
  - [English](https://tomkam1702.github.io/OCR-Translator/docs/user-manual.html) 
  - [Polish](https://tomkam1702.github.io/OCR-Translator/docs/user-manual_pl.html)
- **Installation Guide** 
  - [English](https://tomkam1702.github.io/OCR-Translator/docs/installation.html) 
  - [Polish](https://tomkam1702.github.io/OCR-Translator/docs/installation_pl.html)
- **OCR Translator Gallery**
  - [English](https://tomkam1702.github.io/OCR-Translator/docs/gallery.html)
  - [Polish](https://tomkam1702.github.io/OCR-Translator/docs/gallery_pl.html)
- **Troubleshooting** 
  - [English](docs/troubleshooting.md)
- **Developer Guide** 
  - [English](docs/developer-guide.md)

## Development Status

This project is considered feature-complete. Small changes may or may not be made in the future, but generally no active development is planned. If you wish to add features or make changes, the best approach is to fork the repository and develop it further yourself.

## Licence

This project is free software, licensed under the GNU General Public Licence version 3 (GPLv3).

You can:
- Use the software for any purpose
- Change the software to suit your needs
- Share the software and your changes with others

This program is distributed in the hope that it will be useful, but WITHOUT ANY WARRANTY. See the [LICENCE](LICENSE) file for complete details.

## Acknowledgments

- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract)
- [MarianMT](https://huggingface.co/docs/transformers/model_doc/marian)
- [Google Cloud Translation API](https://cloud.google.com/translate)
- [DeepL API](https://www.deepl.com/pro-api)
- Developed with the support of the following AI models: Claude 3.7 Sonnet, Claude Sonnet 4 and Gemini 2.5 Pro


## Contributing

Please note that this project is considered feature-complete. If you wish to make substantial changes, please consider forking the repository instead.

> **⚠️ FORKING NOTICE**: This project requires attribution to the original author. Please read [ATTRIBUTION.md](ATTRIBUTION.md) before forking or using this code.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Attribution Required](https://img.shields.io/badge/Attribution-Required-red.svg)](ATTRIBUTION.md)
[![Original Author](https://img.shields.io/badge/Original%20Author-Tomasz%20Kamiński-green.svg)](https://github.com/tomkam1702)
