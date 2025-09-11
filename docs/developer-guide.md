# Developer Guide

This guide provides information for developers who want to understand or modify the Game-Changing Translator application.

> **IMPORTANT NOTE**: This project is considered complete. I won't be accepting pull requests, feature enhancements, or implementing new features that someone else has coded. You are welcome to fork the repository and develop it further as your own project. The code is shared under the GPL licence for others to use, update, and modify as they wish, but I consider my work on it complete and won't be actively engaged in future development.

## Architecture Overview

Game-Changing Translator follows a modular design with the following key components:

### Core Components

1. **Main Application (`app_logic.py`)**
   - Central coordinator that initializes and manages all other components
   - Holds main application state and references to UI elements
   - Delegates specialized tasks to handler classes

2. **Handler Classes (in `handlers/` directory)**
   - `CacheManager` - Manages translation file caching and persistence (Level 2)
   - `ConfigurationHandler` - Manages loading and saving of application settings
   - `DisplayManager` - Handles UI updates for overlays and debug information
   - `GeminiModelsManager` - Manages Gemini model configurations from CSV file
   - `OpenAIModelsManager` - Manages OpenAI model configurations from CSV file
   - `HotkeyHandler` - Manages keyboard shortcuts
   - `StatisticsHandler` - API usage statistics parsing, cost monitoring, and export functionality
   - `TranslationHandler` - Coordinates translation, legacy OCR methods, and non-LLM providers
   - `UIInteractionHandler` - Manages UI interactions and settings

3. **LLM Provider Architecture (in `handlers/` directory)**
   - `LLMProviderBase` - Abstract base class for all LLM-based translation providers
   - `GeminiProvider` - Gemini-specific translation implementation
   - `OpenAIProvider` - OpenAI-specific translation implementation

3. **Worker Threads (`worker_threads.py`)**
   - `run_capture_thread` - Captures screenshots from selected screen areas
   - `run_ocr_thread` - Performs OCR on captured images
   - `run_translation_thread` - Translates OCR text and updates display

4. **UI Components**
   - `gui_builder.py` - Creates the application's tabbed interface
   - `ui_elements.py` - Custom UI components including the overlay windows
   - `overlay_manager.py` - Manages the creation and positioning of overlay windows
   - `language_ui.py` - Manages UI localization for multiple languages

5. **Specialized Modules**
   - `marian_mt_translator.py` - Neural machine translation implementation
   - `convert_marian.py` - HuggingFace conversion script for Tatoeba models (© 2020 The HuggingFace Team, Apache License 2.0)
   - `unified_translation_cache.py` - Unified LRU cache system for all translation providers
   - `ocr_utils.py` - OCR utility functions with adaptive preprocessing
   - `translation_utils.py` - Translation utility functions
   - `rtl_text_processor.py` - Right-to-Left text processing for tkinter widgets (fallback RTL support)
   - `pyside_overlay.py` - PySide6-based RTL translation overlays with native Qt RTL support
   - `language_manager.py` - Language code management and mappings for different translation services
   - `config_manager.py` - Configuration file handling with OCR Preview geometry support
   - `resource_handler.py` - Resource path resolution for packaged applications
   - `resource_copier.py` - Resource management for compiled executables
   - `update_checker.py` - GitHub API integration for automatic update checking
   - `update_applier.py` - Simple update application system with batch file creation
   - `logger.py` - Logging functionality
   - `constants.py` - Application constants and language definitions

### Data Flow

The application uses a pipeline architecture for processing:

1. **Capture** → **OCR** → **Translation** → **Display**

Data flows between stages through thread-safe queues:
- `ocr_queue` - Screenshots from capture thread to OCR thread
- `translation_queue` - OCR text from OCR thread to translation thread

This design allows each stage to operate at its own pace without blocking other stages.

## Code Structure

```
ocr-translator/
├── __init__.py                    # Package initialization
├── main.py                        # Application entry point
├── app_logic.py                   # Main application logic
├── resource_copier.py             # Resource management for compiled executables
├── config_manager.py              # Configuration handling
├── constants.py                   # Constant definitions
├── gui_builder.py                 # GUI building functions
├── handlers/                      # Specialized handler classes
│   ├── __init__.py                # Package initialization
│   ├── cache_manager.py           # Translation cache management
│   ├── configuration_handler.py   # Settings and configuration
│   ├── display_manager.py         # Display and UI updates
│   ├── gemini_models_manager.py   # Gemini model configuration management
│   ├── gemini_provider.py         # Gemini LLM translation provider
│   ├── hotkey_handler.py          # Keyboard shortcuts
│   ├── llm_provider_base.py       # Abstract base class for LLM providers
│   ├── openai_models_manager.py   # OpenAI model configuration management
│   ├── openai_provider.py         # OpenAI LLM translation provider
│   ├── statistics_handler.py      # API usage statistics and cost monitoring
│   ├── translation_handler.py     # Translation coordination and legacy methods
│   ├── translation_handler_backup.py # Backup of original handler before refactoring
│   └── ui_interaction_handler.py  # UI event handling
├── language_manager.py            # Language code management and mapping
├── language_ui.py                 # UI localization support
├── logger.py                      # Logging functionality
├── marian_mt_translator.py        # Neural translation implementation
├── convert_marian.py              # HuggingFace conversion script (© HuggingFace Team)
├── ocr_utils.py                   # OCR utility functions
├── overlay_manager.py             # Overlay window management
├── pyside_overlay.py              # PySide6 RTL translation overlays with native Qt support
├── resource_handler.py            # Resource path resolution
├── rtl_text_processor.py          # RTL text processing for tkinter widgets
├── translation_utils.py           # Translation utilities
├── ui_elements.py                 # Custom UI components
├── unified_translation_cache.py   # Unified LRU cache for all translation providers
├── update_checker.py              # GitHub API integration for automatic update checking
├── update_applier.py              # Simple update application system with batch file creation
└── worker_threads.py              # Worker thread implementations
```

