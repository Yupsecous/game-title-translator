# Changelog

All notable changes to the OCR Translator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.0.0] - 2025-07-07

### Added
- **Gemini 2.5 Flash-Lite Integration**: Revolutionary AI-powered translation with advanced context awareness and cost-effectiveness
  - Context-aware translation with configurable sliding window (0-2 previous subtitles) for narrative coherence
  - Intelligent OCR error correction that automatically fixes garbled input text
  - Exceptional cost-effectiveness: translate massive projects like The Witcher 3 for under $5
  - Built-in real-time cost tracking with token usage analytics and cumulative cost monitoring
  - Detailed API call logging with complete transparency (`Gemini_API_call_logs.txt`)
  - Advanced file caching system (`gemini_cache.txt`) for reduced API costs
  - Superior translation quality with context understanding for dialogue flow and character consistency
- **DeepL Free Usage Tracker**: Monitor your monthly free quota consumption with real-time tracking in the Settings tab
  - Displays current usage against the 500,000 character monthly limit for DeepL API Free accounts
  - Helps users optimize their free tier usage and avoid unexpected charges

### Changed
- Enhanced translation provider selection with Gemini API as the recommended default option
- Improved cost monitoring and usage analytics across all translation services
- Updated user interface to accommodate new Gemini-specific configuration options

### Fixed
- N/A

### Removed
- N/A

## [1.1.0] - 2025-06-26

### Added
- MarianMT English-to-Polish language pair support: Downloads model from Tatoeba repository and converts it using the official conversion script, as this model is unavailable on Hugging Face
- Batch mode translation for MarianMT multi-sentence processing: Replaces multi-threading approach with native batch processing for improved performance

### Changed
- MarianMT translation architecture: Switched from multi-threaded sentence processing to efficient batch processing, providing faster translation, lower memory usage, reduced CPU overhead, and better GPU utilization while maintaining identical translation quality

### Fixed
- N/A

### Removed
- N/A

## [1.0.0] - 2025-06-20

### Added
- Initial public release
- Three translation methods: Google Translate API, DeepL API, and MarianMT
- Customisable source and target overlay windows
- Real-time OCR and translation
- Multiple image preprocessing modes
- Adjustable OCR confidence and stability thresholds
- Translation caching to improve performance
- Keyboard shortcuts for common actions
- Comprehensive logging and debugging features

### Fixed
- N/A (initial release)

### Changed
- N/A (initial release)

### Removed
- N/A (initial release)
