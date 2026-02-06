"""
Device Selection Panel
UI for selecting audio input and output devices
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib

from typing import Optional, Callable, List
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from audio_manager import AudioManager, AudioDevice, DeviceType


class DevicePanel(Gtk.Box):
    """Panel for selecting audio input and output devices"""
    
    def __init__(self, audio_manager: AudioManager):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        
        self.audio_manager = audio_manager
        self._on_input_changed: Optional[Callable[[AudioDevice], None]] = None
        self._on_output_changed: Optional[Callable[[AudioDevice], None]] = None
        
        self._setup_ui()
        self._refresh_devices()
        
        # Set up device change callback
        audio_manager.set_callbacks(
            on_devices_changed=self._refresh_devices
        )
        
    def _setup_ui(self):
        """Build the UI"""
        self.add_css_class('device-panel')
        
        # Input Device Section
        input_section = self._create_section("INPUT SOURCE", "audio-input-microphone-symbolic")
        self.append(input_section)
        
        self.input_dropdown = Gtk.DropDown()
        self.input_dropdown.set_hexpand(True)
        self.input_dropdown.connect("notify::selected", self._on_input_selected)
        input_section.append(self.input_dropdown)
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        self.append(separator)
        
        # Output Device Section  
        output_section = self._create_section("OUTPUT DEVICE", "audio-speakers-symbolic")
        self.append(output_section)
        
        self.output_dropdown = Gtk.DropDown()
        self.output_dropdown.set_hexpand(True)
        self.output_dropdown.connect("notify::selected", self._on_output_selected)
        output_section.append(self.output_dropdown)
        
        # Warning box (hidden by default)
        self.warning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        self.warning_box.add_css_class('warning-box')
        self.warning_box.set_visible(False)
        
        warning_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        self.warning_box.append(warning_icon)
        
        warning_label = Gtk.Label(
            label="Headset detected - audio may route to headphones"
        )
        warning_label.set_wrap(True)
        self.warning_box.append(warning_label)
        
        self.append(self.warning_box)
        
    def _create_section(self, title: str, icon_name: str) -> Gtk.Box:
        """Create a labeled section"""
        section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        
        # Header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.add_css_class('device-icon')
        header.append(icon)
        
        label = Gtk.Label(label=title)
        label.add_css_class('section-label')
        label.set_xalign(0)
        header.append(label)
        
        section.append(header)
        
        return section
        
    def _refresh_devices(self):
        """Refresh device dropdowns"""
        # Get devices
        input_devices = self.audio_manager.get_input_devices()
        output_devices = self.audio_manager.get_output_devices()
        
        # Update input dropdown
        input_names = [d.display_name for d in input_devices]
        self.input_dropdown.set_model(Gtk.StringList.new(input_names))
        
        # Select current input
        current_input = self.audio_manager.get_current_input()
        if current_input:
            for i, device in enumerate(input_devices):
                if device.name == current_input.name:
                    self.input_dropdown.set_selected(i)
                    break
                    
        # Update output dropdown
        output_names = [d.display_name for d in output_devices]
        self.output_dropdown.set_model(Gtk.StringList.new(output_names))
        
        # Select current output
        current_output = self.audio_manager.get_current_output()
        if current_output:
            for i, device in enumerate(output_devices):
                if device.name == current_output.name:
                    self.output_dropdown.set_selected(i)
                    break
                    
        # Update warning visibility
        self.warning_box.set_visible(self.audio_manager.has_headphone_conflict)
        
    def _on_input_selected(self, dropdown, _pspec):
        """Handle input device selection"""
        selected = dropdown.get_selected()
        devices = self.audio_manager.get_input_devices()
        
        if 0 <= selected < len(devices):
            device = devices[selected]
            self.audio_manager.set_input_device(device)
            
            if self._on_input_changed:
                self._on_input_changed(device)
                
    def _on_output_selected(self, dropdown, _pspec):
        """Handle output device selection"""
        selected = dropdown.get_selected()
        devices = self.audio_manager.get_output_devices()
        
        if 0 <= selected < len(devices):
            device = devices[selected]
            self.audio_manager.set_output_device(device)
            
            if self._on_output_changed:
                self._on_output_changed(device)
                
        # Check for headphone conflicts after change
        self.warning_box.set_visible(self.audio_manager.has_headphone_conflict)
        
    def set_callbacks(
        self,
        on_input_changed: Optional[Callable[[AudioDevice], None]] = None,
        on_output_changed: Optional[Callable[[AudioDevice], None]] = None
    ):
        """Set callback functions"""
        self._on_input_changed = on_input_changed
        self._on_output_changed = on_output_changed
        
    def refresh(self):
        """Force refresh of devices"""
        self.audio_manager.refresh_devices()
        self._refresh_devices()
        
    def is_android_selected(self) -> bool:
        """Check if Android input is selected"""
        return self.audio_manager.is_android_input_selected()