### Configuration and Resource Files

```
ocr-translator/
├── ocr_translator_config.ini      # Application configuration file
└── resources/                     # Resource files directory
    ├── lang_codes.csv             # Generic language name to ISO code mappings
    ├── google_trans_source.csv    # Source language codes for Google Translate API
    ├── google_trans_target.csv    # Target language codes for Google Translate API
    ├── deepl_trans_source.csv     # Source language codes for DeepL API
    ├── deepl_trans_target.csv     # Target language codes for DeepL API
    ├── gemini_trans_source.csv    # Source language codes for Gemini API
    ├── gemini_trans_target.csv    # Target language codes for Gemini API
    ├── gemini_models.csv          # Gemini model configurations (names, API names, costs, availability)
    ├── openai_trans_source.csv    # Source language codes for OpenAI API
    ├── openai_trans_target.csv    # Target language codes for OpenAI API
    ├── openai_models.csv          # OpenAI model configurations (names, API names, costs, availability)
    ├── MarianMT_select_models.csv # Available MarianMT translation models
    ├── MarianMT_models_short_list.csv # Preferred/recommended MarianMT models
    ├── language_display_names.csv # Localized language display names
    ├── gui_eng.csv                # English UI translations
    └── gui_pol.csv                # Polish UI translations
```

### Cache and Data Files

```
ocr-translator/
├── deepl_cache.txt                # Cached translations from DeepL API
├── googletrans_cache.txt          # Cached translations from Google Translate API
├── gemini_cache.txt               # Cached translations from Gemini API
├── openai_cache.txt               # Cached translations from OpenAI API
├── Gemini_API_call_logs.txt       # Detailed Gemini API call logging with cost tracking
├── OpenAI_API_call_logs.txt       # Detailed OpenAI API call logging with cost tracking
├── GEMINI_API_OCR_short_log.txt   # Short log for Gemini OCR API usage statistics
├── GEMINI_API_TRA_short_log.txt   # Short log for Gemini Translation API usage statistics
├── OpenAI_API_TRA_short_log.txt   # Short log for OpenAI Translation API usage statistics
├── marian_models_cache/           # Directory for cached MarianMT models
└── translator_debug.log           # Application debug log file
```

### Build and Setup Files

```
ocr-translator/
├── GameChangingTranslator.spec    # PyInstaller specification (standard CPU version)
├── GameChangingTranslator_GPU.spec # PyInstaller specification (GPU/CUDA optimized)
├── compile_app.py                 # Python compilation utility for building executables
├── setup.py                       # Setup configuration for building executables
├── run_python_compiler.bat        # Windows batch script for compiling the application
├── install_dependencies.bat       # Windows batch script to install dependencies
├── run.bat                        # Windows batch script to run the application
└── requirements.txt               # Python package dependencies
```

### Debug Resources

```
ocr-translator/
└── debug_images/                  # Directory for saving debug images
```

## Key Features and Implementation Details

### Unified Translation Cache Architecture

The application features a sophisticated two-tier caching system that was redesigned to eliminate memory waste and fix cache clearing bugs:

#### Level 1: Unified In-Memory Cache (`unified_translation_cache.py`)
- **Single LRU cache** for all translation providers (Google, DeepL, MarianMT)
- **Thread-safe design** with proper RLock() mechanisms for concurrent access
- **Smart cache key generation** using MD5 hashes and provider-specific parameters
- **Configurable cache size** (default: 1000 entries) with automatic LRU eviction
- **Provider-specific clearing** allows selective cache management

**Key Benefits:**
- ✅ **40-60% memory reduction** from eliminating duplicate cache storage
- ✅ **Fixed cache clearing bugs** - unified system actually clears all cache levels
- ✅ **Consistent behavior** across all translation providers
- ✅ **Better performance** with reduced cache management overhead

#### Level 2: Persistent File Cache (Existing)
- **`deepl_cache.txt`** - DeepL API translations persisted to disk
- **`googletrans_cache.txt`** - Google Translate API translations persisted to disk  
- **MarianMT has no file cache** (offline model, no API costs to optimize)
- **Preserved compatibility** - existing user cache files remain intact

#### Cache Flow:
```
Translation Request
    ↓
🚀 Level 1: Check Unified In-Memory Cache (fast)
    ↓ (cache miss)
💾 Level 2: Check File Cache (for Google/DeepL only)
    ↓ (cache miss)
🌐 Level 3: Call Translation API/Model
    ↓
📝 Store in BOTH Level 1 (unified) AND Level 2 (file cache)
```

#### Previous Problems Solved:
- **Double caching bug**: MarianMT previously had two overlapping LRU caches storing identical data
- **Incomplete cache clearing**: Cache clearing didn't clear all cache levels, leaving stale data
- **Memory waste**: Multiple caches storing the same translations
- **Thread safety issues**: Inconsistent locking mechanisms across different cache implementations

### LLM Provider Architecture

The application features a modular LLM provider architecture that was introduced to separate concerns and improve maintainability for language model-based translation services (Gemini, OpenAI). This refactoring extracted LLM-specific functionality from the monolithic `TranslationHandler` into specialized provider classes.

#### Architecture Overview

The LLM provider system follows a clean inheritance pattern:

```
AbstractLLMProvider (llm_provider_base.py)
├── GeminiProvider (gemini_provider.py)
└── OpenAIProvider (openai_provider.py)
```

#### Abstract Base Class (`llm_provider_base.py`)

The `AbstractLLMProvider` class contains all common functionality shared across LLM providers:

**Session Management:**
- Translation session lifecycle with numbered identifiers
- Automatic session ending when pending calls complete
- Thread-safe call counting and session state management

**Context Window Management:**
- Sliding context window with configurable size (0-2 previous subtitles)
- Unified context string building with identical format across providers
- Language-aware context updates with duplicate detection

