#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PySide6 Translation Overlay - updated to match tkinter fallback visuals.

Features / fixes included:
- Visual parity with tkinter: top bar height, text padding, font family/size,
  border thickness, opacity.
- Removed forced CSS line-height so Qt uses native font metrics.
- VisualTopBar handles window moving and keeps Qt.SizeAllCursor visible.
- nativeEvent WM_NCHITTEST no longer returns HTCAPTION (prevents Windows from
  overriding the cursor). Resizing hit-tests are still returned to allow native resize.
- create_overlay accepts forwarded visual kwargs (top_bar_height, text_padding, font_size, etc.)
"""

import sys
import os
import re

# Attempt to import logger; if not present, provide a simple fallback
try:
    from logger import log_debug
except Exception:
    def log_debug(*args, **kwargs):
        try:
            print("DEBUG:", *args, **kwargs)
        except Exception:
            pass

# Try to import PySide6; if not available, mark accordingly.
try:
    from PySide6.QtWidgets import QApplication, QTextEdit, QVBoxLayout, QMainWindow, QWidget
    from PySide6.QtCore import Qt, QRect, QPoint
    from PySide6.QtGui import QFont, QTextCursor, QTextBlockFormat
    PYSIDE6_AVAILABLE = True
except Exception:
    PYSIDE6_AVAILABLE = False

# Windows native interaction (only used if running on Win32 and PySide available)
if sys.platform == "win32" and PYSIDE6_AVAILABLE:
    import ctypes
    from ctypes import wintypes

# Optional Arabic reshaper / bidi support (best-effort)
try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    RESHAPER_AVAILABLE = True
except Exception:
    RESHAPER_AVAILABLE = False


# -----------------------
# PySide6-backed classes
# -----------------------
if PYSIDE6_AVAILABLE:

    class RTLTextDisplay(QTextEdit):
        """RTL-capable text display for translation overlay (QTextEdit wrapper)."""

        def __init__(self, parent=None):
            super().__init__(parent)
            # Initialize color storage attributes
            self._bg_color = "#2c3e50"
            self._fg_color = "#ecf0f1"
            self._current_text = ""
            self._current_language = None
            self.setup_widget()

        def setup_widget(self):
            """Configure widget for RTL display using HTML approach.

            Important: do NOT force a CSS line-height so Qt's native metrics determine spacing.
            Padding is left to the parent overlay to set so we can match tkinter's padx/pady.
            """
            # Default to RTL direction; actual text will control alignment when set.
            self.setLayoutDirection(Qt.RightToLeft)

            # Default font (can be overridden by parent overlay)
            font = QFont("Arial Unicode MS", 14)
            font.setFamilies(["Arial Unicode MS", "Segoe UI", "Tahoma"])
            self.setFont(font)

            self.setReadOnly(True)
            self.setLineWrapMode(QTextEdit.WidgetWidth)

            # Don't enforce line-height; keep margins/padding minimal here
            doc = self.document()
            doc.setDefaultStyleSheet("""
                div {
                    margin: 0;
                    padding: 0;
                }
            """)

        def set_rtl_text(self, text: str, language_code: str = None, bg_color: str = "#2c3e50", text_color: str = "#ecf0f1", font_size: int = 14):
            """Set text content while respecting RTL/LTR and applying inline HTML."""
            # Store current state for color updates
            self._current_text = text
            self._current_language = language_code
            self._bg_color = bg_color
            self._fg_color = text_color
            
            # Normalize whitespace WHILE PRESERVING intentional line breaks (SURGICAL FIX)
            processed = text.replace('\r\n', '\n').replace('\r', '\n')
            # Split by lines, clean whitespace within each line, then rejoin with newlines
            lines = processed.split('\n')
            cleaned_lines = []
            for line in lines:
                # Clean excessive whitespace within each line, but preserve the line structure
                cleaned_line = ' '.join(line.split())  # This only affects whitespace within the line
                cleaned_lines.append(cleaned_line)
            processed = '\n'.join(cleaned_lines)

            # Determine direction heuristically if language_code not provided
            is_rtl = False
            if language_code:
                is_rtl = self._is_rtl_language(language_code)
            else:
                is_rtl = self._detect_rtl_text(processed)

            # Optionally reshape Arabic if available and requested
            if RESHAPER_AVAILABLE and (not language_code or language_code.lower().startswith(('ar', 'fa', 'ur', 'ku'))):
                try:
                    processed = arabic_reshaper.reshape(processed)
                except Exception:
                    pass

            # CRITICAL FIX: Convert newlines to HTML line breaks for proper dialog formatting
            # HTML ignores \n characters, so we need to convert them to <br> tags
            html_processed = processed.replace('\n', '<br>')
            print(processed)
            print(html_processed)

            if is_rtl:
                self.setLayoutDirection(Qt.RightToLeft)
                html_text = f"""<div style="text-align: right; direction: rtl; font-family: '{self.font().family()}'; font-size: {font_size}pt; color: {text_color};">
                {html_processed}
                </div>"""
            else:
                self.setLayoutDirection(Qt.LeftToRight)
                html_text = f"""<div style="text-align: left; direction: ltr; font-family: '{self.font().family()}'; font-size: {font_size}pt; color: {text_color};">
                {html_processed}
                </div>"""

            # Use HTML insertion for richer control
            self.setHtml(html_text)

            # Ensure block alignment matches direction
            cursor = self.textCursor()
            cursor.select(QTextCursor.Document)
            block_fmt = QTextBlockFormat()
            if is_rtl:
                block_fmt.setAlignment(Qt.AlignRight | Qt.AlignAbsolute)
            else:
                block_fmt.setAlignment(Qt.AlignLeft | Qt.AlignAbsolute)
            cursor.mergeBlockFormat(block_fmt)
            cursor.clearSelection()
            cursor.movePosition(QTextCursor.Start)
            self.setTextCursor(cursor)

        def _is_rtl_language(self, lang_code: str) -> bool:
            if not lang_code:
                return False
            rtl_languages = ['ar', 'he', 'fa', 'ur', 'yi', 'ku', 'ps', 'dv']
            return any(lang_code.lower().startswith(l) for l in rtl_languages)

        def _detect_rtl_text(self, text: str) -> bool:
            rtl_pattern = r'[\u0590-\u05FF\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF\uFB50-\uFDFF\uFE70-\uFEFF]'
            return bool(re.search(rtl_pattern, text))

        # Simple compatibility wrappers mimicking tkinter Text behavior
        def winfo_exists(self):
            return True

        def winfo_viewable(self):
            return self.isVisible()

        def config(self, **kwargs):
            """Enhanced config method with full tkinter Text widget compatibility"""
            if 'state' in kwargs:
                state_val = kwargs['state']
                if 'DISABLED' in str(state_val).upper():
                    self.setReadOnly(True)
                elif 'NORMAL' in str(state_val).upper():
                    self.setReadOnly(False)
            
            # Handle background color (bg parameter)
            if 'bg' in kwargs:
                bg_color = kwargs['bg']
                try:
                    # Update the widget's stylesheet for background color
                    current_style = self.styleSheet()
                    # Extract existing padding if present
                    padding_match = re.search(r'padding:\s*([^;]+);', current_style)
                    padding = padding_match.group(1) if padding_match else "5px"
                    
                    new_style = f"""
                        QTextEdit {{
                            background-color: {bg_color};
                            border: none;
                            padding: {padding};
                        }}
                    """
                    self.setStyleSheet(new_style)
                    
                    # Store background color for later use
                    self._bg_color = bg_color
                    log_debug(f"PySide RTLTextDisplay: Updated background color to {bg_color}")
                except Exception as e:
                    log_debug(f"Error setting PySide text background color: {e}")
            
            # Handle foreground/text color (fg parameter)
            if 'fg' in kwargs:
                fg_color = kwargs['fg']
                try:
                    # Store text color for later use in HTML rendering
                    self._fg_color = fg_color
                    
                    # Re-render current text with new color if text exists
                    if hasattr(self, '_current_text') and hasattr(self, '_current_language'):
                        self.set_rtl_text(
                            self._current_text, 
                            self._current_language, 
                            getattr(self, '_bg_color', '#2c3e50'), 
                            fg_color, 
                            self.font().pointSize()
                        )
                    log_debug(f"PySide RTLTextDisplay: Updated text color to {fg_color}")
                except Exception as e:
                    log_debug(f"Error setting PySide text foreground color: {e}")
            
            # Handle font changes (font parameter)
            if 'font' in kwargs:
                font_spec = kwargs['font']
                try:
                    if isinstance(font_spec, tuple) and len(font_spec) >= 2:
                        # Font specified as tuple (family, size, *style)
                        font_family = font_spec[0]
                        font_size = int(font_spec[1])
                        
                        # Update the widget font
                        qfont = QFont(font_family, font_size)
                        self.setFont(qfont)
                        
                        # Re-render current text with new font if text exists
                        if hasattr(self, '_current_text') and hasattr(self, '_current_language'):
                            self.set_rtl_text(
                                self._current_text, 
                                self._current_language, 
                                getattr(self, '_bg_color', '#2c3e50'), 
                                getattr(self, '_fg_color', '#ecf0f1'), 
                                font_size
                            )
                        log_debug(f"PySide RTLTextDisplay: Updated font to {font_family} {font_size}")
                    else:
                        log_debug(f"Unsupported font specification format: {font_spec}")
                except Exception as e:
                    log_debug(f"Error setting PySide text font: {e}")

        def configure(self, **kwargs):
            """Alias for config method to match tkinter Text widget interface exactly"""
            return self.config(**kwargs)

        def get(self, start=None, end=None):
            return self.toPlainText()

        def delete(self, start=None, end=None):
            self.clear()

        def insert(self, index, text):
            self.setPlainText(text)

        def see(self, index):
            cursor = self.textCursor()
            cursor.movePosition(QTextCursor.Start)
            self.setTextCursor(cursor)


    class VisualTopBar(QWidget):
        """A purely visual draggable top bar that preserves the SizeAll cursor."""

        def __init__(self, parent=None, height: int = 10):
            super().__init__(parent)
            self.setFixedHeight(int(height))
            self.setCursor(Qt.SizeAllCursor)
            self.setMouseTracking(True)
            self._dragging = False
            self._drag_offset = QPoint()

        def _global_pos(self, event):
            try:
                # Qt6
                return event.globalPosition().toPoint()
            except AttributeError:
                return event.globalPos()

        def enterEvent(self, event):
            # Keep SizeAll cursor when hovering the top bar
            self.setCursor(Qt.SizeAllCursor)
            super().enterEvent(event)

        def leaveEvent(self, event):
            # Let parent decide cursor when leaving; but ensure we don't leave it stale
            try:
                self.window().unsetCursor()
            except Exception:
                pass
            super().leaveEvent(event)

        def mousePressEvent(self, event):
            if event.button() == Qt.LeftButton:
                win = self.window().windowHandle()
                used_system_move = False
                if win is not None:
                    try:
                        # Prefer native system move if available (Qt 6)
                        win.startSystemMove()
                        used_system_move = True
                    except Exception:
                        used_system_move = False

                if not used_system_move:
                    # Manual fallback dragging
                    self._dragging = True
                    self._drag_offset = self._global_pos(event) - self.window().frameGeometry().topLeft()
            super().mousePressEvent(event)

        def mouseMoveEvent(self, event):
            self.setCursor(Qt.SizeAllCursor)
            if self._dragging and (event.buttons() & Qt.LeftButton):
                self.window().move(self._global_pos(event) - self._drag_offset)
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            self._dragging = False
            super().mouseReleaseEvent(event)


    class PySideTranslationOverlay(QMainWindow):
        """PySide translation overlay window with native OS resize/move handling."""

        def __init__(self, initial_geometry, bg_color, title="Translation",
                     top_bar_height: int = 10,
                     text_padding: tuple = (5, 5),
                     font_size: int = 14,
                     font_family: str = "Arial",
                     border_px: int = 0,
                     opacity: float = 0.85,
                     parent=None):
            super().__init__(parent)
            self.text_widget = None
            self.bg_color = bg_color

            # Visual parameters (stored)
            self._top_bar_height = int(top_bar_height)
            # Expect text_padding as (pad_x, pad_y)
            try:
                self._text_padding = (int(text_padding[0]), int(text_padding[1]))
            except Exception:
                self._text_padding = (5, 5)
            self._font_size = int(font_size)
            self._font_family = font_family
            self._border_px = int(border_px)
            try:
                self._opacity = float(opacity)
            except Exception:
                self._opacity = 0.85

            # Native hit-test constants for Windows
            if sys.platform == "win32":
                self.HTLEFT = 10
                self.HTRIGHT = 11
                self.HTTOP = 12
                self.HTTOPLEFT = 13
                self.HTTOPRIGHT = 14
                self.HTBOTTOM = 15
                self.HTBOTTOMLEFT = 16
                self.HTBOTTOMRIGHT = 17
                self.HTCAPTION = 2  # kept for reference but not returned

            self.setup_window(initial_geometry, bg_color, title)

        def setup_window(self, initial_geometry, bg_color, title):
            """Setup overlay window visuals and layout."""
            self.setWindowTitle(title)
            # Frameless, top-most window
            self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
            self.setWindowFlag(Qt.Tool, True)
            # self.setMinimumSize(100, 50)

            # Apply opacity if possible
            try:
                self.setWindowOpacity(self._opacity)
            except Exception:
                pass

            # Geometry
            try:
                x1, y1, x2, y2 = map(int, initial_geometry)
                width = max(x2 - x1, 100)
                height = max(y2 - y1, 50)
                self.setGeometry(x1, y1, width, height)
                log_debug(f"PySide overlay geometry set: {width}x{height}+{x1}+{y1}")
            except Exception as e:
                log_debug(f"Error setting PySide overlay geometry {initial_geometry}: {e}. Using default.")
                self.setGeometry(200, 200, 300, 200)

            # Central widget + layout
            central_widget = QWidget()
            self.setCentralWidget(central_widget)
            layout = QVBoxLayout(central_widget)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(0)

            # Border styling (honor border_px; if zero, no border)
            border_css = f"border: {self._border_px}px solid {self._adjust_color_brightness(bg_color, -20)};" if self._border_px > 0 else "border: none;"

            self.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {bg_color};
                    {border_css}
                }}
            """)

            # Top bar (purely visual) using the requested height
            self.top_bar = VisualTopBar(self, height=self._top_bar_height)
            self.top_bar.setStyleSheet(f"""
                QWidget {{
                    background-color: {bg_color};
                    border: none;
                }}
            """)
            layout.addWidget(self.top_bar)

            # Text display
            self.text_widget = RTLTextDisplay()
            # Set requested font and size
            try:
                qfont = QFont(self._font_family, self._font_size)
                self.text_widget.setFont(qfont)
            except Exception:
                pass

            pad_x, pad_y = self._text_padding
            # Set padding in the QTextEdit to match tkinter padx/pady layout
            self.text_widget.setStyleSheet(f"""
                QTextEdit {{
                    background-color: {bg_color};
                    border: none;
                    padding: {pad_y}px {pad_x}px; /* top/bottom left/right */
                }}
            """)
            layout.addWidget(self.text_widget)

        def _adjust_color_brightness(self, hex_color, adjustment):
            """Adjust hex color brightness by a signed integer amount (-255.255)."""
            try:
                hex_color = hex_color.lstrip('#')
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                r = max(0, min(255, r + adjustment))
                g = max(0, min(255, g + adjustment))
                b = max(0, min(255, b + adjustment))
                return f"#{r:02x}{g:02x}{b:02x}"
            except Exception:
                return hex_color

        def show_translation(self, text: str, language_code: str = None, text_color: str = "#FFFFFF", font_size: int = None):
            """Set the translation text in the QTextEdit-compatible widget."""
            if not self.text_widget:
                return
            if font_size is None:
                font_size = self._font_size
            # Our RTLTextDisplay provides set_rtl_text which matches tkinter semantics
            try:
                self.text_widget.set_rtl_text(text, language_code, self.bg_color, text_color, font_size)
            except Exception as e:
                log_debug(f"Error setting translation text: {e}")

        def update_color(self, new_color):
            """Update colors for window and child widgets."""
            self.bg_color = new_color
            border_css = f"border: {self._border_px}px solid {self._adjust_color_brightness(new_color, -20)};" if self._border_px > 0 else "border: none;"
            self.setStyleSheet(f"""
                QMainWindow {{
                    background-color: {new_color};
                    {border_css}
                }}
            """)
            if self.top_bar:
                self.top_bar.setStyleSheet(f"""
                    QWidget {{
                        background-color: {new_color};
                        border: none;
                    }}
                """)
            if self.text_widget:
                # Use the enhanced config method to ensure proper color handling
                try:
                    self.text_widget.config(bg=new_color)
                    log_debug(f"PySide overlay: Updated text widget background color to {new_color}")
                except Exception as e:
                    log_debug(f"Error updating PySide text widget color: {e}")
                    # Fallback to direct stylesheet update
                    pad_x, pad_y = self._text_padding
                    self.text_widget.setStyleSheet(f"""
                        QTextEdit {{
                            background-color: {new_color};
                            border: none;
                            padding: {pad_y}px {pad_x}px;
                        }}
                    """)

        def update_text_color(self, new_text_color):
            """Update text color for the translation display."""
            if self.text_widget:
                try:
                    self.text_widget.config(fg=new_text_color)
                    log_debug(f"PySide overlay: Updated text color to {new_text_color}")
                except Exception as e:
                    log_debug(f"Error updating PySide text color: {e}")

        def get_geometry(self):
            """Return geometry as [x1, y1, x2, y2] for compatibility with tkinter overlay code."""
            try:
                x = self.x()
                y = self.y()
                w = self.width()
                h = self.height()
                return [x, y, x + w, y + h]
            except Exception as e:
                log_debug(f"Error getting PySide overlay geometry: {e}")
                return None

        def hide(self):
            super().hide()

        def show(self):
            super().show()
            self.raise_()
            self.activateWindow()
            # Re-apply color to ensure styling is correct after show
            self.update_color(self.bg_color)

        def toggle_visibility(self):
            if self.isVisible():
                self.hide()
            else:
                self.show()

        def winfo_exists(self):
            return True

        def winfo_viewable(self):
            try:
                return self.isVisible()
            except Exception:
                return False

        def destroy(self):
            try:
                self.close()
            except Exception:
                pass

        def mouseMoveEvent(self, event):
            """Handle cursor feedback for move & resize zones.

            The top bar handles moves; here we set SizeAll when within the top bar area,
            otherwise show appropriate resize cursors. We use a small padding so the visual
            top bar matches the effective move area.
            """
            try:
                top_bar_area_height = self.top_bar.height() + 2
            except Exception:
                top_bar_area_height = 12

            if event.pos().y() <= top_bar_area_height:
                self.setCursor(Qt.SizeAllCursor)
            else:
                margin = 4
                x = event.pos().x()
                y = event.pos().y()
                w = self.width()
                h = self.height()

                on_left = x < margin
                on_right = x > w - margin
                on_top = y < margin
                on_bottom = y > h - margin

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
            """Handle Windows native messages for resizing only.

            IMPORTANT: do NOT return HTCAPTION here for the top bar area. Moving is handled
            by VisualTopBar which preserves SizeAllCursor. Returning HTCAPTION forces Windows
            to set the Arrow cursor which overrides Qt's cursor.

            This implementation converts the WM_NCHITTEST coordinates (which are in
            physical pixels on Windows) to Qt logical/device-independent coordinates
            before calling mapFromGlobal().
            """
            if sys.platform != "win32" or eventType != "windows_generic_MSG":
                return super().nativeEvent(eventType, message)

            try:
                # Convert WPARAM/LPARAM to MSG structure
                msg = ctypes.wintypes.MSG.from_address(message.__int__())
                # WM_NCHITTEST = 0x0084
                if msg.message == 0x0084:
                    lparam = msg.lParam
                    # Extract X and Y as signed shorts (preserves negative coords if any)
                    x_phys = ctypes.c_short(lparam & 0xFFFF).value
                    y_phys = ctypes.c_short((lparam >> 16) & 0xFFFF).value

                    # Convert physical -> logical coordinates using devicePixelRatioF()
                    try:
                        # QWidget.devicePixelRatioF() is preferred if available
                        scale = self.devicePixelRatioF()
                    except Exception:
                        try:
                            scale = float(self.window().devicePixelRatio())
                        except Exception:
                            scale = 1.0

                    if not scale or scale <= 0:
                        scale = 1.0

                    logical_x = int(round(x_phys / scale))
                    logical_y = int(round(y_phys / scale))

                    local_pt = self.mapFromGlobal(QPoint(logical_x, logical_y))

                    # If outside window bounds, fallback
                    if (local_pt.x() < 0 or local_pt.y() < 0 or
                            local_pt.x() > self.width() or local_pt.y() > self.height()):
                        return super().nativeEvent(eventType, message)

                    margin = 4
                    on_left = local_pt.x() >= 0 and local_pt.x() < margin
                    on_right = local_pt.x() > self.width() - margin and local_pt.x() <= self.width()
                    on_top = local_pt.y() >= 0 and local_pt.y() < margin
                    on_bottom = local_pt.y() > self.height() - margin and local_pt.y() <= self.height()

                    # Return resize hit-tests only
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

                    # Do NOT return HTCAPTION even if inside the top bar; VisualTopBar handles moving.
            except Exception as e:
                log_debug(f"Error in nativeEvent: {e}")

            return super().nativeEvent(eventType, message)


