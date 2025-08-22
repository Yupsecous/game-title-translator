#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PySide6 Translation Overlay for Game-Changing Translator
RTL-capable translation display overlay using PySide6

RTL Architecture:
- This module provides Qt's native RTL support (preferred)
- Falls back to existing rtl_text_processor.py for tkinter widgets
- Shares RTL language detection with rtl_text_processor.py for consistency
"""

import sys
import re
import os
from logger import log_debug

# Check if PySide6 is available
try:
    from PySide6.QtWidgets import QApplication, QTextEdit, QVBoxLayout, QMainWindow, QWidget
    from PySide6.QtCore import Qt, QRect, QPoint
    from PySide6.QtGui import QFont, QTextCursor, QTextBlockFormat
    PYSIDE6_AVAILABLE = True
except ImportError:
    PYSIDE6_AVAILABLE = False
    log_debug("PySide6 not available - falling back to tkinter overlays")

# Platform-specific imports for native window handling (Windows)
if sys.platform == "win32" and PYSIDE6_AVAILABLE:
    import ctypes
    from ctypes import wintypes

# Import Arabic reshaper for proper character joining
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    RESHAPER_AVAILABLE = True
except ImportError:
    RESHAPER_AVAILABLE = False


# Only define classes if PySide6 is available
if PYSIDE6_AVAILABLE:
    class RTLTextDisplay(QTextEdit):
        """RTL-capable text display for translation overlay"""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setup_widget()

        def setup_widget(self):
            """Configure widget for RTL display using HTML approach"""
            # Set RTL layout direction by default
            self.setLayoutDirection(Qt.RightToLeft)

            # Configure font with good RTL support
            font = QFont("Arial Unicode MS", 14)
            font.setFamilies(["Arial Unicode MS", "Segoe UI", "Tahoma"])
            self.setFont(font)

            # Read-only and word wrap
            self.setReadOnly(True)
            self.setLineWrapMode(QTextEdit.WidgetWidth)

            # Set document properties for HTML
            doc = self.document()
            doc.setDefaultStyleSheet("""
                div {
                    margin: 0;
                    padding: 0;
                    line-height: 1.4;
                }
            """)

        def set_rtl_text(self, text: str, language_code: str = None, bg_color: str = "#2c3e50", text_color: str = "#ecf0f1", font_size: int = 14):
            """Set RTL text using HTML approach for better alignment control"""
            # Clear existing content
            self.clear()

            # Check if RTL language
            is_rtl = self._is_rtl_language(language_code) if language_code else self._detect_rtl_text(text)

            if is_rtl:
                # Simple processing: just clean up and apply reshaping if needed
                processed_text = self._simple_rtl_processing(text, language_code)

                # Set RTL direction BEFORE inserting text
                self.setLayoutDirection(Qt.RightToLeft)

                # Use HTML with explicit right alignment and direction
                html_text = f"""
                <div style="text-align: right; direction: rtl; font-family: 'Arial Unicode MS', 'Segoe UI'; font-size: {font_size}pt; color: {text_color};">
                {processed_text}
                </div>
                """

                # Insert as HTML instead of plain text
                self.setHtml(html_text)

                # Force block/document alignment to the right
                cursor = self.textCursor()
                cursor.select(QTextCursor.Document)
                block_fmt = QTextBlockFormat()
                block_fmt.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
                cursor.mergeBlockFormat(block_fmt)
                
                # Clear selection and move cursor to start
                cursor.clearSelection()
                cursor.movePosition(QTextCursor.Start)
                self.setTextCursor(cursor)

            else:
                # LTR text with HTML
                html_text = f"""
                <div style="text-align: left; direction: ltr; font-family: 'Arial Unicode MS', 'Segoe UI'; font-size: {font_size}pt; color: {text_color};">
                {text}
                </div>
                """
                self.setLayoutDirection(Qt.LeftToRight)
                self.setHtml(html_text)

                # Force block/document alignment to the left for LTR
                cursor = self.textCursor()
                cursor.select(QTextCursor.Document)
                block_fmt = QTextBlockFormat()
                block_fmt.setAlignment(Qt.AlignLeft | Qt.AlignAbsolute)
                cursor.mergeBlockFormat(block_fmt)
                
                # Clear selection and move cursor to start
                cursor.clearSelection()
                cursor.movePosition(QTextCursor.Start)
                self.setTextCursor(cursor)

            # Update background color using stylesheet
            self.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {bg_color};
                    color: {text_color};
                    border: none;
                    padding: 5px;
                }}
            """)

        def _simple_rtl_processing(self, text: str, language_code: str) -> str:
            """Simple RTL processing - focus on what actually works"""
            # Step 1: Make text continuous (no paragraph breaks)
            processed = text.replace('\n\n', ' ').replace('\n', ' ')
            processed = ' '.join(processed.split())  # Normalize spaces

            # Step 2: Apply Arabic reshaping if available and needed
            if RESHAPER_AVAILABLE and self._needs_reshaping(language_code):
                try:
                    processed = arabic_reshaper.reshape(processed)
                except Exception:
                    pass  # Use original if reshaping fails

            return processed

        def _is_rtl_language(self, lang_code: str) -> bool:
            """Check if language is RTL - uses shared RTL processor if available"""
            if not lang_code:
                return False
            
            # Use existing RTL processor if available for consistency
            try:
                from rtl_text_processor import RTLTextProcessor
                return RTLTextProcessor._is_rtl_language(lang_code)
            except ImportError:
                # Fallback to built-in detection
                rtl_languages = ['ar', 'he', 'fa', 'ur', 'yi', 'ku', 'ps', 'dv']
                return any(lang_code.lower().startswith(lang) for lang in rtl_languages)

        def _detect_rtl_text(self, text: str) -> bool:
            """Detect RTL characters in text"""
            rtl_pattern = r'[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]'
            return bool(re.search(rtl_pattern, text))

        def _needs_reshaping(self, language_code: str) -> bool:
            """Check if text needs Arabic reshaping"""
            if not language_code:
                return True
            reshaping_langs = ['ar', 'fa', 'ur', 'ku']
            return any(language_code.lower().startswith(lang) for lang in reshaping_langs)

        # Compatibility methods with tkinter Text widget interface
        def winfo_exists(self):
            """Compatibility method with tkinter interface"""
            try:
                # For PySide, if we can access the widget and it's not destroyed, it exists
                return True  # PySide widgets exist until explicitly destroyed
            except:
                return False

        def winfo_viewable(self):
            """Compatibility method with tkinter interface"""
            try:
                return self.isVisible()
            except:
                return False

        def config(self, **kwargs):
            """Compatibility method with tkinter interface - handles common config options"""
            try:
                if 'state' in kwargs:
                    # Handle state changes (NORMAL/DISABLED)
                    state_val = kwargs['state']
                    if hasattr(state_val, 'split'):  # String value
                        if 'DISABLED' in str(state_val).upper() or 'disabled' in str(state_val).lower():
                            self.setReadOnly(True)
                        elif 'NORMAL' in str(state_val).upper() or 'normal' in str(state_val).lower():
                            self.setReadOnly(False)
            except Exception as e:
                log_debug(f"PySide config error: {e}")

        def get(self, start, end=None):
            """Compatibility method with tkinter interface - get text content"""
            try:
                return self.toPlainText()
            except:
                return ""

        def delete(self, start, end=None):
            """Compatibility method with tkinter interface - clear text"""
            try:
                self.clear()
            except:
                pass

        def insert(self, index, text):
            """Compatibility method with tkinter interface - insert text"""
            try:
                self.setPlainText(text)
            except:
                pass

        def see(self, index):
            """Compatibility method with tkinter interface - scroll to position"""
            try:
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.Start)
                self.setTextCursor(cursor)
            except:
                pass


    class VisualTopBar(QMainWindow):
        """A purely visual top bar with no event handling."""
        def __init__(self, parent=None):
            super().__init__(parent)
            self.setFixedHeight(10)


    class PySideTranslationOverlay(QMainWindow):
        """PySide translation overlay window with native OS resize/move handling"""

        def __init__(self, initial_geometry, bg_color, title="Translation", parent=None):
            super().__init__(parent)
            self.text_widget = None
            self.bg_color = bg_color

            # Define constants for native hit-testing (Windows-specific)
            if sys.platform == "win32":
                self.HTLEFT = 10
                self.HTRIGHT = 11
                self.HTTOP = 12
                self.HTTOPLEFT = 13
                self.HTTOPRIGHT = 14
                self.HTBOTTOM = 15
                self.HTBOTTOMLEFT = 16
                self.HTBOTTOMRIGHT = 17
                self.HTCAPTION = 2

            self.setup_window(initial_geometry, bg_color, title)

        def setup_window(self, initial_geometry, bg_color, title):
            """Setup overlay window"""
            self.setWindowTitle(title)

            # Frameless window, resizable, keep on top
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
            self.setMinimumSize(100, 50)  # Match tkinter minimum sizes
            self.setWindowOpacity(0.85)  # Match tkinter transparency

            # Set initial geometry
            try:
                x1, y1, x2, y2 = map(int, initial_geometry)
                width = max(x2 - x1, 100)
                height = max(y2 - y1, 50) 
                self.setGeometry(x1, y1, width, height)
                log_debug(f"PySide overlay geometry set: {width}x{height}+{x1}+{y1}")
            except (ValueError, TypeError) as e:
                log_debug(f"Error setting PySide overlay geometry {initial_geometry}: {e}. Using default.")
                self.setGeometry(200, 200, 300, 200)

            # Central widget and layout
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Set background color for the overlay window
            self.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {bg_color};
                    border: 2px solid {self._adjust_color_brightness(bg_color, -20)};
                }}
            """)

            # Add the purely visual top bar with SAME color as main window
            self.top_bar = VisualTopBar(self)
            # ISSUE 3 FIX: Top bar should have the same color as the main window
            self.top_bar.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {bg_color};
                    border: none;
                }}
            """)
            # ISSUE 4 FIX: Set cursor for moving window - use SizeAllCursor (four-directional arrow)
            self.top_bar.setCursor(Qt.SizeAllCursor)
            layout.addWidget(self.top_bar)

            # Create RTL text display
            self.text_widget = RTLTextDisplay()
            # ISSUE 2 FIX: Ensure text widget gets the correct background color
            self.text_widget.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {bg_color};
                    border: none;
                    padding: 5px;
                }}
            """)
            layout.addWidget(self.text_widget)

        def _adjust_color_brightness(self, hex_color, adjustment):
            """Adjust hex color brightness by a given amount"""
            try:
                # Remove # if present
                hex_color = hex_color.lstrip('#')
                
                # Convert to RGB
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                
                # Adjust brightness
                r = max(0, min(255, r + adjustment))
                g = max(0, min(255, g + adjustment))
                b = max(0, min(255, b + adjustment))
                
                # Convert back to hex
                return f"#{r:02x}{g:02x}{b:02x}"
            except:
                return hex_color  # Return original if conversion fails

        def show_translation(self, text: str, language_code: str = None, text_color: str = "#FFFFFF", font_size: int = 14):
            """Show translation text"""
            if self.text_widget:
                self.text_widget.set_rtl_text(text, language_code, self.bg_color, text_color, font_size)

        def update_color(self, new_color):
            """Update the color of the overlay"""
            self.bg_color = new_color
            self.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {new_color};
                    border: 2px solid {self._adjust_color_brightness(new_color, -20)};
                }}
            """)
            # ISSUE 2 & 3 FIX: Update top bar to match main window color
            if self.top_bar:
                self.top_bar.setStyleSheet(f"""
                    QMainWindow {{
                        background-color: {new_color};
                        border: none;
                    }}
                """)
            # ISSUE 2 FIX: Also update text widget background color
            if self.text_widget:
                self.text_widget.setStyleSheet(f"""
                    QTextEdit {{
                        background-color: {new_color};
                        border: none;
                        padding: 5px;
                    }}
                """)

        def get_geometry(self):
            """Return the window's geometry as [x1, y1, x2, y2] compatible with tkinter overlay"""
            try:
                x = self.x()
                y = self.y()
                width = self.width()
                height = self.height()
                return [x, y, x + width, y + height]
            except Exception as e:
                log_debug(f"Error getting PySide overlay geometry: {e}")
                return None

        def hide(self):
            """Hide the window"""
            super().hide()

        def show(self):
            """Show the window and ensure it's topmost with correct color"""
            super().show()
            self.raise_()
            self.activateWindow()
            # ISSUE 2 FIX: Ensure correct color when shown via hotkey
            self.update_color(self.bg_color)

        def toggle_visibility(self):
            """Toggle the window's visibility"""
            if self.isVisible():
                self.hide()
            else:
                self.show()

        def winfo_exists(self):
            """Compatibility method with tkinter overlay interface"""
            try:
                # For PySide, the window exists if we can access it and it's not destroyed
                return True  # PySide windows exist until explicitly destroyed
            except:
                return False

        def winfo_viewable(self):
            """Compatibility method with tkinter overlay interface"""
            try:
                return self.isVisible()
            except:
                return False

        def destroy(self):
            """Destroy the window - compatibility with tkinter"""
            try:
                self.close()
            except:
                pass

        def enterEvent(self, event):
            """ISSUE 3 FIX: Handle mouse enter event to set cursor in top area"""
            # Check if mouse is in the top area (movable area)
            if event.pos().y() <= (self.top_bar.height() + 10):
                self.setCursor(Qt.SizeAllCursor)
            else:
                self.setCursor(Qt.ArrowCursor)
            super().enterEvent(event)

        def leaveEvent(self, event):
            """ISSUE 3 FIX: Handle mouse leave event to reset cursor"""
            self.setCursor(Qt.ArrowCursor)
            super().leaveEvent(event)

        def mouseMoveEvent(self, event):
            """ISSUE 3 FIX: Handle mouse move to update cursor based on position"""
            # Check if mouse is in the top area (movable area)
            if event.pos().y() <= (self.top_bar.height() + 10):
                self.setCursor(Qt.SizeAllCursor)
            else:
                # Check if we're near the edges for resize cursors
                margin = 4
                on_left = event.pos().x() < margin
                on_right = event.pos().x() > self.width() - margin
                on_top = event.pos().y() < margin
                on_bottom = event.pos().y() > self.height() - margin
                
                if (on_top and on_left) or (on_bottom and on_right):
                    self.setCursor(Qt.SizeFDiagCursor)
                elif (on_top and on_right) or (on_bottom and on_left):
                    self.setCursor(Qt.SizeBDiagCursor)
                elif on_left or on_right:
                    self.setCursor(Qt.SizeHorCursor)
                elif on_top or on_bottom:
                    self.setCursor(Qt.SizeVerCursor)
                else:
                    self.setCursor(Qt.ArrowCursor)
            super().mouseMoveEvent(event)

        def nativeEvent(self, eventType, message):
            """Handle native Windows messages for resizing and moving"""
            if sys.platform != "win32" or eventType != "windows_generic_MSG":
                return super().nativeEvent(eventType, message)

            try:
                msg = ctypes.wintypes.MSG.from_address(message.__int__())
                if msg.message == 0x0084:  # WM_NCHITTEST
                    # Get mouse position in global coordinates
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short(msg.lParam >> 16).value
                    
                    # Convert global coordinates to local
                    local_pos = self.mapFromGlobal(QPoint(x, y))

                    # ISSUE 5 FIX: Ensure coordinates are within window bounds
                    if (local_pos.x() < 0 or local_pos.y() < 0 or 
                        local_pos.x() > self.width() or local_pos.y() > self.height()):
                        return super().nativeEvent(eventType, message)

                    # Define the resize margin
                    margin = 4
                    
                    # Check if cursor is within resize margins
                    on_left = local_pos.x() >= 0 and local_pos.x() < margin
                    on_right = local_pos.x() > self.width() - margin and local_pos.x() <= self.width()
                    on_top = local_pos.y() >= 0 and local_pos.y() < margin
                    on_bottom = local_pos.y() > self.height() - margin and local_pos.y() <= self.height()

                    # Return appropriate hit-test code
                    if on_top and on_left:
                        return True, self.HTTOPLEFT
                    if on_top and on_right:
                        return True, self.HTTOPRIGHT
                    if on_bottom and on_left:
                        return True, self.HTBOTTOMLEFT
                    if on_bottom and on_right:
                        return True, self.HTBOTTOMRIGHT
                    if on_left:
                        return True, self.HTLEFT
                    if on_right:
                        return True, self.HTRIGHT
                    if on_top:
                        return True, self.HTTOP
                    if on_bottom:
                        return True, self.HTBOTTOM
                    
                    # ISSUE 4 & 5 FIX: Check if cursor is on the top bar for moving
                    if hasattr(self, 'top_bar'):
                        # Get the top bar's position within the main window
                        top_bar_height = self.top_bar.height()
                        # Consider the top area (including top bar + margin) as movable
                        if local_pos.y() >= 0 and local_pos.y() <= (top_bar_height + 10):
                            # Also ensure we're not in a resize corner/edge area
                            if not (on_left or on_right or on_top or on_bottom):
                                return True, self.HTCAPTION
            except Exception as e:
                log_debug(f"Error in nativeEvent: {e}")

            return super().nativeEvent(eventType, message)