**Comprehensive Logging System:**
- Atomic logging with thread safety for complete API call records
- Detailed main logs with request/response content and token analysis
- Concise short logs for statistics and monitoring
- Automatic log file initialization with proper headers

**Client Management:**
- Automatic client refresh based on age (30 minutes) and call count (100 calls)
- Circuit breaker pattern for network degradation detection
- API key change detection and session reset

**Cost Tracking:**
- Efficient memory caching for cumulative totals
- Model-specific cost calculations from CSV configuration
- Real-time cost monitoring and statistics

#### Provider-Specific Implementations

**GeminiProvider (`gemini_provider.py`):**
- Uses Google's Gen AI library with client-based approach
- Supports both thinking and non-thinking modes via `thinking_budget` configuration
- Handles multiple response formats and model types
- Integrated with `GeminiModelsManager` for dynamic model configuration

**OpenAIProvider (`openai_provider.py`):**
- Supports both Chat Completions API and Responses API
- Handles GPT-5 models (Responses API) and GPT-4.1 models (Chat Completions API)
- Configurable reasoning effort and verbosity for GPT-5 models
- Integrated with `OpenAIModelsManager` for dynamic model configuration

#### Integration with TranslationHandler

The refactored `TranslationHandler` now serves as a coordinator:

```python
# Initialize providers
self.providers = {
    'gemini': GeminiProvider(app),
    'openai': OpenAIProvider(app)
}

# Get active provider based on selected model
def _get_active_llm_provider(self):
    selected_model = self.app.translation_model_var.get()
    if selected_model == 'gemini_api':
        return self.providers.get('gemini')
    elif self.app.is_openai_model(selected_model):
        return self.providers.get('openai')
    return None
```

#### Benefits of the New Architecture

✅ **Separation of Concerns**: Each provider focuses only on its specific implementation
✅ **Code Reuse**: Common functionality is shared via inheritance 
✅ **Maintainability**: Much easier to add new LLM providers or modify existing ones
✅ **Consistent Behavior**: All providers share identical session management, logging, and context handling
✅ **Backward Compatibility**: Public interface remains unchanged

#### Legacy Functionality Preservation

The `TranslationHandler` retains:
- **Legacy OCR methods** for Gemini OCR (non-translation use cases)
- **Non-LLM translation methods** (MarianMT, Google Translate, DeepL)
- **File cache management** for all translation providers
- **Unified translation cache coordination**

This architecture makes it straightforward to add new LLM providers while maintaining all existing functionality and ensuring consistent behavior across all AI-powered translation services.

### API Usage Statistics and Monitoring System

The application includes a comprehensive API usage monitoring system for tracking costs and performance across all translation providers, with particular focus on Gemini API cost management.

#### Statistics Handler (`handlers/statistics_handler.py`)
The StatisticsHandler provides real-time monitoring and analysis of API usage:

**Core Features:**
- **Real-time monitoring** of Gemini OCR and Translation API usage
- **Cost calculation** with proper currency formatting for different locales
- **Export functionality** for statistics in CSV and TXT formats  
- **Clipboard integration** for easy data sharing
- **Multi-language support** with proper Polish number formatting

**API Usage Tab Integration:**
The GUI includes a dedicated "API Usage" tab that displays:
- **Gemini OCR Statistics**: Total calls, average cost per call/minute/hour, total cost
- **Gemini Translation Statistics**: Total calls, words translated, words per minute, cost per word/call/minute/hour, total cost
- **Combined API Statistics**: Total API cost, combined cost per minute/hour
- **DeepL Usage Tracker**: Free monthly limit monitoring

#### API Log Files
The system maintains multiple log levels for different use cases:

**Short Log Files (Statistics Processing):**
- **`GEMINI_API_OCR_short_log.txt`** - Condensed log for OCR API calls with timing and cost data
- **`GEMINI_API_TRA_short_log.txt`** - Condensed log for Translation API calls with timing and cost data

**Detailed Log Files (Full Analysis):**
- **`Gemini_API_call_logs.txt`** - Complete request/response data with token analysis

#### Export and Sharing Features
- **CSV Export**: Structured data export with proper localization
- **Text Export**: Human-readable summary reports in English/Polish
- **Clipboard Copy**: Quick sharing with proper formatting for each language
- **Automatic Currency Formatting**: Proper decimal separators and currency symbols for different locales

### Gemini API Integration and Logging

The application features sophisticated Gemini API integration with comprehensive logging and cost tracking capabilities designed for the Gemini 2.5 Flash-Lite model.

#### Gemini API Call Logging System (`Gemini_API_call_logs.txt`)

When enabled in settings, the application generates detailed logs of all Gemini API interactions for cost monitoring, debugging, and usage analysis.

**Log Structure and Content:**
Each API call creates a comprehensive log entry containing:

1. **Call Metadata:**
   - Precise timestamp and language pair
   - Message character/word/line counts
   - API call duration for performance analysis

2. **Complete Context Window:**
   - Full message content sent to Gemini API
   - Shows context-aware translation implementation
   - Demonstrates how previous subtitles are included for narrative coherence

3. **Token and Cost Analysis:**
   - Exact input/output token counts from Gemini API
   - Per-call cost breakdown using Gemini 2.5 Flash-Lite pricing
   - Cumulative cost tracking across sessions
   - Cost-per-word analysis for budget planning

**Example Log Entry Format:**
```
=== GEMINI API CALL LOG ===
Timestamp: 2025-07-03 01:10:10
Language Pair: en -> pl
Original Text: [source text]

CALL DETAILS:
- Message Length: 117 characters
- Word Count: 17 words
- Line Count: 4 lines

COMPLETE MESSAGE CONTENT SENT TO GEMINI:
---BEGIN MESSAGE---
<Translate idiomatically from English to Polish. Return translation only.>

ENGLISH: [source text]
POLISH:
---END MESSAGE---

RESPONSE RECEIVED:
[translation result]

TOKEN & COST ANALYSIS (CURRENT CALL):
- Translated Words: 6
- Exact Input Tokens: 28
- Exact Output Tokens: 11
- Input Cost: $0.00000280
- Output Cost: $0.00000440
- Total Cost for this Call: $0.00000720

CUMULATIVE TOTALS:
- Total Translated Words (so far): 6
- Total Input Tokens (so far): 28
- Total Output Tokens (so far): 11
- Cumulative Log Cost: $0.00000720
```

