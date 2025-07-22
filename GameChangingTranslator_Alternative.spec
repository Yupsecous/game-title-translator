# -*- mode: python ; coding: utf-8 -*-

"""
Alternative Game-Changing Translator PyInstaller Specification File
Uses simpler import approach to avoid numpy docstring issues
To build: pyinstaller GameChangingTranslator_Alternative.spec
"""

import os

# Get the current directory for proper path handling
current_dir = os.path.dirname(os.path.abspath('__file__'))

block_cipher = None

a = Analysis(
    ['main.py'],  # Use main.py directly instead of build_alternative.py
    pathex=[current_dir],
    binaries=[],
    datas=[
        ('resources', 'resources'),
        ('docs', 'docs'),
        ('README.md', '.'),
        ('LICENSE', '.'),
    ],
    hiddenimports=[
        # Core application modules
        'main',
        'app_logic',
        'logger',
        'config_manager',
        'constants',
        'gui_builder',
        'language_manager',
        'language_ui',
        'marian_mt_translator',
        'unified_translation_cache',
        'ocr_utils',
        'overlay_manager',
        'resource_handler',
        'resource_copier',
        'translation_utils',
        'ui_elements',
        'worker_threads',
        
        # Handler modules
        'handlers',
        'handlers.cache_manager',
        'handlers.configuration_handler',
        'handlers.display_manager',
        'handlers.hotkey_handler',
        'handlers.statistics_handler',
        'handlers.translation_handler',
        'handlers.ui_interaction_handler',
        
        # GUI libraries
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.colorchooser',
        
        # Image processing
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        
        # Scientific libraries
        'numpy',
        'cv2',
        'pytesseract',
        'pyautogui',
        
        # Optional dependencies
        'keyboard',
        'requests',
        'urllib.parse',
        
        # Google APIs
        'google.cloud.translate_v2',
        'google.generativeai',
        'google.auth',
        
        # DeepL
        'deepl',
        
        # Threading
        'concurrent.futures',
        'threading',
        
        # PyTorch/Transformers (for MarianMT)
        'torch',
        'transformers',
        'sentencepiece',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
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

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='GameChangingTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='GameChangingTranslator',
)
