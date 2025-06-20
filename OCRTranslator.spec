# -*- mode: python ; coding: utf-8 -*-

"""
OCR Translator PyInstaller Specification File - Optimized Version
This spec file includes all necessary dependencies while excluding unnecessary bloat.
Keeps ALL functionality but optimizes package size by excluding unused parts of heavy libraries.
To build: pyinstaller OCRTranslator.spec
"""

import os

# Get the current directory for proper path handling
current_dir = os.path.dirname(os.path.abspath('__file__'))

block_cipher = None

a = Analysis(
    ['bundled_app.py'],  # Use bundled_app.py to ensure proper imports
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
        'handlers.translation_handler',
        'handlers.ui_interaction_handler',
        # Essential GUI libraries
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.colorchooser',
        '_tkinter',
        # Essential image processing
        'PIL.Image',
        'PIL.ImageTk',
        'PIL._tkinter_finder',
        # Essential dependencies
        'numpy',
        'cv2',
        'pytesseract',
        'pyautogui',
        # Optional but needed dependencies
        'keyboard',
        'google.cloud.translate_v2',
        'deepl',
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
        # Only exclude libraries that are definitely not used
        'tensorflow',
        'keras',
        'sklearn',
        'pandas',
        'matplotlib',
        'seaborn',
        'plotly',
        'bokeh',
        'dash',
        'jupyter',
        'ipython',
        'notebook',
        'sphinx',
        'pytest',
        'networkx',
        'PySide2',
        'PySide6',
        'PyQt5',
        'PyQt6',
        'flask',
        'django',
        'fastapi',
        'dask',
        'numba',
        'h5py',
        'tables',
        'mediapipe',
        'face_recognition',
        'dlib',
        'librosa',
        'soundfile',
        # Only exclude obvious PyTorch modules not needed for basic inference
        'torchvision',
        'torchaudio',
        'torchtext',
    ],
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
    name='OCRTranslator',
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
    name='OCRTranslator',
)
