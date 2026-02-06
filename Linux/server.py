"""
Audio Streaming Server
Handles UDP audio packet reception and playback with low-latency optimizations
"""

import socket
import threading
import queue
import struct
import numpy as np
from typing import Callable, Optional
from dataclasses import dataclass
from enum import Enum
import time
from scipy import signal

# Import sounddevice for audio playback
try:
    import sounddevice as sd
    SD_AVAILABLE = True
except ImportError:
    SD_AVAILABLE = False
    print("Warning: sounddevice not available, audio playback disabled")


class ServerState(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"


@dataclass
class ClientInfo:
    """Information about a connected client"""
    address: tuple
    last_seen: float
    packet_count: int = 0


class AudioServer:
    """
    UDP Audio Streaming Server
    Receives raw PCM audio from Android client and outputs to speakers
    """
    
    DEFAULT_PORT = 5555
    SAMPLE_RATE = 48000
    CHANNELS = 1
    FRAME_SIZE = 960
    BUFFER_SIZE = 2048
    
    # Volume boost
    VOLUME_GAIN = 4.0
    
    def __init__(self, port: int = DEFAULT_PORT):
        self.port = port
        self.state = ServerState.STOPPED
        self._socket: Optional[socket.socket] = None
        self._receive_thread: Optional[threading.Thread] = None
        self._playback_thread: Optional[threading.Thread] = None
        self._audio_queue: queue.Queue = queue.Queue(maxsize=6)
        self._running = False
        
        # Callbacks
        self._on_state_change: Optional[Callable[[ServerState], None]] = None
        self._on_client_connect: Optional[Callable[[ClientInfo], None]] = None
        self._on_client_disconnect: Optional[Callable[[ClientInfo], None]] = None
        self._on_audio_level: Optional[Callable[[float], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        
        self._current_client: Optional[ClientInfo] = None
        self._output_stream = None
        self._last_seq_num = -1
        
        # Low-pass filter coefficients (cut off high-frequency noise)
        # Butterworth filter, order 2, cutoff at 8kHz (most voice is below this)
        nyquist = self.SAMPLE_RATE / 2
        cutoff = 10000  # 10kHz cutoff - keeps voice clear, removes hiss
        self._filter_b, self._filter_a = signal.butter(2, cutoff / nyquist, btype='low')
        self._filter_zi = None  # Filter state for continuous filtering
            
    def set_callbacks(
        self,
        on_state_change: Optional[Callable[[ServerState], None]] = None,
        on_client_connect: Optional[Callable[[ClientInfo], None]] = None,
        on_client_disconnect: Optional[Callable[[ClientInfo], None]] = None,
        on_audio_level: Optional[Callable[[float], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ):
        self._on_state_change = on_state_change
        self._on_client_connect = on_client_connect
        self._on_client_disconnect = on_client_disconnect
        self._on_audio_level = on_audio_level
        self._on_error = on_error
        
    def _set_state(self, state: ServerState):
        self.state = state
        if self._on_state_change:
            self._on_state_change(state)
            
    def start(self) -> bool:
        if self.state != ServerState.STOPPED:
            return False
            
        self._set_state(ServerState.STARTING)
        self._last_seq_num = -1
        self._filter_zi = signal.lfilter_zi(self._filter_b, self._filter_a)  # Reset filter state
        
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)
            self._socket.bind(('0.0.0.0', self.port))
            self._socket.settimeout(0.5)
            
            self._running = True
            
            self._receive_thread = threading.Thread(
                target=self._receive_loop,
                daemon=True,
                name="AudioReceiver"
            )
            self._receive_thread.start()
            
            self._playback_thread = threading.Thread(
                target=self._playback_loop,
                daemon=True,
                name="AudioPlayback"
            )
            self._playback_thread.start()
            
            self._set_state(ServerState.RUNNING)
            print(f"Audio server started on port {self.port}")
            return True
            
        except Exception as e:
            self._set_state(ServerState.STOPPED)
            if self._on_error:
                self._on_error(f"Failed to start server: {e}")
            return False
            
    def stop(self):
        if self.state not in (ServerState.RUNNING, ServerState.STARTING):
            return
            
        print("Stopping audio server...")
        self._set_state(ServerState.STOPPING)
        self._running = False
        
        try:
            self._audio_queue.put_nowait(None)
        except:
            pass
        
        time.sleep(0.1)
        
        if self._socket:
            try:
                self._socket.close()
            except:
                pass
            self._socket = None
        
        if self._receive_thread and self._receive_thread.is_alive():
            self._receive_thread.join(timeout=0.5)
            
        if self._playback_thread and self._playback_thread.is_alive():
            self._playback_thread.join(timeout=0.5)
            
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except:
                pass
                
        self._current_client = None
        self._set_state(ServerState.STOPPED)
        print("Audio server stopped")
        
    def _receive_loop(self):
        while self._running:
            try:
                if not self._socket:
                    break
                    
                data, addr = self._socket.recvfrom(self.BUFFER_SIZE)
                
                if len(data) < 4:
                    continue
                    
                seq_num = struct.unpack('>I', data[:4])[0]
                audio_data = data[4:]
                
                # Skip duplicates
                if seq_num <= self._last_seq_num and self._last_seq_num - seq_num < 1000:
                    continue
                self._last_seq_num = seq_num
                
                current_time = time.time()
                if self._current_client is None or self._current_client.address != addr:
                    old_client = self._current_client
                    if old_client and self._on_client_disconnect:
                        self._on_client_disconnect(old_client)
                        
                    self._current_client = ClientInfo(
                        address=addr,
                        last_seen=current_time,
                        packet_count=1
                    )
                    print(f"Client connected from {addr}")
                    if self._on_client_connect:
                        self._on_client_connect(self._current_client)
                else:
                    self._current_client.last_seen = current_time
                    self._current_client.packet_count += 1
                    
                if len(audio_data) > 0:
                    while self._audio_queue.qsize() >= 4:
                        try:
                            self._audio_queue.get_nowait()
                        except:
                            break
                    try:
                        self._audio_queue.put_nowait(audio_data)
                    except queue.Full:
                        pass
                    
            except socket.timeout:
                if self._current_client:
                    if time.time() - self._current_client.last_seen > 3.0:
                        if self._on_client_disconnect:
                            self._on_client_disconnect(self._current_client)
                        self._current_client = None
                continue
            except OSError:
                break
            except Exception as e:
                if self._running:
                    print(f"Receive error: {e}")
                    
    def _playback_loop(self):
        if not SD_AVAILABLE:
            if self._on_error:
                self._on_error("sounddevice not available")
            return
            
        stream = None
        filter_zi = self._filter_zi.copy() if self._filter_zi is not None else None
        
        try:
            print(f"Initializing audio output...")
            
            stream = sd.OutputStream(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                dtype='float32',
                blocksize=1024,
                latency='high',
            )
            stream.start()
            print(f"Audio playback: {self.SAMPLE_RATE}Hz, vol: {self.VOLUME_GAIN}x, filter: 10kHz LP")
            
            level_counter = 0
            
            while self._running:
                try:
                    audio_data = self._audio_queue.get(timeout=0.05)
                    
                    if audio_data is None:
                        break
                    
                    # Convert to float32
                    audio_int16 = np.frombuffer(audio_data, dtype='<i2')
                    audio_float = audio_int16.astype(np.float32) / 32768.0
                    
                    # Apply low-pass filter to remove high-frequency noise
                    if filter_zi is not None:
                        audio_float, filter_zi = signal.lfilter(
                            self._filter_b, self._filter_a, 
                            audio_float, zi=filter_zi
                        )
                    else:
                        audio_float = signal.lfilter(self._filter_b, self._filter_a, audio_float)
                    
                    # Apply volume boost
                    audio_float = audio_float * self.VOLUME_GAIN
                    audio_float = np.clip(audio_float, -1.0, 1.0)
                    audio_float = audio_float.reshape(-1, 1).astype(np.float32)
                        
                    # Audio level
                    level_counter += 1
                    if self._on_audio_level and level_counter >= 2:
                        level_counter = 0
                        rms = np.sqrt(np.mean(audio_float ** 2))
                        self._on_audio_level(min(1.0, rms * 2))
                        
                    if stream and stream.active and self._running:
                        stream.write(audio_float)
                        
                except queue.Empty:
                    if self._on_audio_level:
                        self._on_audio_level(0.0)
                    continue
                except Exception as e:
                    if self._running:
                        print(f"Playback error: {e}")
                    
        except Exception as e:
            print(f"Playback init error: {e}")
        finally:
            if stream:
                try:
                    stream.stop()
                except:
                    pass
                try:
                    stream.close()
                except:
                    pass
            print("Audio playback stopped")
                
    @property
    def is_running(self) -> bool:
        return self.state == ServerState.RUNNING
        
    @property
    def client_connected(self) -> bool:
        return self._current_client is not None
        
    def get_client_info(self) -> Optional[ClientInfo]:
        return self._current_client