**Context Window Implementation:**
The logs demonstrate the sophisticated context-aware translation system:
```
ENGLISH: [Previous subtitle 1]
ENGLISH: [Previous subtitle 2]
ENGLISH: [Current subtitle to translate]

POLISH: [Previous translation 1]
POLISH: [Previous translation 2]
POLISH: [Space for current translation]
```

This context window (configurable 0-2 previous subtitles) enables narrative coherence and improved grammar flow.

#### Gemini Translation Cache (`gemini_cache.txt`)

**Cache Format:**
```
Gemini(LANG_PAIR,timestamp):original_text:==:translated_text
```

**Format Components:**
- **Provider**: "Gemini" identifier
- **Language Pair**: Source-target codes (e.g., "CS-PL", "FR-EN")  
- **Timestamp**: Cache entry creation time
- **Delimiter**: ":==:" separates original from translated text

**Integration with Unified Cache:**
- Level 2 persistent storage in two-tier caching system
- Works alongside unified in-memory cache (Level 1)
- Reduces API costs through intelligent caching
- Cache effectiveness depends on OCR consistency

### Auto-Update System

The application features a complete auto-update system that allows users to easily update to the latest version through a "Check for Updates" button in the About tab.

#### Update Checker (`update_checker.py`)

The UpdateChecker class provides GitHub API integration for checking and downloading updates:

**Core Features:**
- **GitHub API Integration** - Queries the latest release information from GitHub API
- **Version Comparison** - Uses semantic version comparison to detect newer versions
- **Asset Download** - Downloads the main executable installer from GitHub releases  
- **Progress Monitoring** - Provides download progress callbacks for UI updates
- **Staging System** - Downloads updates to a staging directory for safe application

**Key Methods:**
- `check_for_updates()` - Queries GitHub API for latest release information
- `download_update(update_info, progress_callback)` - Downloads update file with progress tracking
- `has_staged_update()` - Checks if there's a staged update waiting to be applied
- `get_staged_update_info()` - Retrieves metadata about staged updates

#### Update Applier (`update_applier.py`)

The UpdateApplier class handles the actual application of downloaded updates:

**Core Features:**
- **Simple Batch File Creation** - Creates minimal Windows batch scripts for update installation
- **File Preservation** - Preserves user configuration files (.log, .ini, .txt) during updates
- **Clean Installation** - Removes old application files before installing new version
- **Graceful Process Termination** - Waits for application to close before applying updates
- **Self-Cleanup** - Batch files automatically clean up temporary files and self-delete

**Update Process:**
1. Creates staging directory with downloaded installer
2. Generates Windows batch file with update commands
3. Batch file waits for application termination
4. Preserves user configuration files
5. Removes old application files and directories
6. Extracts new version from installer
7. Restores user configuration files
8. Launches updated application
9. Cleans up temporary files and self-deletes

**Safety Features:**
- Validates staged files before applying updates
- Checks file sizes to ensure complete downloads
- Preserves user data throughout the update process
- Provides fallback behavior for failed updates

### Dynamic Gemini Models Configuration

The application features a dynamic Gemini model management system that allows flexible configuration of models for different operations (OCR vs Translation) through CSV-based configuration.

#### Gemini Models Manager (`handlers/gemini_models_manager.py`)

The GeminiModelsManager class provides centralized management of Gemini model configurations:

**Core Features:**
- **CSV-based configuration** - All model information loaded from `resources/gemini_models.csv`
- **Separate OCR and Translation models** - Different models can be selected for each operation
- **Dynamic cost management** - Token costs automatically updated based on selected models
- **Real-time model switching** - Models can be changed without application restart
- **Availability filtering** - Models are filtered based on Translation/OCR capability flags

**Configuration File Format (`gemini_models.csv`):**
```csv
Model Name,API Name,Input Cost per 1M,Output Cost per 1M,Translation,OCR
Gemini 2.5 Flash-Lite,gemini-2.5-flash-lite,0.1,0.4,yes,yes
Gemini 2.0 Flash,gemini-2.0-flash-001,0.1,0.4,yes,yes
Gemini 2.0 Flash-Lite,gemini-2.0-flash-lite-001,0.075,0.3,no,yes
```

**Key Methods:**
- `get_translation_model_names()` - Returns models available for translation
- `get_ocr_model_names()` - Returns models available for OCR
- `get_model_costs(api_name)` - Retrieves cost information for a specific model
- `get_api_name_by_display_name(display_name)` - Converts display names to API names
- `reload_models()` - Refreshes model list from CSV file

**Integration Points:**
- **GUI Dropdowns**: Translation and OCR model dropdowns are populated from CSV data
- **Cost Updates**: Token costs in configuration are updated when models change  
- **API Calls**: Translation and OCR operations use the appropriate selected model
- **Settings Persistence**: Model selections are saved to configuration file

**Benefits:**
- ✅ **Flexible Model Selection**: Different models for OCR vs Translation operations
- ✅ **Dynamic Configuration**: No code changes needed to add/remove models
- ✅ **Accurate Cost Tracking**: Costs automatically reflect selected models
- ✅ **Easy Maintenance**: Model information centralized in single CSV file

### Dynamic OpenAI Models Configuration

The application features a dynamic OpenAI model management system that allows flexible configuration of models for translation operations through CSV-based configuration.

#### OpenAI Models Manager (`handlers/openai_models_manager.py`)

The OpenAIModelsManager class provides centralized management of OpenAI model configurations:

**Core Features:**
- **CSV-based configuration** - All model information loaded from `resources/openai_models.csv`
- **Translation-focused models** - Models are specifically configured for translation operations (OCR is not supported for OpenAI)
- **Dynamic cost management** - Token costs automatically updated based on selected models
- **Real-time model switching** - Models can be changed without application restart
- **Advanced model support** - Supports different OpenAI model types including GPT-4.1 and GPT-5 models

**Configuration File Format (`openai_models.csv`):**
```csv
Model Name,API Name,Input Cost per 1M,Output Cost per 1M,Translation,OCR
GPT 5 Nano,gpt-5-nano,0.05,0.4,yes,no
GPT 4.1 Mini,gpt-4.1-mini,0.25,2.0,yes,no
GPT 4.1 Nano,gpt-4.1-nano,0.15,0.6,yes,no
```

**Key Methods:**
- `get_translation_model_names()` - Returns models available for translation
- `get_model_costs(api_name)` - Retrieves cost information for a specific model
- `get_api_name_by_display_name(display_name)` - Converts display names to API names
- `is_valid_translation_model(display_name)` - Check if display name is a valid translation model
- `reload_models()` - Refreshes model list from CSV file

**Integration Points:**
- **GUI Dropdowns**: Translation model dropdowns are populated from CSV data
- **Cost Updates**: Token costs in configuration are updated when models change  
- **API Calls**: Translation operations use the appropriate selected model with context window support
- **Settings Persistence**: Model selections are saved to configuration file

**OpenAI Model Types Support:**
- **GPT-5 Models**: Use the Responses API with configurable reasoning effort and verbosity settings
- **GPT-4.1 Models**: Use the Chat Completions API with temperature=0 for non-thinking mode
- **Context Window**: Configurable context window (0-2 previous subtitles) for narrative coherence
- **Comprehensive Logging**: Detailed API call logging with token usage and cost tracking

**Benefits:**
- ✅ **Translation-Focused**: Optimized specifically for translation tasks with context awareness
- ✅ **Advanced Model Support**: Supports latest OpenAI models including GPT-5 series
- ✅ **Dynamic Configuration**: No code changes needed to add/remove models
- ✅ **Accurate Cost Tracking**: Costs automatically reflect selected models and usage patterns

### Multi-Language UI Support

The application supports multiple UI languages through:
- `language_ui.py` - UILanguageManager class that loads translations
- CSV files in `resources/` directory containing UI text translations
- Dynamic UI rebuilding when language changes

### RTL Text Processing System

The application includes comprehensive support for Right-to-Left (RTL) languages through a hybrid architecture combining native Qt support (PySide6) with fallback tkinter processing, providing optimal text display and punctuation handling for Arabic, Hebrew, and Persian languages.

#### Hybrid RTL Architecture

The application implements a two-tier RTL support system for maximum compatibility and performance:

**Primary: PySide6 Native RTL Support**
- **Technology**: Qt's native RTL + HTML rendering + Arabic reshaping
- **Used for**: Translation overlay windows (target overlays)
- **Advantages**: True bidirectional text support, perfect character positioning, native text rendering quality
- **Implementation**: `pyside_overlay.py` module with `RTLTextDisplay` class

**Fallback: tkinter + RTL Processor**
- **Technology**: python-bidi + arabic-reshaper + tkinter text tags
- **Used for**: When PySide6 unavailable or tkinter widgets
- **Advantages**: Proven solution, full compatibility with existing setup
- **Implementation**: `rtl_text_processor.py` module with `RTLTextProcessor` class

#### PySide6 RTL Integration (`pyside_overlay.py`)

The PySide6 integration provides superior RTL support through Qt's native capabilities:

**Core Components:**
- **`RTLTextDisplay`** - RTL-capable QTextEdit widget with tkinter compatibility methods
- **`PySideTranslationOverlay`** - Native Qt window with resize/move handling
- **`PySideOverlayManager`** - Manager for PySide overlays that coexists with tkinter

**Key Features:**
- **HTML-based RTL rendering** with `dir="rtl"` and `text-align: right`
- **Native Arabic/Hebrew character shaping** using arabic-reshaper library
- **Qt's bidirectional text algorithm** for proper text flow
- **Full tkinter compatibility layer** for seamless integration
- **Graceful fallback** when PySide6 unavailable

**Architecture Benefits:**
- ✅ **Solves Hebrew word wrapping issues** - Qt handles RTL text natively
- ✅ **Proper punctuation positioning** - No manual repositioning needed
- ✅ **Superior font rendering** - Qt's text engine vs tkinter limitations
- ✅ **Zero breaking changes** - Existing code works unchanged
- ✅ **Automatic detection** - Switches between PySide/tkinter seamlessly

**Implementation Example:**
```python
# Automatic RTL detection and rendering
if hasattr(self.app.translation_text, 'set_rtl_text'):
    # PySide text widget - use Qt's native RTL display
    self.app.translation_text.set_rtl_text(
        text, language_code, bg_color, text_color, font_size
    )
else:
    # Fallback to tkinter with RTL processor
    processed_text = RTLTextProcessor.process_bidi_text(text, language_code)
    # Apply to tkinter widget...
```

#### tkinter RTL Processor (`rtl_text_processor.py`)

The RTLTextProcessor provides RTL support for tkinter widgets and serves as a fallback:

**Core Features:**
- **Punctuation repositioning** for RTL text display in tkinter widgets
- **BiDi text preparation** for proper rendering in UI components that lack native RTL support
- **Language-specific handling** for Persian (fa), Arabic (ar), and Hebrew (he) language codes
- **Error resilience** with graceful fallback to original text if processing fails

**Key Methods:**

1. **`fix_rtl_punctuation(text, language_code)`**
   - Corrects punctuation positioning for RTL languages
   - Handles common punctuation marks (periods, question marks, exclamation marks)
   - Removes incorrectly positioned punctuation from text beginnings
   - Ensures proper sentence-ending punctuation placement

