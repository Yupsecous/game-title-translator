# Game-Changing Translator
Copyright © 2025 Tomasz Kamiński

![Game-Changing Translator Logo](docs/screenshots/readme_screen.jpg)

## Overview

Game-Changing Translator is a powerful desktop application that automatically captures text from any area of your screen, performs optical character recognition (OCR), and translates the text in real-time. It creates floating overlay windows that can be positioned anywhere on your screen, making it perfect for translating games, videos, PDFs, or any application with text that you can't easily copy and paste.

This project was inspired by a family member who was learning French by playing games with French subtitles and needed real-time translation. I hope it will be useful both for gamers and non-gamers alike for casual on-screen translations, whether you're learning a new language through entertainment or simply need to understand content in a foreign language.

This application was developed or rather vibe-coded with the support of the following AI models: Claude 3.7 Sonnet, Claude Sonnet 4 and Gemini 2.5 Pro.

## Game-Changing Translator Gallery
  - [English](https://tomkam1702.github.io/OCR-Translator/docs/gallery.html)
  - [Polish](https://tomkam1702.github.io/OCR-Translator/docs/gallery_pl.html)

## Key Features

### 🚀 NEW in Version 3.0.0

- **Gemini OCR - Premium Text Recognition**: Revolutionary AI-powered OCR that delivers exceptional accuracy for challenging subtitle scenarios where traditional OCR engines struggle
  - Superior OCR quality with outstanding cost-to-quality ratio using Gemini 2.5 Flash-Lite model
  - **Challenging Screenshot Examples**: See the dramatic difference in quality:
  
    ![OCR Comparison Example 1](docs/screenshots/ocr_1.png)
    
    **Tesseract OCR Result:** `~ Trust me, OD tite WE loca mS`  
    **Gemini OCR Result:** `Trust me, Oakmonters know a newcomer when they see one. We locals can tell.`
    
    ![OCR Comparison Example 2](docs/screenshots/ocr_2.png)
    
    **Tesseract OCR Result:** `' Paulie: Driv: show, Tom. Next stop's Bi the motel. 7 jj ie`  
    **Gemini OCR Result:** `Paulie: Drive before the cops show, Tom. Next stop's Bill at the motel.`
  
  - **Professional Results**: Handles low-contrast text, stylized fonts, and dynamic backgrounds that confuse traditional OCR
  - **Cost-Effective Excellence**: ~$0.00004 per subtitle screenshot - 37.5 times cheaper than Google Cloud Vision API while delivering superior results
  - **Unique Gaming Translation Solution**: First-of-its-kind integration of premium AI OCR with real-time game subtitle translation
  - **Special Cost Estimation**: Dedicated API Usage tab with rough cost estimates and comprehensive usage monitoring
- **Extended Context Window**: Expanded sliding history window from 2 to 5 previous subtitles for enhanced translation quality
  - **Better Context Awareness**: Improved narrative coherence and grammatical consistency across longer conversations
  - **Enhanced Asian Language Support**: Extended context particularly beneficial for languages that rely heavily on contextual understanding

### 🚀 NEW in Version 2.0.0

- **Gemini 2.5 Flash-Lite Integration**: Revolutionary AI-powered translation with advanced context awareness and cost-effectiveness
  - Context-aware translation with configurable sliding window (0-2 previous subtitles) for narrative coherence
  - Intelligent OCR error correction that automatically fixes garbled input text
  - Exceptional cost-effectiveness: translate massive games like The Witcher 3 for pennies
  - Built-in real-time cost tracking with token usage analytics and cumulative cost monitoring
  - Detailed API call logging with complete transparency (`Gemini_API_call_logs.txt`)
  - Advanced file caching system (`gemini_cache.txt`) for reduced API costs
  - Superior translation quality with context understanding for dialogue flow and character consistency
- **DeepL Free Usage Tracker**: Monitor your monthly free quota consumption with real-time tracking in the Settings tab
  - Displays current usage against the 500,000 character monthly limit for DeepL API Free accounts
  - Helps users optimize their free tier usage

### Core Features

- **Screen Area Selection**: Define custom regions for text capture and translation display
- **Real-time Translation**: Automatically detects and translates text as it changes
- **Multiple Translation Engines**:
  - Gemini 2.5 Flash-Lite API
  - MarianMT (offline neural machine translation)
  - DeepL API
  - Google Translate API
- **Multilingual User Interface**: Full support for English and Polish interface languages
- **Floating Overlays**: Translucent, movable windows that stay on top of other applications
- **Customizable Appearance**: Adjust colours, fonts, and transparency
- **Image Preprocessing**: Various modes to improve OCR accuracy
- **Hotkey Support**: Control the application without switching windows
- **Translation Caching**: Reduce API calls and improve performance

## Ready-to-Use Compiled Version

**🎮 Perfect for Gamers and Non-Technical Users!**

If you want to start using Game-Changing Translator immediately without installing Python or dealing with dependencies, we've prepared a ready-to-use compiled version for you:

### Quick Start Options

**📥 [Download from Releases](https://github.com/tomkam1702/OCR-Translator/releases)**

1. Download both files.
2. Run the .exe installer file to unpack and install the application to your preferred folder.
3. Install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) (one-time requirement).
4. Launch the application by running `GameChangingTranslator.exe` from your installation folder.
5. Experience premium AI OCR and enhanced context translation! 🤖.

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
- **Game-Changing Translator Gallery**
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
