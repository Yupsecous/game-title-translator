# Changelog

All notable changes to the OCR Translator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
