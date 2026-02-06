#!/usr/bin/env python3
"""
PulseLink - Audio Streaming Server
Main entry point for the GTK4 application
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw, Gio, GLib, Gdk
import sys
import os

# Add the current directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ui.main_window import MainWindow


class PulseLinkApp(Adw.Application):
    """Main application class for PulseLink"""
    
    def __init__(self):
        super().__init__(
            application_id='dev.uzair.pulselink',
            flags=Gio.ApplicationFlags.FLAGS_NONE
        )
        self.window = None
        
    def do_startup(self):
        Adw.Application.do_startup(self)
        
    def do_activate(self):
        if not self.window:
            self.window = MainWindow(application=self)
            self._load_css()
        self.window.present()
        
    def _load_css(self):
        """Load custom CSS styles"""
        css_provider = Gtk.CssProvider()
        css_path = os.path.join(os.path.dirname(__file__), 'style.css')
        
        try:
            css_provider.load_from_path(css_path)
            display = Gdk.Display.get_default()
            if display:
                Gtk.StyleContext.add_provider_for_display(
                    display,
                    css_provider,
                    Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
                )
        except Exception as e:
            print(f"Warning: Could not load CSS: {e}")
            
    def do_shutdown(self):
        """Clean shutdown"""
        if self.window and hasattr(self.window, 'cleanup'):
            self.window.cleanup()
        Adw.Application.do_shutdown(self)


def main():
    """Application entry point"""
    app = PulseLinkApp()
    return app.run(sys.argv)


if __name__ == '__main__':
    sys.exit(main())
