# -*- mode: python ; coding: utf-8 -*-

"""
Game-Changing Translator PyInstaller Specification File - Simple GPU Version
This spec file bundles everything needed for CUDA support without detection.
Just includes all necessary dependencies statically.
To build: pyinstaller GameChangingTranslator_GPU.spec
"""

import os

# Get the current directory
current_dir = os.path.dirname(os.path.abspath('__file__'))

block_cipher = None

a = Analysis(
    ['bundled_app.py'],
    pathex=[current_dir],
    binaries=[],
    datas=[
        ('resources', 'resources'),
        ('docs', 'docs'),
        ('README.md', '.'),
        ('LICENSE', '.'),
    ],
    hiddenimports=[
        # Core application
        'logger',
        'app_logic',
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
        'main',
        
        # Handlers
        'handlers',
        'handlers.cache_manager',
        'handlers.configuration_handler',
        'handlers.display_manager',
        'handlers.hotkey_handler',
        'handlers.statistics_handler',
        'handlers.translation_handler',
        'handlers.ui_interaction_handler',
        
        # GUI
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.colorchooser',
        '_tkinter',
        
        # Image processing
        'PIL.Image',
        'PIL.ImageTk',
        'PIL._tkinter_finder',
        
        # Core dependencies
        'numpy',
        'cv2',
        'pytesseract',
        'pyautogui',
        
        # Optional
        'keyboard',
        'google.cloud.translate_v2',
        'google.generativeai',
        'deepl',
        
        # GPU monitoring (Windows)
        'nvidia_ml_py3',
        
        # PyTorch (CPU + CUDA)
        'torch',
        'torch.nn',
        'torch.nn.functional',
        'torch.nn.modules',
        'torch.cuda',
        'torch.cuda.amp',
        'torch.amp',
        'torch.backends',
        'torch.backends.cuda',
        'torch.serialization',
        'torch.storage',
        'torch.utils',
        'torch.utils.data',
        'torch._C',
        
        # Transformers
        'transformers',
        'transformers.models',
        'transformers.models.marian',
        'transformers.models.marian.configuration_marian',
        'transformers.models.marian.modeling_marian',
        'transformers.models.marian.tokenization_marian',
        'transformers.configuration_utils',
        'transformers.modeling_utils',
        'transformers.tokenization_utils',
        'transformers.tokenization_utils_base',
        'transformers.tokenization_utils_fast',
        'transformers.utils',
        'transformers.utils.hub',
        'transformers.utils.import_utils',
        'transformers.file_utils',
        'transformers.generation',
        'transformers.generation.utils',
        
        # Tokenization
        'tokenizers',
        'tokenizers.implementations',
        'tokenizers.models',
        'tokenizers.pre_tokenizers',
        'tokenizers.processors',
        'sentencepiece',
        
        # Hugging Face Hub
        'huggingface_hub',
        'huggingface_hub.file_download',
        'huggingface_hub.hf_api',
        'huggingface_hub.repository',
        'huggingface_hub.snapshot_download',
        
        # Networking and utilities
        'requests',
        'requests.adapters',
        'requests.auth',
        'requests.models',
        'requests.sessions',
        'urllib3',
        'tqdm',
        'tqdm.auto',
        
        # File and data handling
        'pathlib',
        'tempfile',
        'shutil',
        'json',
        'yaml',
        'safetensors',
        'safetensors.torch',
        
        # Text processing
        'regex',
        're',
        'unicodedata',
        
        # System
        'threading',
        'concurrent.futures',
        'multiprocessing',
        'logging',
        'warnings',
        'traceback',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Only exclude what's definitely not needed
        'tensorflow',
        'keras',
        'sklearn',
        'pandas',
        'matplotlib',
        'seaborn',
        'plotly',
        'jupyter',
        'ipython',
        'notebook',
        'pytest',
        'PySide2',
        'PySide6',
        'PyQt5',
        'PyQt6',
        'flask',
        'django',
        'fastapi',
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
    name='GameChangingTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
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
    upx_exclude=[],
    name='GameChangingTranslator',
)
