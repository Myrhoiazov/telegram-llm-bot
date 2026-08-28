"""Voice-message pre-processing before text enters BotService."""
from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path

from app.stt.lemonade import TranscriptionError


class VoiceProcessingError(Exception):
    """Raised when voice input cannot be converted or transcribed."""


class EmptyTranscriptionError(VoiceProcessingError):
    """Raised when transcription succeeds but contains no usable text."""


ConvertAudio = Callable[[Path, Path], None]


def convert_ogg_to_wav(input_path: Path, output_path: Path, timeout_seconds: int = 30) -> None:
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, timeout=timeout_seconds)
    except (subprocess.SubprocessError, OSError) as exc:
        raise VoiceProcessingError("audio conversion failed") from exc


class VoiceProcessor:
    def __init__(
        self,
        transcriber,
        convert: ConvertAudio = convert_ogg_to_wav,
        temp_dir: Path | None = None,
    ) -> None:
        self._transcriber = transcriber
        self._convert = convert
        self._temp_dir = temp_dir

    def process(self, audio_bytes: bytes) -> str:
        input_path: Path | None = None
        output_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".ogg", dir=self._temp_dir, delete=False
            ) as source_file:
                source_file.write(audio_bytes)
                input_path = Path(source_file.name)

            with tempfile.NamedTemporaryFile(
                suffix=".wav", dir=self._temp_dir, delete=False
            ) as wav_file:
                output_path = Path(wav_file.name)

            self._convert(input_path, output_path)
            text = self._transcriber.transcribe(output_path).strip()
            if not text:
                raise EmptyTranscriptionError("empty transcription")
            return text
        except EmptyTranscriptionError:
            raise
        except (TranscriptionError, VoiceProcessingError) as exc:
            raise VoiceProcessingError(str(exc)) from exc
        finally:
            for path in (input_path, output_path):
                if path is not None:
                    path.unlink(missing_ok=True)
