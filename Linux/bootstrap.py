#!/usr/bin/env python3
"""
PulseLink Bootstrap Launcher
- Checks for required dependencies
- Creates a venv and installs deps if needed
- Launches the main application
"""
import os
import sys
import subprocess
import json
from pathlib import Path

# Configuration
APP_NAME = "pulselink"
CONFIG_DIR = Path.home() / ".config" / APP_NAME
VENV_DIR = CONFIG_DIR / "venv"
CONFIG_FILE = CONFIG_DIR / "config.json"

REQUIRED_PACKAGES = [
    "pulsectl",
    "sounddevice", 
    "numpy",
    "scipy",
    "qrcode",
    "Pillow",
    "netifaces",
]

# Get the app directory (where this script is located)
if getattr(sys, 'frozen', False):
    APP_DIR = Path(sys.executable).parent
else:
    APP_DIR = Path(__file__).parent.resolve()


def check_system_gtk():
    """Check if system GTK4 and libadwaita are available."""
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Gtk, Adw
        return True
    except Exception as e:
        return False


def check_deps_in_venv():
    """Check if all deps are installed in our venv."""
    # First check if config file exists with installed flag
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                config = json.load(f)
                if config.get("installed") == True:
                    # Verify venv still exists
                    python_path = VENV_DIR / "bin" / "python3"
                    if python_path.exists():
                        return True
        except Exception:
            pass
    
    # Fallback: check if venv and packages exist
    if not VENV_DIR.exists():
        return False
    
    python_path = VENV_DIR / "bin" / "python3"
    if not python_path.exists():
        return False
    
    # Quick check - just verify a few key packages exist
    # Using import check is slow, so only do minimal validation
    site_packages = VENV_DIR / "lib"
    if not site_packages.exists():
        return False
    
    return True


def show_gtk_dialog(title, message, show_cancel=True):
    """Show a GTK dialog and return True if OK was clicked."""
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Gtk, Adw, GLib, Gio
        
        result = [None]
        app = None
        
        class DialogApp(Adw.Application):
            def __init__(self):
                super().__init__(
                    application_id="dev.uzair.pulselink.setup",
                    flags=Gio.ApplicationFlags.FLAGS_NONE
                )
            
            def do_activate(self):
                # Create a hidden window as parent
                win = Adw.ApplicationWindow(application=self)
                win.set_default_size(1, 1)
                win.set_decorated(False)
                
                # Create the dialog
                dialog = Adw.MessageDialog(
                    transient_for=win,
                    heading=title,
                    body=message,
                )
                
                if show_cancel:
                    dialog.add_response("cancel", "Cancel")
                    dialog.add_response("install", "Install")
                    dialog.set_response_appearance("install", Adw.ResponseAppearance.SUGGESTED)
                    dialog.set_default_response("install")
                    dialog.set_close_response("cancel")
                else:
                    dialog.add_response("ok", "OK")
                    dialog.set_default_response("ok")
                    dialog.set_close_response("ok")
                
                def on_response(dialog, response):
                    if show_cancel:
                        result[0] = response == "install"
                    else:
                        result[0] = True
                    win.close()
                    self.quit()
                
                dialog.connect("response", on_response)
                
                # Show window briefly then show dialog
                win.present()
                dialog.present()
        
        app = DialogApp()
        app.run([])
        
        return result[0] if result[0] is not None else False
        
    except Exception as e:
        print(f"Dialog error: {e}")
        # Fallback to terminal prompt
        print(f"\n{title}")
        print(f"{message}")
        if show_cancel:
            response = input("\nProceed with installation? [y/N]: ").strip().lower()
            return response in ('y', 'yes')
        else:
            input("\nPress Enter to continue...")
            return True