2. **`prepare_rtl_for_display(text, language_code)`**
   - Prepares RTL text for proper display in tkinter Text widgets
   - Adds Right-to-Left Mark (RLM) character (\u200F) for proper directionality
   - Works with tkinter's right-alignment to achieve correct RTL rendering
   - Maintains text readability without complex BiDi algorithms

3. **`is_rtl_text_likely_incorrect(text)`**
   - Detects potentially incorrectly positioned punctuation in RTL text
   - Identifies common indicators like periods at text beginnings
   - Used for validation and debugging RTL text processing

**Implementation Strategy:**
The RTL processor uses a simplified approach optimized for tkinter limitations:
- Rather than complex BiDi algorithms, it relies on modern tkinter's right-alignment capabilities
- Adds directional markers (RLM) to ensure proper text flow
- Focuses on punctuation correction rather than full text reversal
- Maintains compatibility with tkinter Text widget constraints

#### Shared Components and Integration

**RTL Language Detection:** Unified between both systems for consistency
```python
# PySide overlay uses existing RTL processor for consistency
from rtl_text_processor import RTLTextProcessor
return RTLTextProcessor._is_rtl_language(lang_code)
```

**Arabic Reshaping:** Both systems use the `arabic-reshaper` library for proper character joining

**Display Manager Integration:** Automatic detection and routing
- Detects PySide vs tkinter text widgets automatically
- Routes to appropriate RTL handling system
- Maintains backward compatibility with existing code

**Integration Points:**
- **overlay_manager.py**: Creates PySide overlays with tkinter fallback
- **display_manager.py**: Routes text updates to appropriate RTL system
- **app_logic.py**: Safe widget existence checking for both systems

**Supported Languages:**
- **Persian (fa)**: Full support with Persian-specific punctuation handling
- **Arabic (ar)**: Arabic punctuation marks and text flow
- **Hebrew (he)**: Hebrew text directionality and punctuation
- **Language detection**: Automatic processing based on language code prefixes

#### Dependencies

**PySide6 RTL Support:**
- `PySide6>=6.4.0` - Qt6 framework for native RTL support
- `arabic-reshaper>=3.0.0` - Character shaping for Arabic/Persian
- `python-bidi>=0.4.2` - BiDi algorithm (shared with tkinter fallback)

**Graceful Degradation:**
- Application works fully without PySide6 installed
- Automatically falls back to proven tkinter RTL system
- No functionality loss when PySide6 unavailable

This hybrid system ensures that RTL translations appear correctly across all scenarios while providing optimal display quality when advanced RTL support is available.

### Working with Gemini API Files

**Monitoring API Usage:**
Developers can analyze the `Gemini_API_call_logs.txt` file to:
- Track exact API costs with token-level precision
- Monitor context window effectiveness
- Debug translation quality issues
- Analyze performance patterns (call duration, token efficiency)

**Cache Management:**
The `gemini_cache.txt` file enables:
- API cost reduction through intelligent caching
- Long-term storage of translation pairs
- Integration with unified in-memory cache system
- Manual cache analysis for optimization

**Cost Optimization Strategies:**
- Monitor cumulative costs through log analysis
- Analyze cache hit rates for different content types
- Optimize OCR settings to improve cache consistency
- Configure context window size based on cost/quality trade-offs

### Modular Handler Architecture

The handler classes in the `handlers/` directory provide separation of concerns:
- Each handler manages a specific aspect of the application
- Handlers are initialized with a reference to the main app instance
- This design makes it easier to maintain and extend functionality

### Resource Management

The application handles resources differently for development and compiled versions:
- `resource_handler.py` - Provides cross-platform resource path resolution
- `resource_copier.py` - Ensures resources are available next to compiled executables
- Resources are organized in the `resources/` directory for better structure

## Adding New Features

### Adding a New LLM Translation Provider

To add a new LLM-based translation provider (e.g., Claude, Llama):

1. **Create a new provider class** inheriting from `AbstractLLMProvider`:
   ```python
   # handlers/claude_provider.py
   from .llm_provider_base import AbstractLLMProvider
   
   class ClaudeProvider(AbstractLLMProvider):
       def __init__(self, app):
           super().__init__(app, "claude")
       
       def _get_api_key(self):
           return self.app.claude_api_key_var.get().strip()
       
       def _check_provider_availability(self):
           return CLAUDE_AVAILABLE
       
       # Implement other abstract methods...
   ```

2. **Implement all abstract methods** required by the base class:
   - `_get_api_key()` - Get API key for the provider
   - `_check_provider_availability()` - Check if libraries are available
   - `_get_context_window_size()` - Get context window setting
   - `_initialize_client()` - Initialize provider-specific client
   - `_get_model_config()` - Get model configuration for API calls
   - `_make_api_call()` - Make provider-specific API call
   - `_parse_response()` - Parse response and extract tokens/costs
   - `_get_model_costs()` - Get model-specific costs
   - `_is_logging_enabled()` - Check if logging is enabled
   - `_should_suppress_error()` - Check if errors should be suppressed

3. **Add provider to TranslationHandler**:
   ```python
   # In TranslationHandler.__init__()
   self.providers = {
       'gemini': GeminiProvider(app),
       'openai': OpenAIProvider(app),
       'claude': ClaudeProvider(app)  # Add new provider
   }
   
   # Update _get_active_llm_provider() method
   def _get_active_llm_provider(self):
       selected_model = self.app.translation_model_var.get()
       if selected_model == 'claude_api':
           return self.providers.get('claude')
       # ... existing logic
   ```

4. **Create model manager** (optional, for dynamic model configuration):
   - Create `claude_models_manager.py` similar to existing managers
   - Add CSV file in `resources/claude_models.csv`

5. **Update UI elements** in `gui_builder.py`:
   - Add provider to translation model dropdown
   - Add UI elements for provider-specific settings
   - Handle visibility toggling in `update_translation_model_ui`

6. **Add configuration support**:
   - Add provider to available options in `app_logic.py`
   - Add API key variables and settings
   - Add language mapping CSV files in `resources/`

