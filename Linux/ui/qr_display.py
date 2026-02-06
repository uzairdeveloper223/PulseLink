"""
QR Code Display Widget
Generates and displays a QR code with server connection info
"""

import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GdkPixbuf, GLib

import io
import json
import socket
from typing import Optional

try:
    import qrcode
    from PIL import Image
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False
    print("Warning: qrcode/PIL not available")

try:
    import netifaces
    NETIFACES_AVAILABLE = True
except ImportError:
    NETIFACES_AVAILABLE = False


class QRDisplay(Gtk.Box):
    """Widget that displays a QR code for mobile connection"""
    
    def __init__(self, port: int = 5555):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        
        self.port = port
        self._setup_ui()
        
    def _setup_ui(self):
        """Build the UI"""
        # Container with white background for QR
        self.qr_frame = Gtk.Frame()
        self.qr_frame.add_css_class('qr-container')
        
        # QR Image
        self.qr_image = Gtk.Picture()
        self.qr_image.set_size_request(200, 200)
        self.qr_image.set_can_shrink(True)
        self.qr_image.set_keep_aspect_ratio(True)
        
        self.qr_frame.set_child(self.qr_image)
        self.append(self.qr_frame)
        
        # IP Address label
        self.ip_label = Gtk.Label()
        self.ip_label.add_css_class('subtitle-label')
        self.ip_label.set_selectable(True)
        self.append(self.ip_label)
        
        # Instructions
        instructions = Gtk.Label(label="Scan with PulseLink Android app")
        instructions.add_css_class('subtitle-label')
        self.append(instructions)
        
        # Generate initial QR
        self.regenerate()
        
    def get_local_ip(self) -> str:
        """Get the local IP address"""
        if NETIFACES_AVAILABLE:
            try:
                # Try to find a non-loopback interface
                for iface in netifaces.interfaces():
                    addrs = netifaces.ifaddresses(iface)
                    if netifaces.AF_INET in addrs:
                        for addr in addrs[netifaces.AF_INET]:
                            ip = addr.get('addr', '')
                            if ip and not ip.startswith('127.'):
                                return ip
            except:
                pass
                
        # Fallback method
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
            
    def regenerate(self):
        """Regenerate the QR code with current network info"""
        ip = self.get_local_ip()
        self.ip_label.set_text(f"{ip}:{self.port}")
        
        if not QR_AVAILABLE:
            self._show_placeholder(ip)
            return
            
        # Connection data
        data = json.dumps({
            "ip": ip,
            "port": self.port,
            "protocol": "udp",
            "app": "pulselink"
        })
        
        try:
            # Generate QR code
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_M,
                box_size=10,
                border=2
            )
            qr.add_data(data)
            qr.make(fit=True)
            
            # Create PIL image
            img = qr.make_image(fill_color="black", back_color="white")
            
            # Convert to GdkPixbuf
            buffer = io.BytesIO()
            img.save(buffer, format='PNG')
            buffer.seek(0)
            
            loader = GdkPixbuf.PixbufLoader.new_with_type('png')
            loader.write(buffer.read())
            loader.close()
            pixbuf = loader.get_pixbuf()
            
            # Scale to fit
            scaled = pixbuf.scale_simple(200, 200, GdkPixbuf.InterpType.NEAREST)
            
            # Set image
            texture = Gdk.Texture.new_for_pixbuf(scaled)
            self.qr_image.set_paintable(texture)
            
        except Exception as e:
            print(f"QR generation error: {e}")
            self._show_placeholder(ip)
            
    def _show_placeholder(self, ip: str):
        """Show placeholder when QR generation fails"""
        # Create a simple placeholder
        placeholder = Gtk.Label(label=f"📱\n\nConnect to:\n{ip}:{self.port}")
        placeholder.set_justify(Gtk.Justification.CENTER)
        self.qr_frame.set_child(placeholder)
        
    def set_port(self, port: int):
        """Update the port and regenerate QR"""
        self.port = port
        self.regenerate()


# Import Gdk for texture creation
from gi.repository import Gdk