else:
    # PySide not available: define placeholders that raise when used
    class RTLTextDisplay:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 not available")

    class PySideTranslationOverlay:
        def __init__(self, *args, **kwargs):
            raise ImportError("PySide6 not available")


# -----------------------
# QApplication helper
# -----------------------
def ensure_qapplication():
    """Ensure a single QApplication instance exists and configure high-dpi settings."""
    if not PYSIDE6_AVAILABLE:
        log_debug("PySide6 not available - cannot create QApplication")
        return None

    if sys.platform == "win32":
        # Environment tweaks for HiDPI behavior
        os.environ.setdefault('QT_AUTO_SCREEN_SCALE_FACTOR', '1')
        os.environ.setdefault('QT_ENABLE_HIGHDPI_SCALING', '1')
        
        try:
            # Ensure Qt knows we want high-dpi support (set attributes before creating app)
            QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
            QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
            QApplication.setHighDpiScaleFactorRoundingPolicy(
                Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )
        except Exception:
            pass

    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
        log_debug("Created QApplication instance for PySide overlays")
    return app


# -----------------------
# Manager for overlays
# -----------------------
class PySideOverlayManager:
    """Manager for PySide overlays to coexist with a tkinter application."""

    def __init__(self):
        self.overlay = None
        self.qapp = None
        self.available = PYSIDE6_AVAILABLE

    def ensure_qapp(self):
        if not self.available:
            return None
        if self.qapp is None:
            self.qapp = ensure_qapplication()
        return self.qapp

    def create_overlay(self, initial_geometry, bg_color, title="Translation", **kwargs):
        """Create PySide overlay and forward optional visual kwargs to the overlay."""
        if not self.available:
            log_debug("PySide6 not available - cannot create overlay")
            return None

        try:
            self.ensure_qapp()

            if self.overlay:
                try:
                    self.overlay.close()
                except Exception:
                    pass

            log_debug(f"Creating PySide overlay with geometry: {initial_geometry}, color: {bg_color}, opts: {kwargs}")
            self.overlay = PySideTranslationOverlay(initial_geometry, bg_color, title, **kwargs)
            log_debug("PySide overlay created successfully")
            return self.overlay
        except Exception as e:
            log_debug(f"Error creating PySide overlay: {e}")
            self.overlay = None
            return None

    def close_overlay(self):
        if self.overlay:
            try:
                self.overlay.close()
            except Exception:
                pass
            self.overlay = None


# Singleton manager
_pyside_manager = PySideOverlayManager()


def get_pyside_manager():
    return _pyside_manager


def is_pyside_available():
    return PYSIDE6_AVAILABLE
