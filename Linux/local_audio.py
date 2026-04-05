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
    input_device: str
    output_device: str


class LocalAudioCapture:

    def __init__(self):
        self._pulse: Optional[pulsectl.Pulse] = None
        self._state = LocalAudioState.STOPPED
        self._lock = threading.Lock()
        self._pw_loopback_process: Optional[subprocess.Popen] = None

        self._on_state_change: Optional[
            Callable[[LocalAudioState], None]
        ] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._on_audio_level: Optional[
            Callable[[float], None]
        ] = None

        self._current_route: Optional[AudioRoute] = None

        if PULSE_AVAILABLE:
            try:
                self._pulse = pulsectl.Pulse(
                    'pulselink-local-capture'
                )
            except Exception:
                pass

    def set_callbacks(
        self,
        on_state_change: Optional[
            Callable[[LocalAudioState], None]
        ] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_audio_level: Optional[
            Callable[[float], None]
        ] = None
    ):
        self._on_state_change = on_state_change
        self._on_error = on_error
        self._on_audio_level = on_audio_level

    def _set_state(self, state: LocalAudioState):
        self._state = state
        if self._on_state_change:
            self._on_state_change(state)

    def _run_cmd(
        self, args: list
    ) -> tuple[bool, str]:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0, result.stdout.strip()
        except Exception as exc:
            return False, str(exc)

    def unmute_capture(self, source_name: str) -> bool:
        self._run_cmd(
            ['amixer', '-c', '0', 'set', 'Capture', '100%', 'on']
        )
        self._run_cmd(
            ['pactl', 'set-source-mute', source_name, '0']
        )
        self._run_cmd(
            ['pactl', 'set-source-volume', source_name, '100%']
        )
        return True

    def set_sink_port(
        self, sink_name: str, port_name: str
    ) -> bool:
        success, _ = self._run_cmd(
            ['pactl', 'set-sink-port', sink_name, port_name]
        )
        return success

    def set_source_port(
        self, source_name: str, port_name: str
    ) -> bool:
        success, _ = self._run_cmd(
            ['pactl', 'set-source-port', source_name, port_name]
        )
        return success

    def start_loopback(
        self,
        source_name: str,
        sink_name: str
    ) -> bool:
        if self._state == LocalAudioState.RUNNING:
            self.stop_loopback()

        try:
            with self._lock:
                self.unmute_capture(source_name)

                self._pw_loopback_process = subprocess.Popen(
                    [
                        'pw-loopback',
                        '-C', source_name,
                        '-P', sink_name,
                        '-l', '30',
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )

                time.sleep(0.5)

                if self._pw_loopback_process.poll() is not None:
                    stderr_output = (
                        self._pw_loopback_process.stderr.read()
                    )
                    raise RuntimeError(
                        f"pw-loopback exited: {stderr_output}"
                    )

                self._current_route = AudioRoute(
                    input_device=source_name,
                    output_device=sink_name
                )

                self._set_state(LocalAudioState.RUNNING)
                return True

        except Exception as exc:
            self._set_state(LocalAudioState.ERROR)
            if self._on_error:
                self._on_error(
                    f"Failed to start loopback: {exc}"
                )
            return False

    def stop_loopback(self):
        try:
            with self._lock:
                if self._pw_loopback_process:
                    self._pw_loopback_process.terminate()
                    try:
                        self._pw_loopback_process.wait(
                            timeout=3
                        )
                    except subprocess.TimeoutExpired:
                        self._pw_loopback_process.kill()
                        self._pw_loopback_process.wait(
                            timeout=1
                        )
                    self._pw_loopback_process = None

                self._stop_speaker_watchdog()
        except Exception:
            pass
        finally:
            self._current_route = None
            self._set_state(LocalAudioState.STOPPED)

    def get_available_sources(self) -> List[Dict]:
        if not self._pulse:
            return []

        sources = []
        try:
            for source in self._pulse.source_list():
                if '.monitor' in source.name:
                    continue
                sources.append({
                    'name': source.name,
                    'description': source.description,
                    'ports': [
                        {
                            'name': p.name,
                            'description': p.description
                        }
                        for p in (source.port_list or [])
                    ],
                    'active_port': (
                        source.port_active.name
                        if source.port_active else None
                    )
                })
        except Exception:
            pass

        return sources

    def get_available_sinks(self) -> List[Dict]:
        if not self._pulse:
            return []

        sinks = []
        try:
            for sink in self._pulse.sink_list():
                sinks.append({
                    'name': sink.name,
                    'description': sink.description,
                    'ports': [
                        {
                            'name': p.name,
                            'description': p.description
                        }
                        for p in (sink.port_list or [])
                    ],
                    'active_port': (
                        sink.port_active.name
                        if sink.port_active else None
                    )
                })
        except Exception:
            pass

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
        self.stop_loopback()
        with self._lock:
            if self._pulse:
                try:
                    self._pulse.close()
                except Exception:
                    pass
                self._pulse = None
