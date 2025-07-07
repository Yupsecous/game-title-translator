#!/usr/bin/env python3
"""
Game-Changing Translator Compilation Script
Automates the compilation process for CPU and GPU versions
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"\n{description}")
    print("-" * len(description))
    
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print("✓ Success!")
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"✗ Error: {e}")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        return False

def verify_pytorch_installation():
    """Verify PyTorch installation and show details"""
    print("\nVerifying PyTorch installation...")
    verification_code = '''
import torch
print(f"PyTorch version: {torch.__version__}")
print(f"CUDA available: {torch.cuda.is_available()}")
if torch.cuda.is_available():
    print(f"CUDA version: {torch.version.cuda}")
    print(f"GPU device count: {torch.cuda.device_count()}")
    for i in range(torch.cuda.device_count()):
        print(f"GPU {i}: {torch.cuda.get_device_name(i)}")
else:
    print("CUDA version: N/A")
'''
    
    try:
        result = subprocess.run([sys.executable, "-c", verification_code], 
                              capture_output=True, text=True, check=True)
        print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"Error verifying PyTorch: {e}")
        print(e.stderr)
        return False

def compile_cpu_version():
    """Compile CPU-only version"""
    print("\n" + "="*50)
    print("         COMPILING CPU-ONLY VERSION")
    print("="*50)
    
    # Step 1: Uninstall existing PyTorch
    if not run_command("pip uninstall -y torch torchvision torchaudio", 
                      "Step 1: Uninstalling existing PyTorch libraries..."):
        print("Warning: Uninstallation had issues, continuing...")
    
    # Step 2: Install CPU PyTorch
    if not run_command("pip install torch torchvision torchaudio", 
                      "Step 2: Installing CPU-only PyTorch libraries..."):
        print("Failed to install CPU PyTorch libraries!")
        return False
    
    # Step 3: Verify installation
    if not verify_pytorch_installation():
        print("Failed to verify PyTorch installation!")
        return False
    
    # Step 4: Compile with PyInstaller
    if not run_command("pyinstaller GameChangingTranslator.spec", 
                      "Step 4: Compiling with PyInstaller..."):
        print("Compilation failed!")
        return False
    
    print("\n" + "="*50)
    print("    CPU VERSION COMPILED SUCCESSFULLY!")
    print("="*50)
    return True

def compile_gpu_version():
    """Compile GPU-enabled version"""
    print("\n" + "="*50)
    print("        COMPILING GPU-ENABLED VERSION")
    print("="*50)
    
    # Step 1: Uninstall existing PyTorch
    if not run_command("pip uninstall -y torch torchvision torchaudio", 
                      "Step 1: Uninstalling existing PyTorch libraries..."):
        print("Warning: Uninstallation had issues, continuing...")
    
    # Step 2: Install GPU PyTorch
    if not run_command("pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121", 
                      "Step 2: Installing GPU-enabled PyTorch libraries..."):
        print("Failed to install GPU PyTorch libraries!")
        return False
    
    # Step 3: Verify installation
    if not verify_pytorch_installation():
        print("Failed to verify PyTorch installation!")
        return False
    
    # Step 4: Compile with PyInstaller
    if not run_command("pyinstaller GameChangingTranslator_GPU.spec", 
                      "Step 4: Compiling with PyInstaller..."):
        print("Compilation failed!")
        return False
    
    print("\n" + "="*50)
    print("   GPU VERSION COMPILED SUCCESSFULLY!")
    print("="*50)
    return True

def main():
    """Main function"""
    # Change to script directory
    script_dir = Path(__file__).parent
    os.chdir(script_dir)
    print(f"Working directory: {script_dir}")
    
    while True:
        print("\n" + "="*50)
        print("       Game-Changing Translator Compilation Script")
        print("="*50)
        print("\nPlease select the version to compile:")
        print("1. CPU-only version")
        print("2. GPU-enabled version")
        print("3. Exit")
        
        try:
            choice = input("\nEnter your choice (1-3): ").strip()
            
            if choice == "1":
                success = compile_cpu_version()
            elif choice == "2":
                success = compile_gpu_version()
            elif choice == "3":
                print("\nThank you for using the Game-Changing Translator Compilation Script!")
                break
            else:
                print("Invalid choice. Please try again.")
                continue
            
            if success:
                another = input("\nWould you like to compile another version? (y/n): ").strip().lower()
                if another not in ['y', 'yes']:
                    break
            else:
                retry = input("\nWould you like to try again? (y/n): ").strip().lower()
                if retry not in ['y', 'yes']:
                    break
                    
        except KeyboardInterrupt:
            print("\n\nOperation cancelled by user.")
            break
        except Exception as e:
            print(f"\nUnexpected error: {e}")
            break

if __name__ == "__main__":
    main()
