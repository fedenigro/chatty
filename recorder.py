import io
import threading
import wave

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Whisper expects 16 kHz
CHANNELS = 1


class Recorder:
    def __init__(self):
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None
        self.is_recording = False
        self.current_level: float = 0.0  # live RMS, 0.0–1.0

    def start(self) -> None:
        with self._lock:
            if self.is_recording:
                return
            self._frames = []
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                dtype="int16",
                callback=self._callback,
            )
            self._stream.start()
            self.is_recording = True

    def stop(self) -> io.BytesIO | None:
        with self._lock:
            if not self.is_recording:
                return None
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self.is_recording = False
            frames = self._frames[:]

        if not frames:
            return None

        audio = np.concatenate(frames, axis=0)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(CHANNELS)
            wf.setsampwidth(2)  # int16 = 2 bytes
            wf.setframerate(SAMPLE_RATE)
            wf.writeframes(audio.tobytes())
        buf.seek(0)
        return buf

    def _callback(self, indata: np.ndarray, frames, time, status) -> None:
        self._frames.append(indata.copy())
        # Update live level: RMS normalised to ~0–1 for typical speech
        rms = float(np.sqrt(np.mean(indata.astype(np.float32) ** 2)))
        self.current_level = min(1.0, rms / 4000.0)
