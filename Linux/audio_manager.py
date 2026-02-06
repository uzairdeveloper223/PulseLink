"""
Audio Device Manager
Handles enumeration and control of audio input/output devices via PipeWire/PulseAudio
"""

import threading
from typing import List, Optional, Callable, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

try:
    import pulsectl
    PULSE_AVAILABLE = True
except ImportError:
    PULSE_AVAILABLE = False
    print("Warning: pulsectl not available, device enumeration disabled")


class DeviceType(Enum):
    INPUT = "input"
    OUTPUT = "output"


@dataclass
class AudioDevice:
    """Represents an audio device"""
    name: str
    description: str
    device_type: DeviceType
    index: int
    is_default: bool = False
    volume: float = 1.0
    muted: bool = False
    ports: List[str] = field(default_factory=list)
    active_port: Optional[str] = None
    
    @property
    def display_name(self) -> str:
        """Get a user-friendly display name"""
        return self.description or self.name


class AudioManager:
    """
    Manages audio devices and routing through PipeWire/PulseAudio
    """
    
    # Virtual device representing the Android microphone (network input)
    ANDROID_MIC_NAME = "android_network"
    
    def __init__(self):
        self._pulse: Optional[pulsectl.Pulse] = None
        self._lock = threading.Lock()
        
        # Cached devices
        self._input_devices: List[AudioDevice] = []
        self._output_devices: List[AudioDevice] = []
        
        # Current selections
        self._current_input: Optional[AudioDevice] = None
        self._current_output: Optional[AudioDevice] = None
        
        # Callbacks
        self._on_devices_changed: Optional[Callable[[], None]] = None
        self._on_device_error: Optional[Callable[[str], None]] = None
        
        # Headphone detection
        self._headphone_warning: bool = False
        
        self._initialize()
        
    def _initialize(self):
        """Initialize connection to PulseAudio"""
        if not PULSE_AVAILABLE:
            return
            
        try:
            self._pulse = pulsectl.Pulse('pulselink-manager')
            self.refresh_devices()
        except Exception as e:
            if self._on_device_error:
                self._on_device_error(f"Failed to connect to PulseAudio: {e}")
                
    def set_callbacks(
        self,
        on_devices_changed: Optional[Callable[[], None]] = None,
        on_device_error: Optional[Callable[[str], None]] = None
    ):
        """Set callback functions"""
        self._on_devices_changed = on_devices_changed
        self._on_device_error = on_device_error
        
    def refresh_devices(self):
        """Refresh the list of available devices"""
        if not self._pulse:
            self._create_mock_devices()
            return
            
        with self._lock:
            try:
                # Get sources (inputs)
                self._input_devices = []
                default_source = self._pulse.server_info().default_source_name
                
                for source in self._pulse.source_list():
                    # Skip monitor sources
                    if '.monitor' in source.name:
                        continue
                        
                    device = AudioDevice(
                        name=source.name,
                        description=source.description,
                        device_type=DeviceType.INPUT,
                        index=source.index,
                        is_default=(source.name == default_source),
                        volume=source.volume.value_flat if source.volume else 1.0,
                        muted=bool(source.mute),
                        ports=[p.name for p in (source.port_list or [])],
                        active_port=source.port_active.name if source.port_active else None
                    )
                    self._input_devices.append(device)
                    
                # Add virtual Android device
                android_device = AudioDevice(
                    name=self.ANDROID_MIC_NAME,
                    description="Android Device (Network)",
                    device_type=DeviceType.INPUT,
                    index=-1,
                    is_default=False
                )
                self._input_devices.append(android_device)
                    
                # Get sinks (outputs)
                self._output_devices = []
                default_sink = self._pulse.server_info().default_sink_name
                
                for sink in self._pulse.sink_list():
                    device = AudioDevice(
                        name=sink.name,
                        description=sink.description,
                        device_type=DeviceType.OUTPUT,
                        index=sink.index,
                        is_default=(sink.name == default_sink),
                        volume=sink.volume.value_flat if sink.volume else 1.0,
                        muted=bool(sink.mute),
                        ports=[p.name for p in (sink.port_list or [])],
                        active_port=sink.port_active.name if sink.port_active else None
                    )
                    self._output_devices.append(device)
                    
                # Check for headphone routing conflicts
                self._check_headphone_conflict()
                
                # Set defaults if not set
                if self._current_input is None and self._input_devices:
                    default = next((d for d in self._input_devices if d.is_default), None)
                    self._current_input = default or self._input_devices[0]
                    
                if self._current_output is None and self._output_devices:
                    default = next((d for d in self._output_devices if d.is_default), None)
                    self._current_output = default or self._output_devices[0]
                    
            except Exception as e:
                if self._on_device_error:
                    self._on_device_error(f"Failed to enumerate devices: {e}")
                    
        if self._on_devices_changed:
            self._on_devices_changed()
            
    def _create_mock_devices(self):
        """Create mock devices when PulseAudio is not available"""
        self._input_devices = [
            AudioDevice(
                name="default_input",
                description="Built-in Microphone",
                device_type=DeviceType.INPUT,
                index=0,
                is_default=True
            ),
            AudioDevice(
                name=self.ANDROID_MIC_NAME,
                description="Android Device (Network)",
                device_type=DeviceType.INPUT,
                index=-1,
                is_default=False
            )
        ]
        
        self._output_devices = [
            AudioDevice(
                name="default_output",
                description="Built-in Speakers",
                device_type=DeviceType.OUTPUT,
                index=0,
                is_default=True
            )
        ]
        
        self._current_input = self._input_devices[0]
        self._current_output = self._output_devices[0]
        
        if self._on_devices_changed:
            self._on_devices_changed()
            
    def _check_headphone_conflict(self):
        """
        Check if headphones with mic are connected - this can cause routing issues
        where audio output goes to headphones instead of speakers
        """
        self._headphone_warning = False
        
        # Look for devices that have both headphone and headset ports
        for output in self._output_devices:
            if output.active_port:
                port_lower = output.active_port.lower()
                if 'headphone' in port_lower or 'headset' in port_lower:
                    # Check if there's also an input with headset port
                    for input_dev in self._input_devices:
                        if input_dev.active_port:
                            input_port = input_dev.active_port.lower()
                            if 'headset' in input_port:
                                self._headphone_warning = True
                                return
                                
    @property
    def has_headphone_conflict(self) -> bool:
        """Returns True if there's a potential headphone routing conflict"""
        return self._headphone_warning
        
    def get_input_devices(self) -> List[AudioDevice]:
        """Get list of input devices"""
        return self._input_devices.copy()
        
    def get_output_devices(self) -> List[AudioDevice]:
        """Get list of output devices"""
        return self._output_devices.copy()
        
    def get_current_input(self) -> Optional[AudioDevice]:
        """Get currently selected input device"""
        return self._current_input
        
    def get_current_output(self) -> Optional[AudioDevice]:
        """Get currently selected output device"""
        return self._current_output
        
    def set_input_device(self, device: AudioDevice) -> bool:
        """Set the active input device"""
        if device.name == self.ANDROID_MIC_NAME:
            # Virtual device - just track selection
            self._current_input = device
            return True
            
        if not self._pulse:
            self._current_input = device
            return True
            
        try:
            with self._lock:
                self._pulse.source_default_set(device.name)
                self._current_input = device
                return True
        except Exception as e:
            if self._on_device_error:
                self._on_device_error(f"Failed to set input device: {e}")
            return False
            
    def set_output_device(self, device: AudioDevice) -> bool:
        """Set the active output device"""
        if not self._pulse:
            self._current_output = device
            return True
            
        try:
            with self._lock:
                self._pulse.sink_default_set(device.name)
                self._current_output = device
                
                # Move all current streams to new sink
                for stream in self._pulse.sink_input_list():
                    self._pulse.sink_input_move(stream.index, device.index)
                    
                return True
        except Exception as e:
            if self._on_device_error:
                self._on_device_error(f"Failed to set output device: {e}")
            return False
            
    def set_output_volume(self, volume: float):
        """Set output volume (0.0 to 1.0)"""
        if not self._pulse or not self._current_output:
            return
            
        try:
            with self._lock:
                self._pulse.volume_set_all_chans(
                    self._pulse.sink_list()[self._current_output.index],
                    volume
                )
        except Exception as e:
            if self._on_device_error:
                self._on_device_error(f"Failed to set volume: {e}")
                
    def is_android_input_selected(self) -> bool:
        """Check if Android network input is selected"""
        return (self._current_input is not None and 
                self._current_input.name == self.ANDROID_MIC_NAME)
                
    def cleanup(self):
        """Clean up resources"""
        with self._lock:
            if self._pulse:
                try:
                    self._pulse.close()
                except:
                    pass
                self._pulse = None
