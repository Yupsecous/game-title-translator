# -*- mode: python ; coding: utf-8 -*-

"""
Game-Changing Translator PyInstaller Specification File - Optimized Version
This spec file includes all necessary dependencies while excluding unnecessary bloat.
Keeps ALL functionality but optimizes package size by excluding unused parts of heavy libraries.
To build: pyinstaller GameChangingTranslator.spec
"""

import os

# Get the current directory for proper path handling
current_dir = os.path.dirname(os.path.abspath('__file__'))

block_cipher = None

a = Analysis(
    ['main.py'],  # Use main.py instead of bundled_app.py (same as working Alternative spec)
    pathex=[current_dir],  # Include current directory in Python path
    binaries=[],
    # Include all necessary data files
    datas=[
        # Copy entire resources directory to root level (same folder as .exe)
        ('resources', 'resources'),
        # Copy entire docs directory to root level (same folder as .exe)
        ('docs', 'docs'),
        # Essential documentation
        ('README.md', '.'),
        ('LICENSE', '.'),
    ],
    # Include all modules that are actually needed (keep original working set)
    hiddenimports=[
        # Core application modules
        'logger',
        'app_logic',
        'config_manager',
        'constants',
        'gui_builder',
        'language_manager',
        'language_ui',
        'marian_mt_translator',  # Keep MarianMT functionality
        'unified_translation_cache',  # Unified LRU cache for all translation providers
        'ocr_utils',
        'overlay_manager',
        'resource_handler',
        'resource_copier',  # Auto-copy resources functionality
        'translation_utils',
        'ui_elements',
        'worker_threads',
        'main',
        # Handler modules
        'handlers',
        'handlers.cache_manager',
        'handlers.configuration_handler',
        'handlers.display_manager',
        'handlers.hotkey_handler',
        'handlers.statistics_handler',
        'handlers.translation_handler',
        'handlers.ui_interaction_handler',
        # Essential GUI libraries
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.colorchooser',
        '_tkinter',
        # Image processing
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        # Scientific libraries (simplified to avoid docstring issues)
        'numpy',
        'cv2',
        'pytesseract',
        'pyautogui',
        # Optional but needed dependencies
        'keyboard',
        'requests',
        'urllib.parse',
        'google.cloud.translate_v2',
        'google.generativeai',
        'google.auth',
        # Pre-load critical Gemini modules for performance
        'google.generativeai.types',
        'google.generativeai.client',
        'google.ai.generativelanguage',
        'deepl',
        # Threading optimization
        'concurrent.futures',
        'threading',
        # Keep torch/transformers/sentencepiece for MarianMT (minimal exclusions)
        'torch',
        'transformers',
        'sentencepiece',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # Only exclude clearly unnecessary libraries (be very conservative)
    excludes=[
        # Exclude clearly unused libraries
        'matplotlib',
        'pandas',
        'scipy',
        'sklearn',
        'tensorflow',
        'keras',
        'jupyter',
        'notebook',
        'pytest',
        'sphinx',
        'doctest',
        
        # GUI frameworks we don't use
        'PyQt5',
        'PyQt6',
        'PySide2',
        'PySide6',
        
        # Web frameworks
        'flask',
        'django',
        'fastapi',
        
        # Large PyTorch modules we don't need
        'torchvision',
        'torchaudio',
        
        # Test modules
        'tkinter.test',
        'unittest.mock',
    ],
    optimize=1,  # Use level 1 instead of 2 to avoid potential optimization issues
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GameChangingTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # Disabled to avoid antivirus false positives
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon='icon.ico',  # Add icon if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,  # Disabled to avoid antivirus false positives
    upx_exclude=[],
    name='GameChangingTranslator',
)
