import sys
import json
import time
import threading
import numpy as np
from PIL import ImageGrab
import cv2
from PyQt5.QtCore import Qt, QPoint, pyqtSignal, QRect, QSettings, QEvent
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QLabel,
                             QHBoxLayout, QSystemTrayIcon, QMenu, QAction, 
                             QToolButton, QBoxLayout, QSizePolicy, QSlider, 
                             QGraphicsOpacityEffect, QDialog, QComboBox, QCheckBox, 
                             QListWidget, QListWidgetItem, QDialogButtonBox, 
                             QPushButton, QDesktopWidget, QLineEdit, QMessageBox) # Added QGraphicsOpacityEffect
from PyQt5.QtGui import (QColor, QPixmap, QPainter, QBrush, QCursor,
                         QIcon, QGuiApplication)
from pathlib import Path

# --- RegionSelector Class (Unchanged) ---
class RegionSelector(QWidget):
    selection_complete = pyqtSignal(QRect)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint |
                            Qt.WindowStaysOnTopHint |
                            Qt.Tool)
        self.setStyleSheet("background: rgba(0, 0, 0, 150);")
        self.setWindowOpacity(0.2)
        self.setGeometry(QGuiApplication.primaryScreen().virtualGeometry())
        self.setCursor(Qt.CrossCursor)
        self.start_point = QPoint()
        self.end_point = QPoint()
        self.dragging = False
        self.setMouseTracking(True)
        # print("RegionSelector created") # Reduced print noise

    def showEvent(self, event):
        # print("RegionSelector shown") # Reduced print noise
        self.activateWindow()
        self.raise_()
        super().showEvent(event)

    def mousePressEvent(self, event):
        self.start_point = event.pos()
        self.end_point = event.pos()
        self.dragging = True
        self.update()

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.end_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event):
        # print("Mouse released, emitting rect") # Reduced print noise
        self.dragging = False
        global_start = self.mapToGlobal(self.start_point)
        global_end = self.mapToGlobal(self.end_point)
        rect = QRect(global_start, global_end).normalized()
        self.selection_complete.emit(rect)
        self.close()

    def paintEvent(self, event):
        if self.dragging:
            painter = QPainter(self)
            painter.setPen(QColor(255, 0, 0, 255))
            painter.setBrush(QBrush(QColor(255, 255, 255, 50)))
            painter.drawRect(QRect(self.start_point, self.end_point))