def create_venv_and_install():
    """Create a virtual environment and install dependencies with GTK progress dialog."""
    import subprocess
    import threading
    
    try:
        import gi
        gi.require_version('Gtk', '4.0')
        gi.require_version('Adw', '1')
        from gi.repository import Gtk, Adw, GLib, Gio
        
        result = [False]
        error_msg = [None]
        
        class ProgressApp(Adw.Application):
            def __init__(self):
                super().__init__(
                    application_id="dev.uzair.pulselink.installer",
                    flags=Gio.ApplicationFlags.FLAGS_NONE
                )
                self.win = None
                self.status_label = None
                self.spinner = None
            
            def do_activate(self):
                # Create progress window
                self.win = Adw.ApplicationWindow(application=self)
                self.win.set_title("Installing Dependencies")
                self.win.set_default_size(400, 200)
                self.win.set_resizable(False)
                
                # Main box
                main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=20)
                main_box.set_margin_top(30)
                main_box.set_margin_bottom(30)
                main_box.set_margin_start(30)
                main_box.set_margin_end(30)
                
                # Title
                title = Gtk.Label(label="Installing PulseLink Dependencies")
                title.add_css_class("title-2")
                main_box.append(title)
                
                # Spinner
                self.spinner = Gtk.Spinner()
                self.spinner.set_size_request(48, 48)
                self.spinner.start()
                main_box.append(self.spinner)
                
                # Status label
                self.status_label = Gtk.Label(label="Preparing installation...")
                self.status_label.add_css_class("dim-label")
                main_box.append(self.status_label)
                
                # Info label
                info = Gtk.Label(label="This may take a few minutes. Please wait...")
                info.add_css_class("dim-label")
                main_box.append(info)
                
                self.win.set_content(main_box)
                self.win.present()
                
                # Start installation in background thread
                thread = threading.Thread(target=self.install_deps)
                thread.daemon = True
                thread.start()
            
            def update_status(self, text):
                GLib.idle_add(lambda: self.status_label.set_text(text) if self.status_label else None)
            
            def install_deps(self):
                try:
                    # Ensure config directory exists
                    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
                    
                    # Remove old venv if exists
                    if VENV_DIR.exists():
                        import shutil
                        self.update_status("Removing old environment...")
                        shutil.rmtree(VENV_DIR)
                    
                    # Create venv
                    self.update_status("Creating virtual environment...")
                    proc = subprocess.run(
                        [sys.executable, "-m", "venv", str(VENV_DIR), "--system-site-packages"],
                        capture_output=True,
                        text=True
                    )
                    
                    if proc.returncode != 0:
                        error_msg[0] = f"Failed to create venv: {proc.stderr}"
                        GLib.idle_add(self.finish_with_error)
                        return
                    
                    pip_path = VENV_DIR / "bin" / "pip"
                    
                    # Upgrade pip
                    self.update_status("Upgrading pip...")
                    subprocess.run([str(pip_path), "install", "--upgrade", "pip"], 
                                   capture_output=True)
                    
                    # Install packages one by one for better progress
                    for i, pkg in enumerate(REQUIRED_PACKAGES):
                        self.update_status(f"Installing {pkg}... ({i+1}/{len(REQUIRED_PACKAGES)})")
                        proc = subprocess.run(
                            [str(pip_path), "install", pkg],
                            capture_output=True,
                            text=True
                        )
                        if proc.returncode != 0:
                            error_msg[0] = f"Failed to install {pkg}: {proc.stderr}"
                            GLib.idle_add(self.finish_with_error)
                            return
                    
                    # Save config
                    self.update_status("Saving configuration...")
                    config = {
                        "venv_path": str(VENV_DIR),
                        "version": "1.0.0",
                        "installed": True,
                    }
                    with open(CONFIG_FILE, "w") as f:
                        json.dump(config, f, indent=2)
                    
                    result[0] = True
                    GLib.idle_add(self.finish_success)
                    
                except Exception as e:
                    error_msg[0] = str(e)
                    GLib.idle_add(self.finish_with_error)
            
            def finish_success(self):
                self.update_status("Installation complete!")
                self.spinner.stop()
                GLib.timeout_add(1000, self.quit)
            
            def finish_with_error(self):
                self.update_status(f"Error: {error_msg[0]}")
                self.spinner.stop()
                GLib.timeout_add(3000, self.quit)
        
        app = ProgressApp()
        app.run([])
        
        return result[0]
        
    except Exception as e:
        print(f"Progress dialog error: {e}")
        # Fallback to terminal-based installation
        return create_venv_and_install_terminal()


