"""
Local Audio Capture and Playback
Handles capturing audio from local microphone and playing to specific output device
Uses PipeWire/PulseAudio for routing
"""

import threading
import subprocess
import time
from typing import Optional, Callable, List, Dict
from dataclasses import dataclass
from enum import Enum

try:
    import pulsectl
    PULSE_AVAILABLE = True
except ImportError:
    PULSE_AVAILABLE = False


class LocalAudioState(Enum):
    STOPPED = "stopped"
    RUNNING = "running"
    ERROR = "error"


@dataclass 
class AudioRoute:
    """Represents an audio routing configuration"""
    input_device: str  # Source device name
    output_device: str  # Sink device name
    

class LocalAudioCapture:
    """
    Captures audio from local microphone and routes to specified output
    Can force output to specific device (e.g., laptop speakers instead of headphones)
    """
    
    def __init__(self):
        self._pulse: Optional[pulsectl.Pulse] = None
        self._state = LocalAudioState.STOPPED
        self._loopback_module_id: Optional[int] = None
        self._lock = threading.Lock()
        
        # Callbacks
        self._on_state_change: Optional[Callable[[LocalAudioState], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._on_audio_level: Optional[Callable[[float], None]] = None
        
        # Current route
        self._current_route: Optional[AudioRoute] = None
        
        self._initialize()
        
    def _initialize(self):
        """Initialize PulseAudio connection"""
        if not PULSE_AVAILABLE:
            return
            
        try:
            self._pulse = pulsectl.Pulse('pulselink-local-capture')
        except Exception as e:
            print(f"Failed to connect to PulseAudio: {e}")
            
    def set_callbacks(
        self,
        on_state_change: Optional[Callable[[LocalAudioState], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_audio_level: Optional[Callable[[float], None]] = None
    ):
        """Set callback functions"""
        self._on_state_change = on_state_change
        self._on_error = on_error
        self._on_audio_level = on_audio_level
        
    def _set_state(self, state: LocalAudioState):
        """Update state and notify"""
        self._state = state
        if self._on_state_change:
            self._on_state_change(state)
            
    def _run_pactl(self, *args) -> tuple:
        """Run a pactl command and return (success, output)"""
        try:
            result = subprocess.run(
                ['pactl'] + list(args),
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)
            
    def _run_amixer(self, *args) -> tuple:
        """Run an amixer command and return (success, output)"""
        try:
            result = subprocess.run(
                ['amixer', '-c', '0'] + list(args),
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as e:
            return False, str(e)
            
    def force_speakers_on(self) -> bool:
        """
        Force speakers to be on even when headphones are connected.
        Uses ALSA amixer to directly control the Speaker channel,
        bypassing PulseAudio/PipeWire port availability.
        
        Steps:
        1. Disable Auto-Mute Mode (most important - must be done first!)
        2. Unmute and set volume on Speaker channel
        3. Unmute Master channel
        """
        print("=" * 50)
        print("FORCING SPEAKERS ON VIA ALSA")
        print("=" * 50)
        
        # 1. FIRST: Disable Auto-Mute Mode - this is critical!
        # When Auto-Mute is enabled, the speaker channel is automatically muted when headphones are detected
        success_am, output_am = self._run_amixer('set', 'Auto-Mute Mode', 'Disabled')
        if success_am:
            print("✓ Auto-Mute Mode: DISABLED")
        else:
            print(f"✗ Auto-Mute Mode: Failed to disable - {output_am}")
            
        # 2. Unmute and set volume on Speaker channel
        success_spk, output_spk = self._run_amixer('set', 'Speaker', '100%', 'on')
        if success_spk:
            print("✓ Speaker: 100%, unmuted")
        else:
            print(f"✗ Speaker: Failed - {output_spk}")
            
        # 3. Unmute Master channel
        success_mas, output_mas = self._run_amixer('set', 'Master', '100%', 'on')
        if success_mas:
            print("✓ Master: 100%, unmuted")
        else:
            print(f"✗ Master: Failed - {output_mas}")
            
        print("=" * 50)
        
        return success_spk and success_mas
        
    def mute_headphones(self) -> bool:
        """Mute headphone channel so only speakers play"""
        success, output = self._run_amixer('set', 'Headphone', '0%', 'off')
        if success:
            print("✓ Headphones: muted")
        else:
            print(f"✗ Headphones mute failed: {output}")
        return success
            
    def set_sink_port(self, sink_name: str, port_name: str) -> bool:
        """
        Set a specific port on a sink using pactl command
        This is the reliable way to switch between speakers and headphones
        """
        success, output = self._run_pactl('set-sink-port', sink_name, port_name)
        if success:
            print(f"Set sink {sink_name} to port {port_name}")
        else:
            print(f"Failed to set port: {output}")
            if self._on_error:
                self._on_error(f"Failed to set port: {output}")
        return success
        
    def set_source_port(self, source_name: str, port_name: str) -> bool:
        """
        Set a specific port on a source using pactl command
        """
        success, output = self._run_pactl('set-source-port', source_name, port_name)
        if success:
            print(f"Set source {source_name} to port {port_name}")
        else:
            print(f"Failed to set source port: {output}")
        return success
            
    def get_builtin_speaker(self) -> Optional[str]:
        """
        Find the built-in speaker device
        This is useful when headphones are plugged in but we want to use laptop speakers
        """
        if not self._pulse:
            return None
            
        try:
            for sink in self._pulse.sink_list():
                # Look for built-in analog speaker
                name_lower = sink.name.lower()
                desc_lower = sink.description.lower()
                
                # Common patterns for built-in speakers
                if any(pattern in name_lower or pattern in desc_lower for pattern in [
                    'built-in', 'internal', 'analog-stereo', 'alsa_output.pci'
                ]):
                    # Check if it has a speaker port
                    for port in (sink.port_list or []):
                        port_name = port.name.lower()
                        if 'speaker' in port_name:
                            return sink.name
                            
                    # If no specific speaker port, but it's the internal audio
                    if 'pci' in name_lower and 'hdmi' not in name_lower:
                        return sink.name
                        
        except Exception as e:
            print(f"Error finding built-in speaker: {e}")
            
        return None
        
    def force_output_to_speakers(self, sink_name: str) -> bool:
        """
        Force audio output to specific speakers even if headphones are connected
        Uses pactl for port switching
        """
        if not self._pulse:
            return False
            
        try:
            for sink in self._pulse.sink_list():
                if sink.name == sink_name:
                    # Find speaker port
                    for port in (sink.port_list or []):
                        if 'speaker' in port.name.lower():
                            return self.set_sink_port(sink_name, port.name)
                            
                    # If no speaker port found, just set as default
                    self._pulse.sink_default_set(sink.name)
                    return True
                        
        except Exception as e:
            if self._on_error:
                self._on_error(f"Failed to switch output: {e}")
                
        return False
        
    def start_loopback(self, source_name: str, sink_name: str, 
                       force_speaker_port: bool = True) -> bool:
        """
        Start audio loopback from source (mic) to sink (speakers)
        
        Args:
            source_name: PulseAudio source name (microphone)
            sink_name: PulseAudio sink name (speakers)
            force_speaker_port: If True, force output to speaker port even if headphones connected
        """
        if not self._pulse:
            if self._on_error:
                self._on_error("PulseAudio not available")
            return False
            
        if self._state == LocalAudioState.RUNNING:
            self.stop_loopback()
            
        try:
            with self._lock:
                # Force speaker port if requested
                if force_speaker_port:
                    self._force_sink_to_speaker_port(sink_name)
                
                # Load module-loopback to route audio using pactl
                # This creates a real-time audio path from source to sink
                module_args = f"source={source_name} sink={sink_name} latency_msec=30"
                
                success, output = self._run_pactl(
                    'load-module', 'module-loopback', 
                    f'source={source_name}', 
                    f'sink={sink_name}',
                    'latency_msec=30'
                )
                
                if success and output:
                    self._loopback_module_id = int(output)
                elif self._pulse:
                    # Fallback to pulsectl
                    self._loopback_module_id = self._pulse.module_load(
                        'module-loopback',
                        module_args
                    )
                else:
                    raise Exception("Failed to load loopback module")
                
                self._current_route = AudioRoute(
                    input_device=source_name,
                    output_device=sink_name
                )
                
                self._set_state(LocalAudioState.RUNNING)
                print(f"Started loopback: {source_name} -> {sink_name} (module id: {self._loopback_module_id})")
                return True
                
        except Exception as e:
            self._set_state(LocalAudioState.ERROR)
            if self._on_error:
                self._on_error(f"Failed to start loopback: {e}")
            return False
            
    def _force_sink_to_speaker_port(self, sink_name: str):
        """Force a sink to use its speaker port instead of headphone port"""
        try:
            for sink in self._pulse.sink_list():
                if sink.name == sink_name:
                    for port in (sink.port_list or []):
                        port_lower = port.name.lower()
                        # Look for speaker port, avoid headphone/headset
                        if 'speaker' in port_lower and 'headphone' not in port_lower:
                            self.set_sink_port(sink_name, port.name)
                            return
        except Exception as e:
            print(f"Could not force speaker port: {e}")
            
    def stop_loopback(self):
        """Stop the audio loopback"""
        if self._loopback_module_id is None:
            return
            
        try:
            with self._lock:
                # Try pactl first
                success, _ = self._run_pactl('unload-module', str(self._loopback_module_id))
                if not success and self._pulse:
                    # Fallback to pulsectl
                    self._pulse.module_unload(self._loopback_module_id)
                    
                print(f"Stopped loopback module {self._loopback_module_id}")
                    
        except Exception as e:
            print(f"Error stopping loopback: {e}")
        finally:
            self._loopback_module_id = None
            self._current_route = None
            self._set_state(LocalAudioState.STOPPED)
            
    def get_available_sources(self) -> List[Dict]:
        """Get list of available input sources (microphones)"""
        if not self._pulse:
            return []
            
        sources = []
        try:
            for source in self._pulse.source_list():
                # Skip monitor sources
                if '.monitor' not in source.name:
                    sources.append({
                        'name': source.name,
                        'description': source.description,
                        'ports': [{'name': p.name, 'description': p.description} 
                                  for p in (source.port_list or [])],
                        'active_port': source.port_active.name if source.port_active else None
                    })
        except Exception as e:
            print(f"Error listing sources: {e}")
            
        return sources
        
    def get_available_sinks(self) -> List[Dict]:
        """Get list of available output sinks (speakers)"""
        if not self._pulse:
            return []
            
        sinks = []
        try:
            for sink in self._pulse.sink_list():
                sinks.append({
                    'name': sink.name,
                    'description': sink.description,
                    'ports': [{'name': p.name, 'description': p.description} 
                              for p in (sink.port_list or [])],
                    'active_port': sink.port_active.name if sink.port_active else None
                })
        except Exception as e:
            print(f"Error listing sinks: {e}")
            
        return sinks
            
    @property
    def state(self) -> LocalAudioState:
        return self._state
        
    @property
    def is_running(self) -> bool:
        return self._state == LocalAudioState.RUNNING
        
    @property
    def current_route(self) -> Optional[AudioRoute]:
        return self._current_route
        
    def cleanup(self):
        """Clean up resources"""
        self.stop_loopback()
        with self._lock:
            if self._pulse:
                try:
                    self._pulse.close()
                except:
                    pass
                self._pulse = None