# --- Draw rectangles around the regions on the screen ---
class RegionDisplayer(QWidget):
    def __init__(self, search_rect, anchor_rect):
        super().__init__()
        self.setWindowFlags(
            Qt.FramelessWindowHint | 
            Qt.WindowStaysOnTopHint | 
            Qt.Tool | 
            Qt.WindowTransparentForInput
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        
        # Cover entire virtual desktop
        self.setGeometry(QDesktopWidget().screenGeometry())  # Key fix
        self.search_rect = search_rect
        self.anchor_rect = anchor_rect

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        
        # Convert ABSOLUTE screen coordinates to WIDGET-RELATIVE coordinates
        offset = self.mapFromGlobal(QPoint(0, 0))
        
        # Draw search region (green)
        if not self.search_rect.isEmpty():
            adj_search = self.search_rect.translated(-offset.x(), -offset.y())
            painter.setPen(QColor(0, 255, 0, 200))
            painter.setBrush(QColor(0, 255, 0, 50))
            painter.drawRect(adj_search)
        
        # Draw anchor region (red)
        if not self.anchor_rect.isEmpty():
            adj_anchor = self.anchor_rect.translated(-offset.x(), -offset.y())
            painter.setPen(QColor(255, 0, 0, 200))
            painter.setBrush(QColor(255, 0, 0, 50))
            painter.drawRect(adj_anchor)

# --- DraggableTitleBar Class (Unchanged) ---
class DraggableTitleBar(QWidget):
    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.dragging = False
        self.offset = QPoint()
        self.is_visible = True # add is_visible

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 0, 5, 0)
        layout.setSpacing(5)

        self.title_label = QLabel(text)
        self.title_label.setStyleSheet("color: white; font: bold 10px; /* Smaller font */") #Smaller font
        self.title_label.setAlignment(Qt.AlignCenter)

        self.toggle_button = QToolButton()
        self.toggle_button.setFixedSize(18, 18); # Smaller size
        self.toggle_button.setStyleSheet("""
            QToolButton {
                color: white;
                border: none;
                border-radius: 3px;
                font: bold 10px; /* Smaller font */
                padding: 0px;
                margin: 0px;
            }
            QToolButton:hover {
                background-color: rgb(80,80,80)
            }
        """)

        self.toggle_button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Add the slider
        self.icon_size_slider = QSlider(Qt.Horizontal)
        self.icon_size_slider.setMinimum(10)
        self.icon_size_slider.setMaximum(100)
        self.icon_size_slider.setValue(48)      # Default icon size
        self.icon_size_slider.setFixedWidth(80)
        self.icon_size_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: 1px solid #999999;
                height: 8px;
                background: rgba(255, 255, 255, 30);
                margin: 2px 0;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: white;
                border: 1px solid #777777;
                width: 10px;
                height: 10px;
                margin: -5px 0;
                border-radius: 5px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #b1b1b1, stop:1 #c8c8c8);
                border: 1px solid #777777;
                height: 8px;
                border-radius: 4px;
                margin: 2px 0;
            }
        """)

        # Add settings button
        self.settings_button = QToolButton()
        self.settings_button.setFixedSize(18, 18)
        self.settings_button.setStyleSheet("""
            QToolButton {
                color: white;
                border: none;
                border-radius: 3px;
                font: bold 10px;
                padding: 0px;
                margin: 0px;
            }
            QToolButton:hover {
                background-color: rgb(80,80,80)
            }
        """)
        self.settings_button.setText("⚙")

        layout.addWidget(self.title_label)
        layout.addWidget(self.icon_size_slider)      # Add slider to layout
        layout.addWidget(self.toggle_button)
        layout.addWidget(self.settings_button)

        self.setFixedHeight(20) # fixed height of title bar
        self.setFixedWidth(220)           # Width of title bar.   Make wider to accommodate slider.
        self.setStyleSheet("""
            background-color: #333;
            border-radius: 5px;
        """)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = True
            self.offset = event.globalPos() - self.parent().pos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.dragging:
            self.parent().move(event.globalPos() - self.offset)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.dragging = False
        super().mouseReleaseEvent(event)

    def set_visibility(self, visible):
        self.is_visible = visible
        if visible:
            self.title_label.show()
            self.icon_size_slider.show()
            self.toggle_button.show()
            self.settings_button.show()
            self.setStyleSheet("""
                background-color: #333;
                border-radius: 5px;
            """)
            self.setEnabled(True)
        else:
            self.title_label.hide()
            self.icon_size_slider.hide()
            self.toggle_button.hide()
            self.settings_button.hide()
            self.setStyleSheet("background-color: transparent; border: none;")
            self.setEnabled(False)
        # Ensure the title bar remains visible in the layout
        self.show()

class SettingsDialog(QDialog):
    def __init__(self, category_config, all_debuffs, tracker, category_name, parent=None):
        super().__init__(parent)
        self.category_config = category_config.copy()
        self.all_debuffs = all_debuffs
        self.tracker = tracker
        self.category_name = category_name
        self.setWindowTitle(f"Settings - {self.category_config['name']}")
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setMinimumWidth(350)
        self.init_ui()

        # Create and show region displayer
        search_rect = QRect(
            self.category_config['x'], 
            self.category_config['y'],
            self.category_config['width'], 
            self.category_config['height']
        )
        anchor_rect = QRect(
            self.category_config.get('anchor_x', 0), 
            self.category_config.get('anchor_y', 0),
            self.category_config.get('anchor_width', 0), 
            self.category_config.get('anchor_height', 0)
        )
        self.region_displayer = RegionDisplayer(search_rect, anchor_rect)
        self.region_displayer.show()
        
        # Close region displayer when dialog is closed
        self.finished.connect(self.region_displayer.close)

    def init_ui(self):
        layout = QVBoxLayout(self)

        # Add Category Name Edit
        name_layout = QHBoxLayout()
        name_label = QLabel("Category Name:")

        self.name_edit = QLineEdit(self.category_config['name'])

        name_layout.addWidget(name_label)
        name_layout.addWidget(self.name_edit)

        layout.addLayout(name_layout)

        # Display Mode Selection Layout
        display_mode_layout = QHBoxLayout()
        display_mode_label = QLabel("Display Mode:")

        self.display_mode_combo = QComboBox()
        self.display_mode_combo.addItems(["Default", "Invert", "Opacity"])
        current_mode = self.category_config.get('display_mode', 'default').capitalize()
        self.display_mode_combo.setCurrentText(current_mode)

        display_mode_layout.addWidget(display_mode_label)
        display_mode_layout.addWidget(self.display_mode_combo)

        layout.addLayout(display_mode_layout)

        # Anchor Detection Layout
        anchor_detection_layout = QHBoxLayout()

        self.anchor_check = QCheckBox("Enable Anchor Detection")
        self.anchor_check.setChecked(self.category_config.get('anchor_detection_enabled', False))

        anchor_detection_layout.addWidget(self.anchor_check)

        anchor_btn = QPushButton("Set Anchor Region")
        anchor_btn.clicked.connect(self.select_anchor_region)

        anchor_detection_layout.addWidget(anchor_btn)

        layout.addLayout(anchor_detection_layout)

        # Add region buttons
        region_btn = QPushButton("Set Search Region")
        region_btn.clicked.connect(self.select_search_region)
        
        layout.addWidget(region_btn)
        
        # Debuff List
        layout.addWidget(QLabel("Select Debuffs:"))
        self.debuff_list = QListWidget()
        for debuff in self.all_debuffs:
            item = QListWidgetItem()
            widget = QWidget()
            hbox = QHBoxLayout(widget)

            # Checkbox
            checkbox = QCheckBox()
            checkbox.setChecked(debuff['name'] in self.category_config.get('selected_debuffs', []))
            checkbox.stateChanged.connect(lambda state, name=debuff['name']: self.toggle_debuff(name, state))
            hbox.addWidget(checkbox)

            # Icon Preview
            icon_label = QLabel()
            try:
                pixmap = QPixmap(f"images/{debuff['icon_image']}")
                if pixmap.isNull():
                    raise FileNotFoundError
                pixmap = pixmap.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            except Exception:
                pixmap = QPixmap(32, 32)
                pixmap.fill(QColor(30, 30, 30))
                painter = QPainter(pixmap)
                painter.setPen(QColor(255, 255, 255))
                painter.drawText(pixmap.rect(), Qt.AlignCenter, debuff['name'][0])
                painter.end()
            icon_label.setPixmap(pixmap)
            hbox.addWidget(icon_label)

            # Debuff Name
            hbox.addWidget(QLabel(debuff['name']))
            hbox.addStretch()

            widget.setLayout(hbox)
            item.setSizeHint(widget.sizeHint())
            self.debuff_list.addItem(item)
            self.debuff_list.setItemWidget(item, widget)

        layout.addWidget(self.debuff_list)

        # Buttons
        button_box_layout = QHBoxLayout()

        self.delete_button = QPushButton("🗑 Delete Category")
        self.delete_button.setStyleSheet("background-color: #ff4444; color: white;")
        self.delete_button.clicked.connect(self.confirm_delete)
        button_box_layout.addWidget(self.delete_button)

        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        button_box_layout.addWidget(button_box)

        layout.addLayout(button_box_layout)

    def confirm_delete(self):
        confirm = QMessageBox.question(
            self,
            "Delete Category",
            f"Are you sure you want to delete '{self.category_name}'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.tracker.delete_category(self.category_name)
            self.accept()  # Close the dialog

    def select_search_region(self):
        self.tracker.handle_region_selection(self.category_name)
        self.accept()  # Close dialog after selection

    def select_anchor_region(self):
        self.tracker.handle_anchor_selection(self.category_name)
        self.accept()

    def toggle_debuff(self, name, state):
        selected = self.category_config.get('selected_debuffs', [])
        if state == Qt.Checked:
            if name not in selected:
                selected.append(name)
        else:
            if name in selected:
                selected.remove(name)
        self.category_config['selected_debuffs'] = selected

    def get_updated_config(self):
        self.category_config['name'] = self.name_edit.text().strip()
        self.category_config['display_mode'] = self.display_mode_combo.currentText().lower()
        self.category_config['anchor_detection_enabled'] = self.anchor_check.isChecked()
        # Sort selected debuffs to maintain order
        all_names = [d['name'] for d in self.all_debuffs]
        self.category_config['selected_debuffs'] = [
            name for name in all_names 
            if name in self.category_config['selected_debuffs']
        ]
        return self.category_config

# --- DebuffIcon Class (Unchanged) ---
class DebuffIcon(QLabel):
    def __init__(self, debuff_data, initial_size=48):
        super().__init__()
        self.debuff_data = debuff_data
        self.current_size = initial_size
        self.setFixedSize(self.current_size, self.current_size)
        self.setStyleSheet("""
            background-color: rgba(30, 30, 30, 150);
            border: 2px solid rgba(255, 255, 255, 100);
            border-radius: 0px;
        """)
        self.setAlignment(Qt.AlignCenter)

        # Add opacity effect
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self.opacity_effect)
        self.set_opacity(1.0) # Start fully opaque

        self.update_icon()

    def update_icon(self):
        """Updates the icon pixmap or text."""
        try:
            pixmap = QPixmap(f"images/{self.debuff_data['icon_image']}")
            if pixmap.isNull():
                # print(f"Warning: Icon image not found: images/{self.debuff_data['icon_image']}") # Optional warning
                raise FileNotFoundError
            self.setPixmap(pixmap.scaled(self.current_size - 2, self.current_size - 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)) # scale down a bit from the label size.
            # Clear text if pixmap is successfully loaded
            self.setText("")
            # Reset stylesheet if needed (in case it was set to error state before)
            self.setStyleSheet("""
                background-color: rgba(30, 30, 30, 150);
                border: 2px solid rgba(255, 255, 255, 100);
                border-radius: 0px;
            """)
        except Exception as e:
            # Display first letter as fallback
            self.setText(self.debuff_data.get('name', '?')[0])
            self.setStyleSheet("""
                background-color: rgba(30, 30, 30, 150);
                border: 2px solid rgba(255, 0, 0, 150);
                border-radius: 5px;
                color: white;
                font: bold 20px;
            """)
        self.setFixedSize(self.current_size, self.current_size)
        self.setAlignment(Qt.AlignCenter) # Ensure alignment is set in both cases

    def resize_icon(self, new_size):
        """Resizes the icon."""
        self.current_size = new_size
        self.update_icon()

    def set_opacity(self, level):
        """Sets the opacity of the icon."""
        self.opacity_effect.setOpacity(level)

# --- CategoryWindow Class (Modified setup_ui) ---
class CategoryWindow(QWidget):
    position_changed = pyqtSignal()
    debuff_detection_changed = pyqtSignal(str, bool)
    anchor_found_changed = pyqtSignal(bool)
    icon_size_changed = pyqtSignal(int)

    def __init__(self, category_config, debuffs, debuff_tracker):
        super().__init__()
        self.debuff_tracker = debuff_tracker
        self.category_config = category_config
        self.category_name = category_config['name']
        self.debuffs = debuffs # All potential debuffs for this category
        self.active_debuffs = {} # Used for default/invert modes to track visible icons
        self.all_debuff_icons = {} # Used for opacity mode to track all icons

        self.detection_running = True
        self.region_lock = threading.Lock()
        self.anchor_region_lock = threading.Lock()
        self.anchor_found = False
        self.icon_size = category_config.get('icon_size', 48) # Load icon size
        self.show_title_bar = True

        self.display_mode = category_config.get('display_mode', 'default').lower()
        self.inactive_opacity = category_config.get('inactive_opacity', 0.3)
        if not (0.0 <= self.inactive_opacity <= 1.0):
            self.inactive_opacity = 0.3

        self.screen_region = QRect(
            category_config['x'], category_config['y'],
            category_config['width'], category_config['height']
        )
        self.anchor_region = QRect(
            category_config.get('anchor_x', 0), category_config.get('anchor_y', 0),
            category_config.get('anchor_width', 0), category_config.get('anchor_height', 0)
        )

        self.layout_direction = category_config.get('layout', 'vertical')
        self.anchor_detection_enabled = category_config.get('anchor_detection_enabled', False)
        self.anchor_image_path = category_config.get('anchor_image', '')

        # --- Important: Call setup_ui which initializes self.debuff_layout ---
        self.setup_ui()
        # --- End Important ---

        self.title_bar.set_visibility(False) # Hide title bar initially
        self.setup_detection_thread()

        self.debuff_detection_changed.connect(self.handle_debuff_update)
        self.anchor_found_changed.connect(self.handle_anchor_found_change)
        self.icon_size_changed.connect(self.handle_icon_size_change)

        self.move(
            self.category_config.get('window_x', 100),
            self.category_config.get('window_y', 100)
        )
        self.setVisible(not self.anchor_detection_enabled or self.anchor_found)
        self.installEventFilter(self)

        if self.display_mode == 'opacity':
            self.initialize_opacity_mode_icons()


    def moveEvent(self, event):
        """Update position in config when window moves"""
        super().moveEvent(event)
        # Update config directly - position_changed signal will trigger save in DebuffTracker
        self.category_config['window_x'] = self.x()
        self.category_config['window_y'] = self.y()
        self.position_changed.emit()

    def setup_ui(self):
        """Sets up the UI elements."""
        self.setWindowFlags(Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0) # No spacing for main layout

        self.title_bar = DraggableTitleBar(self.category_name, self)
        main_layout.addWidget(self.title_bar)

        # --- Create debuff_layout FIRST ---
        self.debuff_layout = QBoxLayout(QBoxLayout.TopToBottom) # Default direction
        self.debuff_layout.setContentsMargins(5, 5, 5, 5)
        self.debuff_layout.setSpacing(5)
        # --- End Create debuff_layout ---

        # Set initial layout direction based on config
        if self.layout_direction == 'horizontal':
            self.debuff_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter) # Align center vertically too
            self.debuff_layout.setDirection(QBoxLayout.LeftToRight)
            self.title_bar.toggle_button.setText("↕")
        else: # Vertical (default)
            self.debuff_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft) # Align center horizontally
            self.debuff_layout.setDirection(QBoxLayout.TopToBottom)
            self.title_bar.toggle_button.setText("↔")

        # Connect toggle button
        self.title_bar.toggle_button.clicked.connect(self.toggle_layout_direction)

        # Add the debuff layout to the main layout
        main_layout.addLayout(self.debuff_layout)
        main_layout.addStretch(1) # Add stretch to push icons up/left

        # --- Set slider value BEFORE connecting the signal ---
        self.title_bar.icon_size_slider.setValue(self.icon_size)
        # --- Connect slider signal AFTER setting value ---
        self.title_bar.icon_size_slider.valueChanged.connect(self.handle_slider_change)

        self.title_bar.settings_button.clicked.connect(self.show_settings_dialog)

        # Adjust minimum size slightly if needed, ensure title bar width is considered
        min_w = self.title_bar.width() + 10 # Margins etc.
        min_h = self.title_bar.height() + 10 # Margins etc.
        self.setMinimumSize(min_w, min_h)

        self.adjust_window_size() # Initial size adjustment after everything is created

    def show_settings_dialog(self):
        dialog = SettingsDialog(
            self.category_config, 
            self.debuff_tracker.debuffs,
            self.debuff_tracker,
            self.category_name,
            self
        )
        if dialog.exec_() == QDialog.Accepted:
            # Update config and save
            self.category_config.update(dialog.get_updated_config())
            self.debuff_tracker.save_settings()
            # Update the window's category name
            self.category_name = self.category_config['name']
            # Recreate window to apply changes
            self.debuff_tracker.recreate_category_window(self.category_name)
            # Refresh tray menu
            self.debuff_tracker.setup_tray_icon()

    def initialize_opacity_mode_icons(self):
        """Creates and adds all icons for opacity mode."""
        print(f"[{self.category_name}] Initializing icons for Opacity mode.")
        if not hasattr(self, 'debuff_layout'): # Safety check
             print(f"Error: debuff_layout not initialized before initialize_opacity_mode_icons in {self.category_name}")
             return

        # Sort debuffs by priority for consistent layout order
        sorted_debuffs = sorted(self.debuffs, key=lambda d: d.get('priority', 0))

        for debuff_data in sorted_debuffs:
            if not debuff_data.get('enabled', True):
                continue
            name = debuff_data['name']
            icon = DebuffIcon(debuff_data, self.icon_size)
            icon.set_opacity(self.inactive_opacity) # Start inactive
            self.all_debuff_icons[name] = icon
            self.debuff_layout.addWidget(icon) # Add directly to layout
        self.adjust_window_size()

    def toggle_layout_direction(self):
        """Toggles the layout between horizontal and vertical."""
        if not hasattr(self, 'debuff_layout'): return # Safety check

        # Store current widgets before clearing
        widgets = []
        while self.debuff_layout.count():
             item = self.debuff_layout.takeAt(0)
             widget = item.widget()
             if widget:
                 widgets.append(widget) # Keep track of the widget itself

        # Change direction and alignment
        if self.debuff_layout.direction() == QBoxLayout.TopToBottom:
            self.debuff_layout.setDirection(QBoxLayout.LeftToRight)
            self.debuff_layout.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.layout_direction = 'horizontal'
            self.title_bar.toggle_button.setText("↕")
        else:
            self.debuff_layout.setDirection(QBoxLayout.TopToBottom)
            self.debuff_layout.setAlignment(Qt.AlignTop | Qt.AlignLeft)
            self.layout_direction = 'vertical'
            self.title_bar.toggle_button.setText("↔")

        # Re-add widgets (order might be based on original add order or priority)
        # For simplicity, re-adding based on the stored list might suffice,
        # but for strict priority, re-querying and sorting might be needed.
        # Let's re-add based on the stored order for now.
        for widget in widgets:
             self.debuff_layout.addWidget(widget)


        self.category_config['layout'] = self.layout_direction
        self.adjust_window_size()
        self.position_changed.emit() # Save layout change

    def handle_slider_change(self, new_size):
        """ Handles slider value change """
        if not hasattr(self, 'debuff_layout'): return # Safety check
        self.icon_size = new_size
        self.icon_size_changed.emit(new_size) # Emit the signal for windows to update icons
        # Save size change via position_changed signal
        self.position_changed.emit()

    def handle_icon_size_change(self, new_size):
        """Resizes all relevant icons when icon_size_changed signal is received."""
        if not hasattr(self, 'debuff_layout'): return # Safety check
        # Resize icons based on mode
        if self.display_mode == 'opacity':
            icon_dict = self.all_debuff_icons
        else:
            icon_dict = self.active_debuffs

        for debuff_icon in icon_dict.values():
            debuff_icon.resize_icon(new_size)
        self.adjust_window_size() # Adjust window size after resizing icons


    def setup_detection_thread(self):
        """Sets up and starts the detection thread."""
        self.detection_thread = threading.Thread(target=self.detection_loop)
        self.detection_thread.daemon = True
        self.detection_thread.start()

    def detection_loop(self):
        """The main loop for detecting debuffs on screen."""
        last_detection_state = {} # Track last known state to only emit changes

        while self.detection_running:
            anchor_check_passed = False # Assume fail initially
            try:
                # --- Anchor Detection ---
                if self.anchor_detection_enabled and self.anchor_image_path:
                    with self.anchor_region_lock:
                        # Make a copy to avoid holding lock during image processing
                        anchor_region = QRect(self.anchor_region)

                    if not anchor_region.isEmpty():
                        anchor_bbox = (
                            anchor_region.x(), anchor_region.y(),
                            anchor_region.x() + anchor_region.width(), anchor_region.y() + anchor_region.height()
                        )
                        # --- Use try-except for ImageGrab ---
                        try:
                            anchor_screen = ImageGrab.grab(bbox=anchor_bbox)
                            anchor_screen_np = np.array(anchor_screen)
                            if anchor_screen_np.size == 0:
                                print(f"Warning [{self.category_name}]: Anchor ImageGrab failed (empty).")
                                raise ValueError("Empty anchor screenshot") # Treat as error

                            anchor_gray_screen = cv2.cvtColor(anchor_screen_np, cv2.COLOR_BGR2GRAY)
                            anchor_template_path = f"images/{self.anchor_image_path}"
                            # --- Cache anchor template? For now, load each time ---
                            anchor_template = cv2.imread(anchor_template_path, 0)

                            if anchor_template is not None:
                                # Check template size vs region size
                                if anchor_template.shape[0] > anchor_gray_screen.shape[0] or \
                                   anchor_template.shape[1] > anchor_gray_screen.shape[1]:
                                     print(f"Warning [{self.category_name}]: Anchor template larger than anchor region.")
                                     current_anchor_found = False
                                else:
                                     anchor_res = cv2.matchTemplate(anchor_gray_screen, anchor_template, cv2.TM_CCOEFF_NORMED)
                                     _, anchor_max_val, _, _ = cv2.minMaxLoc(anchor_res)
                                     current_anchor_found = anchor_max_val > 0.8 # Configurable threshold?

                                if current_anchor_found != self.anchor_found:
                                    self.anchor_found = current_anchor_found
                                    self.anchor_found_changed.emit(self.anchor_found) # Emit change

                                anchor_check_passed = self.anchor_found # Set based on current status

                            else: # Template file not found
                                print(f"Warning [{self.category_name}]: Anchor template not found at {anchor_template_path}")
                                if self.anchor_found: # If previously found, now it's lost
                                     self.anchor_found = False
                                     self.anchor_found_changed.emit(False)
                                anchor_check_passed = False

                        except Exception as e:
                            print(f"Anchor Detection error [{self.category_name}]: {str(e)}")
                            if self.anchor_found: # If error, assume lost
                                 self.anchor_found = False
                                 self.anchor_found_changed.emit(False)
                            anchor_check_passed = False
                    else: # Anchor region is empty
                         if self.anchor_found: # If previously found, now it's lost
                              self.anchor_found = False
                              self.anchor_found_changed.emit(False)
                         anchor_check_passed = False
                else:
                    # Anchor detection not enabled, always pass this check
                    anchor_check_passed = True
                # --- End Anchor Detection ---


                # --- Debuff Detection ---
                if anchor_check_passed:
                    with self.region_lock:
                        # Make a copy to avoid holding lock
                        current_region = QRect(self.screen_region)

                    if current_region.isEmpty():
                        # print(f"[{self.category_name}] Search region is empty, skipping detection.") # Optional info
                        time.sleep(0.5) # Wait if region is not set
                        continue

                    bbox = (
                        current_region.x(), current_region.y(),
                        current_region.x() + current_region.width(), current_region.y() + current_region.height()
                    )
                    # --- Use try-except for ImageGrab ---
                    try:
                        screen = ImageGrab.grab(bbox=bbox)
                        screen_np = np.array(screen)
                        if screen_np.size == 0:
                            print(f"Warning [{self.category_name}]: Debuff ImageGrab failed (empty).")
                            raise ValueError("Empty debuff screenshot") # Treat as error

                        gray_screen = cv2.cvtColor(screen_np, cv2.COLOR_BGR2GRAY)

                    except Exception as grab_error:
                         print(f"Debuff ImageGrab Error [{self.category_name}]: {grab_error}")
                         # If screen grab fails, assume all debuffs are not detected for this cycle
                         for debuff_name in list(last_detection_state.keys()): # Iterate over keys copy
                             if last_detection_state.get(debuff_name) is True:
                                  self.debuff_detection_changed.emit(debuff_name, False)
                                  last_detection_state[debuff_name] = False
                         time.sleep(0.5) # Wait a bit before retrying grab
                         continue # Skip rest of detection loop for this cycle


                    current_cycle_detected = set() # Track debuffs detected in this specific cycle

                    for debuff in self.debuffs:
                        if not debuff.get('enabled', True):
                            continue

                        debuff_name = debuff['name']
                        try:
                            template_path = f"images/{debuff['detect_image']}"
                            # --- Cache templates? Load each time for now ---
                            template = cv2.imread(template_path, 0)
                            if template is None:
                                # Only print warning once? Or use logging level
                                # print(f"Warning [{self.category_name}]: Template not found for {debuff_name} at {template_path}")
                                continue # Skip if template missing

                            # Check if template is smaller than screen region
                            if template.shape[0] > gray_screen.shape[0] or template.shape[1] > gray_screen.shape[1]:
                                # print(f"Warning [{self.category_name}]: Template for {debuff_name} is larger than the search region.")
                                continue # Skip if template too large

                            res = cv2.matchTemplate(gray_screen, template, cv2.TM_CCOEFF_NORMED)
                            _, max_val, _, _ = cv2.minMaxLoc(res)

                            detected = max_val >= 0.8 # Configurable threshold?

                            if detected:
                                current_cycle_detected.add(debuff_name) # Add to set for this cycle

                            # Emit signal only if state changed from last known state
                            if last_detection_state.get(debuff_name) != detected:
                                self.debuff_detection_changed.emit(debuff_name, detected)
                                last_detection_state[debuff_name] = detected # Update last known state

                        except cv2.error as cv2_err:
                             # Handle specific OpenCV errors, e.g., template larger than image after grab
                             print(f"OpenCV Error during detection [{self.category_name} - {debuff_name}]: {cv2_err}")
                             # Assume not detected if OpenCV error occurs
                             if last_detection_state.get(debuff_name) is not False:
                                 self.debuff_detection_changed.emit(debuff_name, False)
                                 last_detection_state[debuff_name] = False
                        except Exception as e:
                            print(f"Detection error [{self.category_name} - {debuff_name}]: {str(e)}")
                            # If other error occurs, assume not detected and emit if state changed
                            if last_detection_state.get(debuff_name) is not False:
                                self.debuff_detection_changed.emit(debuff_name, False)
                                last_detection_state[debuff_name] = False


                    # Check for debuffs that were previously detected but not in this cycle
                    # These need to be explicitly marked as False if they weren't already
                    disappeared_debuffs = set(last_detection_state.keys()) - current_cycle_detected
                    for name in disappeared_debuffs:
                         if last_detection_state.get(name) is True: # Check if it was *actually* True before
                              self.debuff_detection_changed.emit(name, False)
                              last_detection_state[name] = False

                else: # Anchor check failed
                    # If anchor check failed, treat all *currently tracked* debuffs as 'not detected'
                    # Iterate over a copy of keys as the dictionary might change
                    for debuff_name in list(last_detection_state.keys()):
                         if last_detection_state.get(debuff_name) is True: # If it was detected
                              self.debuff_detection_changed.emit(debuff_name, False) # Emit not detected
                              last_detection_state[debuff_name] = False # Update state


                # --- Sleep ---
                # Adjust sleep time based on needs. Shorter means more CPU usage.
                time.sleep(0.25) # Increased slightly from 0.2

            except Exception as e:
                # Catch errors in the main loop structure itself
                print(f"Outer Detection loop error [{self.category_name}]: {str(e)}")
                # Avoid busy-waiting on continuous errors
                time.sleep(1) # Wait longer after a major loop error


    def handle_debuff_update(self, name, detected):
        """Handles updates based on detection state and display mode."""
        # print(f"[{self.category_name}] Update for {name}: Detected={detected}, Mode={self.display_mode}") # Debug
        if not hasattr(self, 'debuff_layout'): return # Safety check

        if self.display_mode == 'opacity':
            if name in self.all_debuff_icons:
                opacity = 1.0 if detected else self.inactive_opacity
                self.all_debuff_icons[name].set_opacity(opacity)
            # else: # Icon should always exist in opacity mode if initialized correctly
            #      print(f"Warning: Icon for {name} not found in all_debuff_icons for opacity mode.")

        elif self.display_mode == 'invert':
            # Show when detected, hide when not detected
            if detected:
                self.add_debuff_icon(name)
            else:
                self.remove_debuff_icon(name)

        else: # Default mode
            # Show when NOT detected, hide when detected
            if not detected:
                self.add_debuff_icon(name)
            else:
                self.remove_debuff_icon(name)

    def add_debuff_icon(self, name):
        """Adds a debuff icon to the layout in the order specified by selected_debuffs."""
        if not hasattr(self, 'debuff_layout') or name in self.active_debuffs:
            return

        debuff_data = next((d for d in self.debuffs if d['name'] == name), None)
        if not debuff_data:
            return

        # Create the icon
        icon = DebuffIcon(debuff_data, self.icon_size)
        self.active_debuffs[name] = icon

        # Get the position from selected_debuffs
        try:
            # Get the full list of selected debuff names
            selected_order = self.category_config.get('selected_debuffs', [])
            target_index = selected_order.index(name)
            
            # Count how many preceding debuffs are currently active
            insert_position = 0
            for preceding_name in selected_order[:target_index]:
                if preceding_name in self.active_debuffs:
                    insert_position += 1

            # Insert at the calculated position
            self.debuff_layout.insertWidget(insert_position, icon)
        except ValueError:
            # If not found in selected_debuffs, append to end (shouldn't happen normally)
            self.debuff_layout.addWidget(icon)

        icon.show()
        self.adjust_window_size()

    def remove_debuff_icon(self, name):
        """Removes a debuff icon from the layout (for default/invert modes)."""
        if not hasattr(self, 'debuff_layout'): return # Safety check
        if name in self.active_debuffs:
            # print(f"[{self.category_name}] Removing icon: {name}") # Debug
            widget = self.active_debuffs.pop(name)
            # Remove from layout explicitly before deleting
            self.debuff_layout.removeWidget(widget)
            widget.deleteLater() # Schedule for deletion
            self.adjust_window_size()


    def adjust_window_size(self):
        """Adjusts the window size based on icon count, size, and layout."""
        # Safety checks
        if not hasattr(self, 'title_bar') or not self.title_bar: return
        if not hasattr(self, 'debuff_layout') or not self.debuff_layout: return

        title_height = self.title_bar.height() if self.title_bar.is_visible else 0
        icon_count = self.debuff_layout.count() # Count widgets currently in layout

        spacing = self.debuff_layout.spacing()
        margins = self.debuff_layout.contentsMargins()

        # Use current icon_size attribute
        current_icon_size = self.icon_size

        # Calculate required content size
        if icon_count == 0:
             content_width = 0
             content_height = 0
        elif self.layout_direction == 'vertical':
            content_width = current_icon_size
            content_height = (current_icon_size * icon_count) + (spacing * max(0, icon_count - 1)) + 20
        else: # Horizontal
            content_width = (current_icon_size * icon_count) + (spacing * max(0, icon_count - 1))
            content_height = current_icon_size + 15

        # Calculate total size including margins and title bar
        total_width = content_width + margins.left() + margins.right()
        total_height = title_height + content_height + margins.top() + margins.bottom()

        # Ensure minimum size to accommodate title bar and some padding
        min_width = self.title_bar.width() + margins.left() + margins.right() + 10
        # Minimum height includes title bar height + minimum content area (e.g., 10px)
        min_height = title_height + margins.top() + margins.bottom() + 10

        # Set the fixed size, respecting minimums
        final_width = max(total_width, min_width)
        final_height = max(total_height, min_height)

        # Use resize instead of setFixedSize to allow potential future resizing?
        # For now, setFixedSize matches previous behavior.
        self.setFixedSize(final_width, final_height)

        # print(f"[{self.category_name}] Adjusting size: W={final_width}, H={final_height}, Icons: {icon_count}, IconSize: {current_icon_size}, Mode: {self.display_mode}") # Debug


    def update_region(self, new_region):
        """Updates the screen region to monitor."""
        with self.region_lock:
            self.screen_region = new_region
        print(f"[{self.category_name}] Search region updated to: {new_region}")

    def update_anchor_region(self, new_region):
        """Updates the anchor region."""
        with self.anchor_region_lock:
            self.anchor_region = new_region
        print(f"[{self.category_name}] Anchor region updated to: {new_region}")

    def handle_anchor_found_change(self, found):
        """Shows or hides the window based on anchor status."""
        if not hasattr(self, 'debuff_layout'): return # Safety check

        self.setVisible(found or not self.anchor_detection_enabled)
        # print(f"[{self.category_name}] Anchor found: {found}. Window visible: {self.isVisible()}")

    def closeEvent(self, event):
        """Stops the detection thread on close."""
        print(f"Closing category window: {self.category_name}")
        self.detection_running = False # Signal thread to stop
        # Wait for thread to finish before proceeding
        if hasattr(self, 'detection_thread') and self.detection_thread.is_alive():
            print(f"Waiting for detection thread in {self.category_name} to finish...")
            self.detection_thread.join(timeout=1.5) # Increased timeout slightly
            if self.detection_thread.is_alive():
                 print(f"Warning: Detection thread in {self.category_name} did not exit cleanly.")
        super().closeEvent(event) # Call parent closeEvent

    def eventFilter(self, obj, event):
        """Shows/hides the title bar on window activation/deactivation."""
        # Ensure layout exists before adjusting size
        if not hasattr(self, 'debuff_layout'):
             return super().eventFilter(obj, event)

        if obj is self: # Filter events only for this window
            if event.type() == QEvent.WindowActivate:
                # print(f"[{self.category_name}] Window Activated") # Debug
                if hasattr(self, 'title_bar'):
                    self.title_bar.set_visibility(True)
                    self.adjust_window_size() # Recalculate size with title bar
            elif event.type() == QEvent.WindowDeactivate:
                # print(f"[{self.category_name}] Window Deactivated") # Debug
                if hasattr(self, 'title_bar'):
                    self.title_bar.set_visibility(False)
                    self.adjust_window_size() # Recalculate size without title bar
        return super().eventFilter(obj, event)

# --- DebuffTracker Class (Mostly Unchanged, minor logging/init order) ---
class DebuffTracker(QWidget):
    def __init__(self):
        super().__init__()
        self.categories = []
        self.category_windows = []
        self.tray_icon = None
        self.active_selector = None
        self.anchor_selector = None
        self.debuffs = [] # Initialize debuffs list

        # --- Load settings and debuffs before creating UI ---
        self.load_settings()
        self.load_debuffs()
        # --- End Load ---

        self.setup_tray_icon()
        self.create_category_windows() # Create windows after loading data

    def load_settings(self):
        """Loads category settings from settings.json."""
        default_settings = {'categories': []}
        settings_path = Path('settings.json')
        try:
            if not settings_path.exists():
                 print(f"{settings_path} not found, creating default.")
                 with open(settings_path, 'w') as f:
                      json.dump(default_settings, f, indent=2)
                 settings = default_settings
            else:
                 with open(settings_path) as f:
                      settings = json.load(f)
                 if not isinstance(settings.get('categories'), list):
                      print("Warning: 'categories' key in settings.json is not a list. Using defaults.")
                      settings = default_settings

        except json.JSONDecodeError:
             print(f"Error decoding {settings_path}, using defaults.")
             settings = default_settings
        except Exception as e:
            print(f"Unexpected error loading settings: {str(e)}, using defaults.")
            settings = default_settings


        self.categories = settings.get('categories', [])
        needs_save = False
        # Ensure all required fields exist, including new ones
        for i, cat in enumerate(self.categories):
            # Using setdefault returns the value, check if it was the default to see if save needed
            if cat.setdefault('name', f'Category_{i+1}') == f'Category_{i+1}' and 'name' not in cat: needs_save = True
            if cat.setdefault('x', 0) == 0 and 'x' not in cat: needs_save = True
            if cat.setdefault('y', 0) == 0 and 'y' not in cat: needs_save = True
            if cat.setdefault('width', 100) == 100 and 'width' not in cat: needs_save = True
            if cat.setdefault('height', 100) == 100 and 'height' not in cat: needs_save = True
            if cat.setdefault('window_x', 100 + i*50) == 100 + i*50 and 'window_x' not in cat: needs_save = True
            if cat.setdefault('window_y', 100 + i*50) == 100 + i*50 and 'window_y' not in cat: needs_save = True
            if cat.setdefault('anchor_detection_enabled', False) is False and 'anchor_detection_enabled' not in cat: needs_save = True
            if cat.setdefault('anchor_image', '') == '' and 'anchor_image' not in cat: needs_save = True # Allow empty string
            if cat.setdefault('anchor_x', 0) == 0 and 'anchor_x' not in cat: needs_save = True
            if cat.setdefault('anchor_y', 0) == 0 and 'anchor_y' not in cat: needs_save = True
            if cat.setdefault('anchor_width', 0) == 0 and 'anchor_width' not in cat: needs_save = True
            if cat.setdefault('anchor_height', 0) == 0 and 'anchor_height' not in cat: needs_save = True
            if cat.setdefault('icon_size', 48) == 48 and 'icon_size' not in cat: needs_save = True
            if cat.setdefault('layout', 'vertical') == 'vertical' and 'layout' not in cat: needs_save = True
            # --- New Fields ---
            if cat.setdefault('display_mode', 'default') == 'default' and 'display_mode' not in cat: needs_save = True
            if cat.setdefault('inactive_opacity', 0.3) == 0.3 and 'inactive_opacity' not in cat: needs_save = True
            cat.setdefault('selected_debuffs', [])
            if 'debuffs' in cat:
                del cat['debuffs']
            # Validate opacity range
            cat['inactive_opacity'] = max(0.0, min(1.0, cat.get('inactive_opacity', 0.3)))


        if needs_save:
            print("Updating settings.json with default values for missing fields.")
            self.save_settings_internal(settings) # Use internal save to avoid loop


    def save_settings(self):
        """Saves current category settings to settings.json. Triggered by signals."""
        # Ensure all category configs are up-to-date from windows
        for window in self.category_windows:
            for cat in self.categories:
                if cat['name'] == window.category_name:
                    # Update config from the window state BEFORE saving
                    cat['window_x'] = window.x()
                    cat['window_y'] = window.y()
                    cat['icon_size'] = window.icon_size # Get current icon size
                    cat['layout'] = window.layout_direction # Get current layout
                    # Regions are updated directly in update_category_region/anchor_region
                    break

        settings_to_save = {'categories': self.categories}
        self.save_settings_internal(settings_to_save)

    def save_settings_internal(self, settings_dict):
        """Internal method to write settings to file."""
        settings_path = Path('settings.json')
        try:
            with open(settings_path, 'w') as f:
                json.dump(settings_dict, f, indent=2)
            # print("Settings saved.") # Optional confirmation
        except Exception as e:
            print(f"Error saving settings to {settings_path}: {str(e)}")


    def load_debuffs(self):
        """Loads debuff definitions from debuffs.json."""
        debuffs_path = Path('debuffs.json')
        default_debuffs = []
        try:
            if not debuffs_path.exists():
                print(f"{debuffs_path} not found. No debuffs loaded.")
                self.debuffs = default_debuffs
                return

            with open(debuffs_path) as f:
                loaded_data = json.load(f)
                if not isinstance(loaded_data, list):
                    print(f"Warning: {debuffs_path} should contain a list. Loading empty list.")
                    self.debuffs = default_debuffs
                    return

                self.debuffs = []
                for i, debuff in enumerate(loaded_data):
                    if not isinstance(debuff, dict):
                        print(f"Warning: Item at index {i} in debuffs.json is not a dictionary. Skipping.")
                        continue

                    # Validate required fields
                    required = ['name', 'detect_image', 'icon_image']
                    if not all(key in debuff for key in required):
                        print(f"Warning: Debuff at index {i} is missing required fields. Skipping.")
                        continue

                    self.debuffs.append(debuff)

        except Exception as e:
            print(f"Error loading debuffs: {str(e)}")
            self.debuffs = default_debuffs

    def create_category_windows(self):
        """Creates the CategoryWindow instances based on settings."""
        for window in self.category_windows:
            window.close()
        self.category_windows.clear()

        # Create lookup dictionary for debuffs
        debuff_dict = {d['name']: d for d in self.debuffs}

        for category_config in self.categories:
            category_name = category_config.get('name', 'Unnamed Category')
            selected_names = category_config.get('selected_debuffs', [])
            
            # Get debuffs in order of selected_names
            category_debuffs = []
            for name in selected_names:
                if name in debuff_dict:
                    category_debuffs.append(debuff_dict[name])
                else:
                    print(f"Warning: Debuff '{name}' not found for category '{category_name}'")

            try:
                window = CategoryWindow(category_config, category_debuffs, self)
                window.position_changed.connect(self.save_settings)
                window.show()
                self.category_windows.append(window)
            except Exception as e:
                print(f"Error creating window for category '{category_name}': {e}")

    def setup_tray_icon(self):
        """Sets up the system tray icon and menu."""
        if not QSystemTrayIcon.isSystemTrayAvailable():
            print("System tray not available.")
            return

        # If tray icon already exists, just update menu? Or recreate? Recreate for simplicity.
        if self.tray_icon:
             self.tray_icon.hide()

        self.tray_icon = QSystemTrayIcon(self)
        self.tray_icon.setToolTip("Debuff Tracker")

        icon_path = Path("images/uppercut_icon.png") # Example icon path
        if icon_path.exists() and icon_path.is_file():
            self.tray_icon.setIcon(QIcon(str(icon_path)))
        else:
            print(f"Tray icon not found or invalid at {icon_path}, using default.")
            pixmap = QPixmap(32, 32)
            pixmap.fill(QColor(60, 60, 60)) # Slightly lighter default
            # Draw a simple shape or letter?
            painter = QPainter(pixmap)
            painter.setPen(QColor(200, 200, 200))
            painter.setFont(QFont("Arial", 16, QFont.Bold))
            painter.drawText(pixmap.rect(), Qt.AlignCenter, "D")
            painter.end()
            self.tray_icon.setIcon(QIcon(pixmap))

        menu = QMenu()

        categories_menu = menu.addMenu("Categories")
        for category in self.categories:
            cat_name = category.get('name', 'Unnamed Category')
            cat_action = QAction(cat_name, self)
            cat_action.triggered.connect(
                lambda checked, name=cat_name: self.open_category_settings(name)
            )
            categories_menu.addAction(cat_action)

        new_action = QAction("New Category", self)
        new_action.triggered.connect(self.add_new_category)
        categories_menu.addAction(new_action)
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close_all)
        menu.addAction(exit_action)

        self.tray_icon.setContextMenu(menu)
        self.tray_icon.show()

    def open_category_settings(self, category_name):
        for window in self.category_windows:
            if window.category_name == category_name:
                window.show_settings_dialog()
                return
        print(f"Category window for {category_name} not found.")

    def add_new_category(self):
        # Generate unique name
        existing_names = {cat['name'] for cat in self.categories}
        new_name = "New Category"
        count = 1
        while f"{new_name} {count}" in existing_names:
            count += 1
        new_name = f"{new_name} {count}"
        
        # Default configuration
        new_category = {
            'name': new_name,
            'x': 0, 'y': 0, 'width': 100, 'height': 100,
            'window_x': 100, 'window_y': 100,
            'anchor_detection_enabled': False,
            'anchor_image': '',
            'anchor_x': 0, 'anchor_y': 0, 'anchor_width': 0, 'anchor_height': 0,
            'icon_size': 48, 'layout': 'vertical',
            'display_mode': 'default', 'inactive_opacity': 0.3,
            'selected_debuffs': []
        }
        self.categories.append(new_category)
        self.save_settings()
        self.create_category_windows()
        self.setup_tray_icon()
        # Open settings for the new category
        for window in self.category_windows:
            if window.category_name == new_name:
                window.show_settings_dialog()
                break

    def delete_category(self, category_name):
        # Remove category from config
        self.categories = [c for c in self.categories if c['name'] != category_name]
        
        # Close and remove associated window
        for window in self.category_windows[:]:
            if window.category_name == category_name:
                window.close()
                self.category_windows.remove(window)
        
        self.save_settings()
        self.setup_tray_icon()  # Refresh tray menu
        print(f"Deleted category: {category_name}")

    def handle_region_selection(self, category_name):
        """Starts the region selection process for a category by name."""
        print(f"Starting region selection for {category_name}")
        # Find the category config by name
        category_config = next((c for c in self.categories if c['name'] == category_name), None)
        if not category_config:
            print(f"Category {category_name} not found.")
            return
        # Existing logic to show selector and connect signal
        if self.active_selector and self.active_selector.isVisible():
            print("Region selector already active.")
            self.active_selector.activateWindow()
            return
        self.active_selector = RegionSelector()
        self.active_selector.selection_complete.connect(
            lambda rect, name=category_name: self.update_category_region(name, rect)
        )
        self.active_selector.showFullScreen()

    def handle_anchor_selection(self, category_name):
        """Starts the anchor region selection process by category name."""
        print(f"Starting anchor selection for {category_name}")
        category_config = next((c for c in self.categories if c['name'] == category_name), None)
        if not category_config:
            print(f"Category {category_name} not found.")
            return
        if self.anchor_selector and self.anchor_selector.isVisible():
            print("Anchor selector already active.")
            self.anchor_selector.activateWindow()
            return
        self.anchor_selector = RegionSelector()
        self.anchor_selector.selection_complete.connect(
            lambda rect, name=category_name: self.update_category_anchor_region(name, rect)
        )
        self.anchor_selector.showFullScreen()

    def update_category_region(self, category_name, rect):
        """Updates the detection region for a specific category by name."""
        print(f"Updating region for {category_name} to {rect}")
        # Find the category in self.categories
        for category in self.categories:
            if category['name'] == category_name:
                category.update({
                    'x': rect.x(), 'y': rect.y(),
                    'width': rect.width(), 'height': rect.height()
                })
                # Update the window's region
                window_updated = False
                for window in self.category_windows:
                    if window.category_name == category_name:
                        window.update_region(rect)
                        window_updated = True
                        break
                if not window_updated:
                    print(f"Warning: Could not find window for {category_name}")
                self.save_settings()
                break
        else:
            print(f"Category {category_name} not found in settings.")

    def update_category_anchor_region(self, category_name, rect):
        """Updates the anchor region for a specific category by name."""
        print(f"Updating anchor region for {category_name} to {rect}")
        for category in self.categories:
            if category['name'] == category_name:
                category.update({
                    'anchor_x': rect.x(), 'anchor_y': rect.y(),
                    'anchor_width': rect.width(), 'anchor_height': rect.height()
                })
                # Update the window's anchor region
                window_updated = False
                for window in self.category_windows:
                    if window.category_name == category_name:
                        window.update_anchor_region(rect)
                        window_updated = True
                        break
                if not window_updated:
                    print(f"Warning: Could not find window for {category_name}")
                self.save_settings()
                break
        else:
            print(f"Category {category_name} not found in settings.")
    
    def recreate_category_window(self, category_name):
        # Close existing window
        for window in self.category_windows[:]:
            if window.category_name == category_name:
                window.close()
                self.category_windows.remove(window)
        
        # Create new window
        category_config = next((c for c in self.categories if c['name'] == category_name), None)
        if category_config:
            selected_names = category_config.get('selected_debuffs', [])
            debuff_dict = {d['name']: d for d in self.debuffs}
            category_debuffs = [debuff_dict[name] for name in selected_names if name in debuff_dict]
            new_window = CategoryWindow(category_config, category_debuffs, self)  # Pass self as tracker
            new_window.position_changed.connect(self.save_settings)
            new_window.show()
            self.category_windows.append(new_window)
        # Refresh the tray icon to reflect changes
        self.setup_tray_icon()
        
    # --- Optional Reload Functionality ---
    # def reload_all(self):
    #     """Reloads settings and debuffs, then recreates windows."""
    #     print("Reloading settings and debuffs...")
    #     # Stop detection in existing windows first
    #     for window in self.category_windows:
    #         window.detection_running = False
    #         if hasattr(window, 'detection_thread') and window.detection_thread.is_alive():
    #             window.detection_thread.join(timeout=0.5)
    #         window.close() # Close existing windows
    #     self.category_windows.clear()

    #     # Reload data
    #     self.load_settings()
    #     self.load_debuffs()

    #     # Recreate UI elements
    #     self.setup_tray_icon() # Update tray menu if categories changed
    #     self.create_category_windows() # Create new windows
    #     print("Reload complete.")
    # --- End Reload ---

    def close_all(self):
        """Closes all category windows and exits the application."""
        print("Exiting application...")
        if self.tray_icon:
            self.tray_icon.hide()

        # Make copies of lists to iterate over as closing modifies them
        windows_to_close = list(self.category_windows)
        print(f"Closing {len(windows_to_close)} category windows...")

        for window in windows_to_close:
            try:
                 window.close() # This should trigger the window's closeEvent
            except Exception as e:
                 print(f"Error closing window {window.category_name}: {e}")

        self.category_windows.clear() # Clear the list

        # Ensure the application instance quits properly
        app_instance = QApplication.instance()
        if app_instance:
             print("Quitting QApplication...")
             app_instance.quit()
        else:
             print("No QApplication instance found to quit.")


if __name__ == "__main__":
    # Ensure images directory exists
    img_dir = Path("images")
    img_dir.mkdir(exist_ok=True)
    print(f"Image directory: {img_dir.resolve()}")

    app = QApplication(sys.argv)
    # Import QFont here if needed for default icon
    from PyQt5.QtGui import QFont

    # Set quit on last window closed to false so app runs in background via tray icon
    app.setQuitOnLastWindowClosed(False)

    # --- Exception Hook for Uncaught Exceptions ---
    def handle_exception(exc_type, exc_value, exc_traceback):
        """Log uncaught exceptions."""
        import traceback
        error_message = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        print(f"UNCAUGHT EXCEPTION:\n{error_message}")
        # Optionally: Log to a file
        # with open("error_log.txt", "a") as f:
        #    f.write(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] UNCAUGHT EXCEPTION:\n{error_message}\n")
        # Attempt graceful exit?
        QApplication.instance().quit()

    sys.excepthook = handle_exception
    # --- End Exception Hook ---


    manager = DebuffTracker()
    # The manager itself is a QWidget but doesn't need to be shown

    # Handle termination signals (like Ctrl+C) gracefully
    # Note: This might not work reliably on all OS/environments, especially Windows console
    try:
        import signal
        signal.signal(signal.SIGINT, lambda sig, frame: manager.close_all())
        signal.signal(signal.SIGTERM, lambda sig, frame: manager.close_all())
    except ImportError:
        print("Signal handling not available on this platform.")
    except Exception as sig_err:
        print(f"Error setting up signal handlers: {sig_err}")


    print("Debuff Tracker started. Use tray icon to manage.")
    try:
        exit_code = app.exec_()
        print(f"Application exited with code {exit_code}.")
        sys.exit(exit_code)
    except Exception as main_err:
         print(f"Error during app execution: {main_err}")
         # Log the exception if hook didn't catch it
         import traceback
         traceback.print_exc()
         sys.exit(1) # Exit with error code