def create_venv_and_install_terminal():
    """Fallback terminal-based installation."""
    import subprocess
    
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "="*50)
    print("Installing Dependencies")
    print("This may take a few minutes...")
    print("="*50 + "\n")
    
    if VENV_DIR.exists():
        import shutil
        shutil.rmtree(VENV_DIR)
    
    print("Creating virtual environment...")
    result = subprocess.run(
        [sys.executable, "-m", "venv", str(VENV_DIR), "--system-site-packages"],
        capture_output=True,
        text=True
    )
    
    if result.returncode != 0:
        print(f"Error: {result.stderr}")
        return False
    
    pip_path = VENV_DIR / "bin" / "pip"
    
    print("Upgrading pip...")
    subprocess.run([str(pip_path), "install", "--upgrade", "pip"], capture_output=True)
    
    for pkg in REQUIRED_PACKAGES:
        print(f"Installing {pkg}...")
        result = subprocess.run([str(pip_path), "install", pkg], capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error installing {pkg}: {result.stderr}")
            return False
    
    config = {"venv_path": str(VENV_DIR), "version": "1.0.0", "installed": True}
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=2)
    
    print("\nInstallation complete!")
    return True


def run_with_venv():
    """Run the main application using the venv Python."""
    python_path = VENV_DIR / "bin" / "python3"
    main_script = APP_DIR / "main.py"
    
    # Add app directory to PYTHONPATH
    env = os.environ.copy()
    env["PYTHONPATH"] = str(APP_DIR) + ":" + env.get("PYTHONPATH", "")
    
    # Execute main.py with venv python
    os.execve(str(python_path), [str(python_path), str(main_script)] + sys.argv[1:], env)


def run_directly():
    """Run directly with current Python (all deps available)."""
    main_script = APP_DIR / "main.py"
    
    # Add app directory to PYTHONPATH
    sys.path.insert(0, str(APP_DIR))
    
    # Import and run
    exec(open(main_script).read())


def main():
    """Main entry point."""
    
    # First, check if system GTK is available
    if not check_system_gtk():
        show_gtk_dialog(
            "Missing GTK4",
            "PulseLink requires GTK4 and libadwaita.\n\n"
            "Please install them:\n"
            "sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1",
            show_cancel=False
        )
        print("\nError: GTK4 and libadwaita are required.")
        print("Install with: sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adw-1")
        sys.exit(1)
    
    # Check if deps are in venv
    if check_deps_in_venv():
        # All good, run with venv
        run_with_venv()
        return
    
    # Deps not installed, ask user
    proceed = show_gtk_dialog(
        "First-time Setup Required",
        "PulseLink needs to install some Python packages.\n\n"
        "This will create a local environment in:\n"
        f"{CONFIG_DIR}\n\n"
        "Packages to install:\n"
        f"{', '.join(REQUIRED_PACKAGES)}\n\n"
        "This only needs to be done once.",
        show_cancel=True
    )
    
    if not proceed:
        print("Installation cancelled.")
        sys.exit(0)
    
    # Install dependencies
    if create_venv_and_install():
        print("\nSetup complete! Launching PulseLink...")
        run_with_venv()
    else:
        show_gtk_dialog(
            "Installation Failed",
            "Failed to install dependencies.\n\n"
            "Please try running manually:\n"
            f"cd {APP_DIR}\n"
            "pip install pulsectl sounddevice numpy scipy qrcode Pillow netifaces",
            show_cancel=False
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