### Adding a New Non-LLM Translation Provider

For traditional translation services (like Google Translate, DeepL):

1. **Add translation method to TranslationHandler**:
   ```python
   def _new_provider_translate(self, text, source_lang, target_lang):
       # Implementation specific to the new provider
       return translated_text
   ```

2. **Update the main translate_text method**:
   ```python
   elif selected_model == 'new_provider_api':
       translated_api_text = self._new_provider_translate(cleaned_text_main, source_lang, target_lang)
   ```

3. **Add caching support** if needed:
   - Add file cache handling in translate_text method
   - Follow the existing pattern for Google Translate or DeepL

4. **Update UI and configuration** as described above.

### Adding New OCR Preprocessing Modes

1. Update `ocr_utils.py`:
   - Add your preprocessing mode to the `preprocess_for_ocr` function
   - Consider adding specialized OCR parameters for your mode

2. Add the mode to the UI in `gui_builder.py`:
   - Add your mode to the preprocessing mode dropdown values

### Supporting New Languages

1. Ensure Tesseract supports the language:
   - Update language mapping in the `tesseract_to_iso` dictionary in `language_manager.py`
   - Add language codes to `constants.py` if necessary

2. For API-based translation services:
   - Update the appropriate language CSV files in `resources/` directory
   - Add the language name and code to mappings in `language_manager.py` if needed

3. For MarianMT, add models to the MarianMT models CSV file:
   - Add appropriate Helsinki-NLP model paths and display names
   - Ensure language code mapping is present in `translation_handler.py`

### Adding New UI Languages

1. Create a new CSV file in the `resources/` directory:
   - Name it `gui_XXX.csv` where XXX is the language code
   - Copy an existing file (e.g., `gui_eng.csv`) as a template
   - Translate all the UI text entries

2. Update `language_ui.py`:
   - Add the new language to the available languages list
   - Ensure the language code mapping is correct

## Packaging

The application can be packaged as a standalone executable:

### Using PyInstaller

1. Install PyInstaller:
   ```
   pip install pyinstaller
   ```

2. Use the appropriate spec file:
   
   **For standard CPU-only builds:**
   ```
   pyinstaller GameChangingTranslator.spec
   ```
   
   **For GPU/CUDA optimized builds:**
   ```
   pyinstaller GameChangingTranslator_GPU.spec
   ```
   
   **Alternative compilation using batch script:**
   ```
   run_python_compiler.bat
   ```

3. The executable will be in the `dist/GameChangingTranslator` directory

**Note:** The GPU version includes additional CUDA libraries and is optimized for systems with NVIDIA graphics cards. Both versions have been recently fixed to resolve numpy docstring compilation errors that previously caused PyInstaller crashes.

### Using cx_Freeze

1. Install cx_Freeze:
   ```
   pip install cx_freeze
   ```

2. Use the provided setup.py file:
   ```
   python setup.py build
   ```

## Testing

The application includes several test files for manual testing and verification:

### Available Test Files
- `test_*.py` - Various component-specific test files
- `test_unified_cache.py` - Test script for unified translation cache functionality
- `comprehensive_test.py` - Comprehensive testing script
- `simple_verification.py` - Simple verification script
- `verification_test.py` - Verification testing script

### Testing the Unified Cache

Run the unified cache test to verify the new caching system:

```bash
python test_unified_cache.py
```

This test verifies:
- Basic cache operations (store/retrieve)
- LRU eviction functionality when cache is full
- Provider-specific cache clearing
- Full cache clearing
- Cache statistics and utilization

### Testing Gemini API Integration

When testing Gemini API functionality, verify:

1. **API Call Logging:**
   - Enable API logging in settings
   - Perform test translations
   - Verify `Gemini_API_call_logs.txt` contains complete log entries
   - Check token counts and cost calculations for accuracy

2. **Cache Functionality:**
   - Test cache file creation and format in `gemini_cache.txt`
   - Verify cache hits for identical OCR text
   - Test cache persistence across application restarts

3. **Context Window:**
   - Test different context window settings (0, 1, 2 previous subtitles)
   - Verify context is included in API call logs
   - Check translation quality with and without context

4. **Cost Tracking:**
   - Monitor cumulative cost tracking accuracy
   - Verify per-call cost calculations match expected Gemini pricing
   - Test cost reset functionality when logs are cleared

### Manual Testing Areas

When adding new functionality, be sure to:

1. Test manually with different scenarios:
   - Different language pairs
   - Various text complexities
   - Different screen configurations
   - Edge cases (empty text, very long text, special characters)

2. Check the debug log for errors or warnings

3. Test performance impact of new features

## Thread Safety Considerations

The application uses multiple threads for capture, OCR, and translation with improved thread safety:

1. **Queue-based communication**: Thread-safe queues are used for passing data between threads
2. **UI updates**: All UI updates must be scheduled on the main thread using `root.after()`
3. **Shared state**: Access to shared state variables should be minimized and protected
4. **Unified cache thread safety**: The unified translation cache uses `threading.RLock()` for safe concurrent access across all translation providers
5. **Cache clearing**: No longer requires pausing translation threads - the unified cache can be safely cleared while translation is running

## Performance Optimization Tips

1. **Adaptive timing**: The threads use adaptive intervals based on queue fullness
2. **Image hashing**: Duplicate frames are detected and skipped using MD5 hashing
3. **Unified translation cache**: Single efficient cache reduces memory usage by 40-60% and eliminates cache management overhead
4. **Text similarity**: Similar text is cached to avoid redundant translations
5. **Preprocessing modes**: Different modes optimize for different text types
6. **OCR Preview**: Updates run on separate timer to avoid impacting main translation performance

## Recent Enhancements

The application has been enhanced with several recent features:

### LLM Provider Architecture Refactoring (Latest)
- **Modular provider system** replacing monolithic translation handler approach
- **Abstract base class** (`AbstractLLMProvider`) containing all common LLM functionality
- **Separated provider implementations** for Gemini and OpenAI with dedicated files
- **Preserved backward compatibility** - public interface unchanged
- **Enhanced maintainability** - much easier to add new LLM providers
- **Consistent behavior** across all LLM providers for session management, logging, and context windows
- **Legacy functionality preserved** - non-LLM providers and OCR methods remain in main handler
- **Backup available** at `handlers/translation_handler_backup.py` for reference

### Thread Management Optimization (Latest)
- **Optimized worker thread performance** for faster capture, OCR, and translation processing
- **Improved thread synchronization** and resource management
- **Enhanced build compilation** with streamlined dependency handling
- **PyInstaller fixes** resolving numpy docstring compilation errors that caused crashes
- **Unified build approach** with all spec files using `main.py` as entry point instead of separate bundled scripts

### Build System Improvements
- **Fixed PyInstaller compilation errors** related to aggressive optimization and numpy docstrings
- **Dual build support** with both CPU-optimized and GPU/CUDA-optimized spec files
- **Streamlined dependency management** with better import handling
- **Removed obsolete files** (`bundled_app.py`, redundant spec files) for cleaner builds
- **Enhanced error handling** in build process with better debugging information

### Gemini API Integration
- **Context-aware translation** with configurable sliding window for narrative coherence
- **Comprehensive API call logging** with detailed cost tracking and token analysis
- **OCR error intelligence** that automatically corrects recognition imperfections
- **Cost-effective translation** using Gemini 2.5 Flash-Lite pricing model
- **Advanced caching integration** with both in-memory and persistent file storage

### Unified Translation Cache System
- **Single LRU cache** replacing multiple overlapping cache layers
- **Thread-safe design** with proper locking mechanisms  
- **Fixed cache clearing bugs** that previously left stale data
- **40-60% memory reduction** from eliminating duplicate storage
- **Preserved file cache compatibility** for existing user data
- **Improved cache clearing** no longer requires pausing translation threads

### OCR Preview Window
- Real-time preview of OCR processing
- 1:1 scale image display with horizontal scrolling
- Configurable adaptive thresholding parameters
- Continuous updates independent of translation state
- Persistent window geometry

### Enhanced OCR Processing
- Adaptive thresholding with configurable parameters
- Trailing garbage removal option
- Multiple preprocessing modes for different text types
- Improved processing pipeline with better error handling

### Improved Localization
- Comprehensive language display names in CSV files
- Support for provider-specific language mappings
- Proper Polish alphabetical sorting
- Bilingual UI with complete translations

### Resource Organization
- All configuration files organized in `resources/` directory
- Automatic resource copying for compiled executables
- Better separation of user-modifiable files
- Improved path resolution for different deployment scenarios

## Contributing

This project is considered complete and is not accepting contributions. If you want to extend or modify the application:

1. Create a fork of the repository
2. Develop your own version as a separate project
3. Respect the GPL licence terms for any derived works

Please do not submit pull requests or feature requests as they will not be reviewed or accepted. The project is shared as-is for educational purposes and for others to build upon as they see fit.

## Third-Party Components and Licensing

The application includes third-party components that are properly licensed and attributed:

### HuggingFace Components
- **`convert_marian.py`** - Model conversion script for Tatoeba to MarianMT format
  - **Copyright**: © 2020 The HuggingFace Team
  - **License**: Apache License 2.0
  - **Usage**: Utility script for converting translation models
  - **Compliance**: Original copyright notices and license terms preserved
  - **Legal Status**: Fully compliant with Apache 2.0 permissive license terms

### License Compatibility
- **Apache 2.0 (HuggingFace)** ↔ **GPL v3 (Main Project)**: Compatible for distribution
- **Third-party attribution**: All original copyright notices preserved
- **Legal compliance**: All usage falls within permitted license terms

For complete third-party attribution details, see `ATTRIBUTION.md` in the project root.

## Code Style

The project follows these general conventions:

- Function and variable names use `snake_case`
- Classes use `CamelCase`
- Constants use `UPPER_CASE`
- Comments should explain "why" not just "what"
- Use descriptive variable names
- Break complex operations into smaller, well-named functions
- Add log statements for important operations or potential failure points

## Setup and Deployment

The project includes several utility scripts for easy setup and deployment:

### Windows Batch Scripts
- **`install_dependencies.bat`** - Automatically installs all required Python packages from `requirements.txt`
- **`run.bat`** - Quick launcher script to run the application from command line
- **`run_python_compiler.bat`** - Automated compilation script using PyInstaller with appropriate spec file

### Setup Files
- **`setup.py`** - Alternative build configuration for cx_Freeze compilation
- **`compile_app.py`** - Python-based compilation utility with advanced options
- **`requirements.txt`** - Complete list of Python package dependencies with versions

### Usage Examples
```bash
# Install all dependencies
install_dependencies.bat

# Run the application
run.bat

# Compile using PyInstaller
run_python_compiler.bat

# Alternative compilation with cx_Freeze
python setup.py build
```

## Dependencies and Imports

The application has several categories of dependencies:

### Required Dependencies
- `tkinter` - GUI framework (included with Python)
- `numpy` - Numerical computing
- `opencv-python` - Computer vision operations
- `pytesseract` - Tesseract OCR wrapper
- `Pillow` - Image processing
- `pyautogui` - Screen capture

### Optional Dependencies
- `keyboard` - Global hotkey support (enables keyboard shortcuts)
- `google-cloud-translate` - Google Translate API
- `deepl` - DeepL API
- `torch` + `transformers` - MarianMT neural translation
- `PySide6` - Qt6 framework for native RTL support in translation overlays
- `python-bidi` + `arabic-reshaper` - BiDi algorithm and Arabic reshaping for RTL text processing

The application gracefully handles missing optional dependencies and provides appropriate fallback behavior. When PySide6 is unavailable, the application automatically falls back to tkinter-based overlays with the existing RTL text processor.