else:
    # Dummy classes when PySide6 is not available
    class RTLTextDisplay:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 not available")
    
    class PySideTranslationOverlay:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 not available")


# Ensure QApplication instance exists
def ensure_qapplication():
    """Ensure QApplication instance exists for PySide overlays"""
    if not PYSIDE6_AVAILABLE:
        log_debug("PySide6 not available - cannot create QApplication")
        return None
    
    # Fix DPI awareness issue on Windows
    if sys.platform == "win32":
        # Set Qt scaling policy before creating QApplication
        os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
        os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
        
        # Suppress DPI awareness warnings
        try:
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except AttributeError:
            # Older Qt versions might not have this method
            pass
        
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        log_debug("Created QApplication instance for PySide overlays")
    return app


class PySideOverlayManager:
    """Manager for PySide overlays to coexist with tkinter application"""
    
    def __init__(self):
        self.overlay = None
        self.qapp = None
        self.available = PYSIDE6_AVAILABLE
    
    def ensure_qapp(self):
        """Ensure QApplication exists"""
        if not self.available:
            return None
            
        if self.qapp is None:
            self.qapp = ensure_qapplication()
        return self.qapp
    
    def create_overlay(self, initial_geometry, bg_color, title="Translation"):
        """Create PySide overlay"""
        if not self.available:
            log_debug("PySide6 not available - cannot create overlay")
            return None
            
        try:
            self.ensure_qapp()
            
            if self.overlay:
                try:
                    self.overlay.close()
                except:
                    pass
            
            log_debug(f"Creating PySide overlay with geometry: {initial_geometry}, color: {bg_color}")
            self.overlay = PySideTranslationOverlay(initial_geometry, bg_color, title)
            log_debug("PySide overlay created successfully")
            return self.overlay
        except Exception as e:
            log_debug(f"Error creating PySide overlay: {e}")
            self.overlay = None
            return None
    
    def close_overlay(self):
        """Close the overlay"""
        if self.overlay:
            try:
                self.overlay.close()
            except:
                pass
            self.overlay = None


# Global manager instance
_pyside_manager = PySideOverlayManager()

def get_pyside_manager():
    """Get global PySide overlay manager"""
    return _pyside_manager

def is_pyside_available():
    """Check if PySide6 is available"""
    return PYSIDE6_AVAILABLE
