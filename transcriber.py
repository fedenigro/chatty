import io
import tempfile
import os

import whisper

AVAILABLE_MODELS = ["tiny", "base", "small", "medium", "large"]


class Transcriber:
    def __init__(self, model_name: str = "base"):
        self._model_name = model_name
        self._model = None

    def load(self) -> None:
        self._model = whisper.load_model(self._model_name)

    def reload(self, model_name: str) -> None:
        self._model_name = model_name
        self._model = whisper.load_model(model_name)

    def transcribe(self, audio_buf: io.BytesIO, language: str | None = None) -> str:
        if self._model is None:
            raise RuntimeError("Model not loaded. Call load() first.")

        # whisper.load_audio requires a file path, so write to a temp file
        audio_buf.seek(0)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            tmp.write(audio_buf.read())
            tmp_path = tmp.name

        try:
            result = self._model.transcribe(
                tmp_path,
                language=language,
                fp16=False,  # fp16 not supported on CPU-only Macs
            )
        finally:
            os.unlink(tmp_path)

        return result["text"].strip()
