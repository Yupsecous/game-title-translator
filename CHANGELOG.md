# Changelog

All notable changes to the Game-Changing Translator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.5.1] - 2025-08-03

### Fixed
- **Gemini OCR Performance Issue**: Fixed client initialization overhead causing OCR timeout and translation failures
  - Resolved issue where successful OCR results were discarded due to timeout limits
  - Implemented automatic Gemini client initialization for OCR operations using the same proven pattern as translation
  - Ensures reliable OCR-to-translation pipeline for all Gemini OCR operations
- **Tesseract Path Validation Error with Gemini OCR**: Fixed application startup and translation errors when Gemini OCR is selected
  - Resolved "Tesseract path invalid!" error that occurred even when Tesseract was not needed
  - Implemented conditional Tesseract path validation only when Tesseract OCR is actually selected
  - Eliminates unnecessary Tesseract dependency checks during Gemini OCR operations
  - Improves application performance by avoiding redundant Tesseract operations when using Gemini OCR

### Changed
- N/A

### Added
- **About Tab Enhancement**: Added current version number and release date display to the About tab for better version tracking

### Removed
- N/A

## [3.5.0] - 2025-08-01

### Added
- **Multiple Gemini Models Support**: Dynamic configuration system for flexible Gemini model selection
  - CSV-based model configuration (`resources/gemini_models.csv`) for easy customization
  - Separate model selection for OCR and translation operations
  - Support for Gemini 2.0 Flash, Gemini 2.0 Flash-Lite, Gemini 2.5 Flash, and Gemini 2.5 Flash-Lite
  - Dynamic cost management that automatically updates based on selected models
- **Enhanced Model Recommendations**: Performance-optimized model selection guidance
  - Gemini 2.5 Flash-Lite recommended for speed (fast-changing subtitles < 1 second)
  - Gemini 2.0 Flash recommended for superior OCR accuracy and idiomatic translations (longer subtitles)
- **Comprehensive OCR Testing Results**: Detailed model comparison data showing Gemini 2.0 models' superior performance
  - Test results demonstrate significantly better OCR accuracy across multilingual content
  - Evidence-based recommendations for optimal model selection

### Changed
- **API Library Migration**: Upgraded from `google.generativeai` to `google.genai` library for improved performance and stability
- **Optimized Threading**: Enhanced OCR and translation thread performance for faster processing and reduced latency
- **Improved Model Management**: Centralized Gemini model configuration through GeminiModelsManager class
- **Dynamic Model Selection**: Models available in UI dropdowns are now dynamically loaded from CSV configuration

### Fixed
- N/A

### Removed
- N/A

## [3.0.1] - 2025-07-24

### Added
- Enhanced debugging and logging capabilities for better troubleshooting in compiled versions
- Comprehensive library availability detection and import status reporting

### Changed
- **Updated Gemini Model**: Default Gemini model name changed from `gemini-2.5-flash-lite-preview-06-17` to `gemini-2.5-flash-lite` (stable release)
  - Provides enhanced stability and reliability with Google's official stable model
  - Automatic upgrade for existing users upon restart
- Improved error handling and exception reporting throughout the application
- Enhanced PyInstaller compilation configuration for better dependency inclusion

### Fixed
- **Critical DeepL Translation Bug**: Fixed "cannot access local variable 'e'" error that occurred when enabling DeepL translation for the first time
  - Previously required disabling and re-enabling translation to work correctly
  - Now works correctly on first attempt without workarounds
- **MarianMT Compilation Issue**: Resolved missing MarianMT translation model in compiled version
  - MarianMT was missing from Translation Model dropdown in compiled applications
  - Fixed by including `unittest.mock` dependency required by transformers library
  - MarianMT now properly available in both Python and compiled versions

### Removed
- N/A

## [3.0.0] - 2025-07-20

### Added
- **Gemini OCR - Premium Text Recognition**: Revolutionary AI-powered OCR using Gemini 2.5 Flash-Lite model for superior accuracy in challenging subtitle scenarios
  - Exceptional OCR quality with outstanding cost-to-quality ratio (~$0.00004 per screenshot)
  - 37.5 times more cost-effective than Google Cloud Vision API while delivering superior results
  - Handles complex backgrounds, low-contrast text, stylized fonts, and motion blur that confuse traditional OCR
  - Unique gaming translation solution combining premium AI OCR with real-time subtitle translation
- **API Usage Monitoring Tab**: Comprehensive cost tracking and usage analytics for all API services
  - Real-time cost monitoring for Gemini OCR and Translation services
  - Detailed statistics with rough cost estimates and performance metrics
  - Export functionality for usage data (CSV/TXT formats)
  - DeepL free usage tracking integration
- **Extended Context Window**: Expanded sliding history window support from 2 to 5 previous subtitles
  - Enhanced narrative coherence and grammatical consistency for longer conversations
  - Improved support for Asian languages that rely heavily on contextual understanding
  - Better pronoun resolution and character voice consistency

### Changed
- Enhanced OCR model selection with Gemini API as premium option alongside traditional Tesseract OCR
- Improved translation context awareness with configurable sliding window (0-5 previous subtitles)
- Updated user interface to accommodate new Gemini OCR configuration options and API usage monitoring

### Fixed
- N/A

### Removed
- N/A

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
