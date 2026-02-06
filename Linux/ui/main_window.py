"""
Main Application Window
Primary UI for PulseLink audio streaming server
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw, GLib, Gio

import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from server import AudioServer, ServerState, ClientInfo
from audio_manager import AudioManager
from local_audio import LocalAudioCapture, LocalAudioState
from ui.qr_display import QRDisplay
from ui.device_panel import DevicePanel
from ui.audio_visualizer import AudioVisualizer


class MainWindow(Adw.ApplicationWindow):
    """Main application window for PulseLink"""
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        
        # Initialize components
        self.audio_manager = AudioManager()
        self.server = AudioServer(port=5555)
        self.local_audio = LocalAudioCapture()
        
        # Current mode: 'android' or 'local'
        self.current_mode = 'local'
        
        # Set up server callbacks
        self.server.set_callbacks(
            on_state_change=self._on_server_state_change,
            on_client_connect=self._on_client_connect,
            on_client_disconnect=self._on_client_disconnect,
            on_audio_level=self._on_audio_level,
            on_error=self._on_server_error
        )
        
        # Set up local audio callbacks
        self.local_audio.set_callbacks(
            on_state_change=self._on_local_audio_state_change,
            on_error=self._on_local_audio_error
        )
        
        # Window setup
        self.set_title("PulseLink")
        self.set_default_size(480, 780)
        
        # Load CSS
        self._load_css()
        
        # Build UI
        self._setup_ui()
        
    def _load_css(self):
        """Load custom CSS"""
        css_provider = Gtk.CssProvider()
        css_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'style.css')
        
        try:
            css_provider.load_from_path(css_path)
            Gtk.StyleContext.add_provider_for_display(
                self.get_display(),
                css_provider,
                Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
            )
        except Exception as e:
            print(f"Warning: Could not load CSS: {e}")
            
    def _setup_ui(self):
        """Build the main UI"""
        # Main content box
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self.set_content(main_box)
        
        # Header bar
        header = Adw.HeaderBar()
        header.set_title_widget(self._create_header_title())
        main_box.append(header)
        
        # Refresh button
        refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        refresh_btn.set_tooltip_text("Refresh devices")
        refresh_btn.connect("clicked", self._on_refresh_clicked)
        header.pack_start(refresh_btn)
        
        # Scrollable content
        scroll = Gtk.ScrolledWindow()
        scroll.set_vexpand(True)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        main_box.append(scroll)
        
        # Content container
        content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        content.set_margin_start(16)
        content.set_margin_end(16)
        content.set_margin_top(8)
        content.set_margin_bottom(16)
        scroll.set_child(content)
        
        # Status Card
        status_card = self._create_status_card()
        content.append(status_card)
        
        # Mode Selection Card (Local Mic vs Android)
        mode_card = self._create_mode_card()
        content.append(mode_card)
        
        # Local Audio Card (Input/Output selection with port control)
        self.local_audio_card = self._create_local_audio_card()
        content.append(self.local_audio_card)
        
        # QR Code Card (for Android mode)
        self.qr_card = self._create_qr_card()
        self.qr_card.set_visible(False)  # Hidden by default (local mode)
        content.append(self.qr_card)
        
        # Audio Visualizer Card
        visualizer_card = self._create_visualizer_card()
        content.append(visualizer_card)
        
        # Main Control Button
        self.main_button = self._create_main_button()
        content.append(self.main_button)
        
    def _create_header_title(self) -> Gtk.Widget:
        """Create custom header title"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        
        # App icon
        icon = Gtk.Image.new_from_icon_name("audio-card-symbolic")
        box.append(icon)
        
        # Title
        title = Gtk.Label(label="PulseLink")
        title.add_css_class('title-label')
        box.append(title)
        
        return box
        
    def _create_status_card(self) -> Gtk.Widget:
        """Create status display card"""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class('card')
        
        # Header row
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        card.append(header)
        
        # Status indicator
        self.status_dot = Gtk.DrawingArea()
        self.status_dot.set_size_request(12, 12)
        self.status_dot.add_css_class('status-dot')
        self.status_dot.add_css_class('disconnected')
        header.append(self.status_dot)
        
        # Status text
        status_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        status_box.set_hexpand(True)
        
        self.status_label = Gtk.Label(label="Ready")
        self.status_label.add_css_class('title-label')
        self.status_label.set_xalign(0)
        status_box.append(self.status_label)
        
        self.status_detail = Gtk.Label(label="Select input and output, then start")
        self.status_detail.add_css_class('subtitle-label')
        self.status_detail.set_xalign(0)
        status_box.append(self.status_detail)
        
        header.append(status_box)
        
        return card
        
    def _create_mode_card(self) -> Gtk.Widget:
        """Create mode selection card (Local Mic vs Android)"""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class('card')
        
        # Section header
        label = Gtk.Label(label="INPUT MODE")
        label.add_css_class('section-label')
        label.set_xalign(0)
        card.append(label)
        
        # Mode toggle buttons
        mode_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        mode_box.set_homogeneous(True)
        card.append(mode_box)
        
        # Local Mic button
        self.local_mode_btn = Gtk.ToggleButton(label="Local Microphone")
        self.local_mode_btn.set_active(True)
        self.local_mode_btn.add_css_class('primary-button')
        self.local_mode_btn.connect("toggled", self._on_mode_changed, 'local')
        mode_box.append(self.local_mode_btn)
        
        # Android button
        self.android_mode_btn = Gtk.ToggleButton(label="Android Device")
        self.android_mode_btn.add_css_class('secondary-button')
        self.android_mode_btn.connect("toggled", self._on_mode_changed, 'android')
        mode_box.append(self.android_mode_btn)
        
        return card
        
    def _create_local_audio_card(self) -> Gtk.Widget:
        """Create local audio routing card with mic->speaker routing"""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        card.add_css_class('card')

        # Limitation info box
        limit_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        limit_box.add_css_class('info-box')
        limit_box.set_margin_top(8)
        
        limit_icon = Gtk.Image.new_from_icon_name("dialog-information-symbolic")
        limit_box.append(limit_icon)
        
        limit_label = Gtk.Label(label="Known Limitation: On some systems, audio may not output through speakers when headphones are connected due to hardware-level jack detection. We are investigating solutions. However, it may still work on your system - feel free to try it!")
        limit_label.set_wrap(True)
        limit_label.set_xalign(0)
        limit_box.append(limit_label)
        
        card.append(limit_box)
        
        # Section header
        label = Gtk.Label(label="AUDIO ROUTING")
        label.add_css_class('section-label')
        label.set_xalign(0)
        card.append(label)
        
        # Input device selection
        input_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.append(input_section)
        
        input_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_icon = Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic")
        input_icon.add_css_class('device-icon')
        input_header.append(input_icon)
        input_label = Gtk.Label(label="Input (Microphone)")
        input_label.add_css_class('subtitle-label')
        input_header.append(input_label)
        input_section.append(input_header)
        
        self.input_dropdown = Gtk.DropDown()
        self.input_dropdown.set_hexpand(True)
        input_section.append(self.input_dropdown)
        
        # Input port selection (for choosing between built-in mic and headphone mic)
        input_port_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        input_port_section.set_margin_top(8)
        card.append(input_port_section)
        
        input_port_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        input_port_icon = Gtk.Image.new_from_icon_name("audio-input-microphone-symbolic")
        input_port_icon.add_css_class('device-icon')
        input_port_header.append(input_port_icon)
        input_port_label = Gtk.Label(label="Input Port (Mic Type)")
        input_port_label.add_css_class('subtitle-label')
        input_port_header.append(input_port_label)
        input_port_section.append(input_port_header)
        
        self.input_port_dropdown = Gtk.DropDown()
        self.input_port_dropdown.set_hexpand(True)
        input_port_section.append(self.input_port_dropdown)
        
        # Separator
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(8)
        separator.set_margin_bottom(8)
        card.append(separator)
        
        # Output device selection
        output_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        card.append(output_section)
        
        output_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        output_icon = Gtk.Image.new_from_icon_name("audio-speakers-symbolic")
        output_icon.add_css_class('device-icon')
        output_header.append(output_icon)
        output_label = Gtk.Label(label="Output (Speakers)")
        output_label.add_css_class('subtitle-label')
        output_header.append(output_label)
        output_section.append(output_header)
        
        self.output_dropdown = Gtk.DropDown()
        self.output_dropdown.set_hexpand(True)
        output_section.append(self.output_dropdown)
        
        # Output port selection (for choosing speakers vs headphones)
        port_section = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        port_section.set_margin_top(8)
        card.append(port_section)
        
        port_header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        port_icon = Gtk.Image.new_from_icon_name("audio-headphones-symbolic")
        port_icon.add_css_class('device-icon')
        port_header.append(port_icon)
        port_label = Gtk.Label(label="Output Port")
        port_label.add_css_class('subtitle-label')
        port_header.append(port_label)
        port_section.append(port_header)
        
        self.port_dropdown = Gtk.DropDown()
        self.port_dropdown.set_hexpand(True)
        port_section.append(self.port_dropdown)
        
        # Force Speakers checkbox - bypasses hardware jack sensing
        force_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        force_box.set_margin_top(16)
        card.append(force_box)
        
        self.force_speakers_check = Gtk.CheckButton(label="Force Speakers On (bypass headphone detection)")
        self.force_speakers_check.set_active(True)  # Default to on
        self.force_speakers_check.add_css_class('force-check')
        force_box.append(self.force_speakers_check)
        
        # Mute headphones checkbox
        self.mute_headphones_check = Gtk.CheckButton(label="Mute Headphones")
        self.mute_headphones_check.set_active(True)
        force_box.append(self.mute_headphones_check)
        
        # Warning/Info box about force speakers
        warning_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        warning_box.add_css_class('warning-box')
        warning_box.set_margin_top(8)
        
        warning_icon = Gtk.Image.new_from_icon_name("dialog-warning-symbolic")
        warning_box.append(warning_icon)
        
        warning_label = Gtk.Label(label="'Force Speakers On' uses ALSA to enable speakers when headphones are connected. Enable 'Mute Headphones' to prevent audio from both outputs.")
        warning_label.set_wrap(True)
        warning_label.set_xalign(0)
        warning_box.append(warning_label)
        
        card.append(warning_box)
        
        # Populate dropdowns
        self._populate_audio_dropdowns()
        
        # Connect signals
        self.input_dropdown.connect("notify::selected", self._on_input_device_selected)
        self.output_dropdown.connect("notify::selected", self._on_output_device_selected)
        
        return card
        
    def _populate_audio_dropdowns(self):
        """Populate the audio device dropdowns"""
        # Get sources and sinks
        sources = self.local_audio.get_available_sources()
        sinks = self.local_audio.get_available_sinks()
        
        # Populate input dropdown
        input_names = [s['description'] for s in sources]
        self.input_dropdown.set_model(Gtk.StringList.new(input_names))
        self._input_sources = sources
        
        # Populate input port dropdown for first source
        if sources:
            self._update_input_port_dropdown(sources[0])
        
        # Populate output dropdown
        output_names = [s['description'] for s in sinks]
        self.output_dropdown.set_model(Gtk.StringList.new(output_names))
        self._output_sinks = sinks
        
        # Populate output port dropdown for first sink
        if sinks:
            self._update_port_dropdown(sinks[0])
            
    def _update_input_port_dropdown(self, source: dict):
        """Update input port dropdown for selected source"""
        ports = source.get('ports', [])
        port_names = [p['description'] for p in ports]
        
        if port_names:
            self.input_port_dropdown.set_model(Gtk.StringList.new(port_names))
            self._current_input_ports = ports
            
            # Select active port
            active_port = source.get('active_port')
            if active_port:
                for i, port in enumerate(ports):
                    if port['name'] == active_port:
                        self.input_port_dropdown.set_selected(i)
                        break
        else:
            self.input_port_dropdown.set_model(Gtk.StringList.new(["Default"]))
            self._current_input_ports = []
            
    def _update_port_dropdown(self, sink: dict):
        """Update output port dropdown for selected sink"""
        ports = sink.get('ports', [])
        port_names = [p['description'] for p in ports]
        
        if port_names:
            self.port_dropdown.set_model(Gtk.StringList.new(port_names))
            self._current_ports = ports
            
            # Select active port
            active_port = sink.get('active_port')
            if active_port:
                for i, port in enumerate(ports):
                    if port['name'] == active_port:
                        self.port_dropdown.set_selected(i)
                        break
        else:
            self.port_dropdown.set_model(Gtk.StringList.new(["Default"]))
            self._current_ports = []
            
    def _on_input_device_selected(self, dropdown, _pspec):
        """Handle input device selection"""
        selected = dropdown.get_selected()
        if 0 <= selected < len(self._input_sources):
            source = self._input_sources[selected]
            self._update_input_port_dropdown(source)
            
    def _on_output_device_selected(self, dropdown, _pspec):
        """Handle output device selection"""
        selected = dropdown.get_selected()
        if 0 <= selected < len(self._output_sinks):
            sink = self._output_sinks[selected]
            self._update_port_dropdown(sink)
        
    def _create_qr_card(self) -> Gtk.Widget:
        """Create QR code display card"""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class('card')
        
        # Section header
        label = Gtk.Label(label="SCAN TO CONNECT")
        label.add_css_class('section-label')
        label.set_xalign(0)
        card.append(label)
        
        # QR Display
        self.qr_display = QRDisplay(port=self.server.port)
        card.append(self.qr_display)
        
        return card
        
    def _create_visualizer_card(self) -> Gtk.Widget:
        """Create audio visualizer card"""
        card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        card.add_css_class('card')
        
        # Section header
        label = Gtk.Label(label="AUDIO LEVEL")
        label.add_css_class('section-label')
        label.set_xalign(0)
        card.append(label)
        
        # Visualizer
        self.visualizer = AudioVisualizer()
        card.append(self.visualizer)
        
        return card
        
    def _create_main_button(self) -> Gtk.Widget:
        """Create the main control button"""
        button = Gtk.Button(label="▶ Start Audio")
        button.add_css_class('primary-button')
        button.set_margin_top(16)
        button.connect("clicked", self._on_main_button_clicked)
        return button
        
    # Event Handlers
    
    def _on_mode_changed(self, button, mode):
        """Handle mode toggle"""
        if not button.get_active():
            return
            
        self.current_mode = mode
        
        # Update toggle buttons
        if mode == 'local':
            self.local_mode_btn.set_active(True)
            self.android_mode_btn.set_active(False)
            self.local_mode_btn.remove_css_class('secondary-button')
            self.local_mode_btn.add_css_class('primary-button')
            self.android_mode_btn.remove_css_class('primary-button')
            self.android_mode_btn.add_css_class('secondary-button')
            
            # Show/hide cards
            self.local_audio_card.set_visible(True)
            self.qr_card.set_visible(False)
            
            self.status_detail.set_text("Local microphone → Speakers")
            
        else:  # android mode
            self.android_mode_btn.set_active(True)
            self.local_mode_btn.set_active(False)
            self.android_mode_btn.remove_css_class('secondary-button')
            self.android_mode_btn.add_css_class('primary-button')
            self.local_mode_btn.remove_css_class('primary-button')
            self.local_mode_btn.add_css_class('secondary-button')
            
            # Show/hide cards
            self.local_audio_card.set_visible(False)
            self.qr_card.set_visible(True)
            
            self.status_detail.set_text("Scan QR with Android app")
            
    def _on_main_button_clicked(self, button):
        """Handle main button click"""
        if self.current_mode == 'local':
            if self.local_audio.is_running:
                self._stop_local_audio()
            else:
                self._start_local_audio()
        else:  # android mode
            if self.server.is_running:
                self.server.stop()
            else:
                self.server.start()
                
    def _start_local_audio(self):
        """Start local microphone → speaker routing"""
        # Get selected input
        input_idx = self.input_dropdown.get_selected()
        if input_idx < 0 or input_idx >= len(self._input_sources):
            self._show_error("Please select an input device")
            return
            
        source = self._input_sources[input_idx]
        source_name = source['name']
        
        # Get selected output
        output_idx = self.output_dropdown.get_selected()
        if output_idx < 0 or output_idx >= len(self._output_sinks):
            self._show_error("Please select an output device")
            return
            
        sink = self._output_sinks[output_idx]
        sink_name = sink['name']
        
        # Set INPUT port if selected (for choosing between built-in mic and headphone mic)
        input_port_idx = self.input_port_dropdown.get_selected()
        if hasattr(self, '_current_input_ports') and self._current_input_ports:
            if 0 <= input_port_idx < len(self._current_input_ports):
                input_port = self._current_input_ports[input_port_idx]
                self.local_audio.set_source_port(source_name, input_port['name'])
                print(f"Set input port to: {input_port['description']}")
        
        # Set OUTPUT port if selected (for choosing between speakers and headphones)
        port_idx = self.port_dropdown.get_selected()
        if hasattr(self, '_current_ports') and self._current_ports:
            if 0 <= port_idx < len(self._current_ports):
                port = self._current_ports[port_idx]
                self.local_audio.set_sink_port(sink_name, port['name'])
                print(f"Set output port to: {port['description']}")
        
        # Force speakers on via ALSA if checkbox is checked
        if self.force_speakers_check.get_active():
            self.local_audio.force_speakers_on()
            
        # Mute headphones if checkbox is checked
        if self.mute_headphones_check.get_active():
            self.local_audio.mute_headphones()
                
        # Start loopback
        success = self.local_audio.start_loopback(
            source_name=source_name,
            sink_name=sink_name,
            force_speaker_port=False  # We handle this with the checkboxes now
        )
        
        if success:
            self.main_button.set_label("⏹ Stop Audio")
            self.main_button.remove_css_class('primary-button')
            self.main_button.add_css_class('danger-button')
            self.status_label.set_text("Audio Active")
            self.status_detail.set_text(f"{source['description']} → Speakers")
            self._update_status_dot('connected')
            
            # Show a simulated audio level (since loopback doesn't give us levels directly)
            self._start_simulated_visualizer()
        else:
            self._show_error("Failed to start audio routing")
            
    def _stop_local_audio(self):
        """Stop local audio routing"""
        self.local_audio.stop_loopback()
        self.main_button.set_label("▶ Start Audio")
        self.main_button.remove_css_class('danger-button')
        self.main_button.add_css_class('primary-button')
        self.status_label.set_text("Ready")
        self.status_detail.set_text("Select input and output, then start")
        self._update_status_dot('disconnected')
        self.visualizer.reset()
        self._stop_simulated_visualizer()
        
    def _start_simulated_visualizer(self):
        """Start a simulated visualizer (since loopback doesn't provide level callbacks)"""
        import random
        
        def update_level():
            if self.local_audio.is_running:
                # Simulate audio activity with random levels
                level = random.uniform(0.2, 0.7)
                self.visualizer.set_level(level)
                return True
            return False
            
        self._visualizer_timer = GLib.timeout_add(100, update_level)
        
    def _stop_simulated_visualizer(self):
        """Stop the simulated visualizer"""
        if hasattr(self, '_visualizer_timer'):
            GLib.source_remove(self._visualizer_timer)
            self._visualizer_timer = None
            
    def _on_refresh_clicked(self, button):
        """Handle refresh button click"""
        self._populate_audio_dropdowns()
        if self.current_mode == 'android':
            self.qr_display.regenerate()
        
    # Local Audio Callbacks
    
    def _on_local_audio_state_change(self, state: LocalAudioState):
        """Handle local audio state change"""
        GLib.idle_add(self._update_local_audio_state, state)
        
    def _update_local_audio_state(self, state: LocalAudioState):
        """Update UI for local audio state"""
        if state == LocalAudioState.RUNNING:
            self._update_status_dot('connected')
        elif state == LocalAudioState.STOPPED:
            self._update_status_dot('disconnected')
        elif state == LocalAudioState.ERROR:
            self._update_status_dot('disconnected')
            
    def _on_local_audio_error(self, error: str):
        """Handle local audio error"""
        GLib.idle_add(self._show_error, error)
        
    # Server Callbacks (for Android mode)
    
    def _on_server_state_change(self, state: ServerState):
        """Handle server state change"""
        GLib.idle_add(self._update_server_state, state)
        
    def _update_server_state(self, state: ServerState):
        """Update UI for server state (main thread)"""
        if self.current_mode != 'android':
            return
            
        if state == ServerState.RUNNING:
            self.main_button.set_label("⏹ Stop Server")
            self.main_button.remove_css_class('primary-button')
            self.main_button.add_css_class('danger-button')
            self.status_label.set_text("Waiting for Connection")
            self.status_detail.set_text("Scan QR code with Android app")
            self._update_status_dot('waiting')
        elif state == ServerState.STOPPED:
            self.main_button.set_label("▶ Start Server")
            self.main_button.remove_css_class('danger-button')
            self.main_button.add_css_class('primary-button')
            self.status_label.set_text("Server Stopped")
            self.status_detail.set_text("Start server for Android audio")
            self._update_status_dot('disconnected')
            self.visualizer.reset()
        elif state == ServerState.STARTING:
            self.main_button.set_label("Starting...")
            self.main_button.set_sensitive(False)
        elif state == ServerState.STOPPING:
            self.main_button.set_label("Stopping...")
            self.main_button.set_sensitive(False)
            
        if state in (ServerState.RUNNING, ServerState.STOPPED):
            self.main_button.set_sensitive(True)
            
    def _on_client_connect(self, client: ClientInfo):
        """Handle client connection"""
        GLib.idle_add(self._update_client_connected, client)
        
    def _update_client_connected(self, client: ClientInfo):
        """Update UI for client connection (main thread)"""
        ip = client.address[0]
        self.status_label.set_text("Connected")
        self.status_detail.set_text(f"Receiving audio from {ip}")
        self._update_status_dot('connected')
        
    def _on_client_disconnect(self, client: ClientInfo):
        """Handle client disconnection"""
        GLib.idle_add(self._update_client_disconnected)
        
    def _update_client_disconnected(self):
        """Update UI for client disconnection (main thread)"""
        if self.server.is_running:
            self.status_label.set_text("Waiting for Connection")
            self.status_detail.set_text("Client disconnected")
            self._update_status_dot('waiting')
            self.visualizer.reset()
            
    def _on_audio_level(self, level: float):
        """Handle audio level update"""
        GLib.idle_add(self.visualizer.set_level, level)
        
    def _on_server_error(self, error: str):
        """Handle server error"""
        GLib.idle_add(self._show_error, error)
        
    def _show_error(self, error: str):
        """Show error dialog (main thread)"""
        dialog = Adw.MessageDialog(
            transient_for=self,
            heading="Error",
            body=error
        )
        dialog.add_response("ok", "OK")
        dialog.present()
        
    def _update_status_dot(self, state: str):
        """Update status indicator"""
        self.status_dot.remove_css_class('connected')
        self.status_dot.remove_css_class('disconnected')
        self.status_dot.remove_css_class('waiting')
        self.status_dot.add_css_class(state)
        
    def cleanup(self):
        """Clean up resources"""
        self._stop_simulated_visualizer()
        self.local_audio.cleanup()
        self.server.stop()
        self.audio_manager.cleanup()
        self.visualizer.cleanup()
