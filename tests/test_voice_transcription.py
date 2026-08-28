from pathlib import Path

import pytest

from app.application.voice import EmptyTranscriptionError, VoiceProcessingError, VoiceProcessor
from app.stt.lemonade import LemonadeTranscriber, TranscriptionError


class FakeResponse:
    def __init__(self, payload=None, ok=True, status_code=200):
        self._payload = payload if payload is not None else {"text": "привет"}
        self.ok = ok
        self.status_code = status_code

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, response):
        self.response = response
        self.post_calls = []

    def post(self, url, files=None, data=None, timeout=None):
        self.post_calls.append({"url": url, "files": files, "data": data, "timeout": timeout})
        return self.response


def test_lemonade_transcriber_posts_wav_with_model(tmp_path):
    wav_path = tmp_path / "speech.wav"
    wav_path.write_bytes(b"wav-bytes")
    session = FakeSession(FakeResponse(payload={"text": "  привет  "}))
    transcriber = LemonadeTranscriber(
        base_url="http://localhost:13305/",
        model="Whisper-Base",
        timeout_seconds=60,
        session=session,
    )

    text = transcriber.transcribe(wav_path)

    assert text == "привет"
    assert session.post_calls[0]["url"] == "http://localhost:13305/v1/audio/transcriptions"
    assert session.post_calls[0]["data"] == {"model": "Whisper-Base"}
    assert session.post_calls[0]["timeout"] == 60


def test_lemonade_transcriber_returns_empty_text_for_processor_to_classify(tmp_path):
    wav_path = tmp_path / "speech.wav"
    wav_path.write_bytes(b"wav-bytes")
    transcriber = LemonadeTranscriber(
        base_url="http://localhost:13305",
        model="Whisper-Base",
        timeout_seconds=60,
        session=FakeSession(FakeResponse(payload={"text": "  "})),
    )

    assert transcriber.transcribe(wav_path) == ""


def test_voice_processor_converts_downloaded_bytes_and_removes_temp_files(tmp_path):
    created_paths = []

    def convert(input_path: Path, output_path: Path) -> None:
        created_paths.extend([input_path, output_path])
        assert input_path.read_bytes() == b"ogg-bytes"
        output_path.write_bytes(b"wav-bytes")

    class FakeTranscriber:
        def __init__(self):
            self.paths = []

        def transcribe(self, wav_path):
            self.paths.append(wav_path)
            assert wav_path.read_bytes() == b"wav-bytes"
            return "распознанный текст"

    transcriber = FakeTranscriber()
    processor = VoiceProcessor(transcriber=transcriber, convert=convert, temp_dir=tmp_path)

    text = processor.process(b"ogg-bytes")

    assert text == "распознанный текст"
    assert transcriber.paths == [created_paths[1]]
    assert all(not path.exists() for path in created_paths)


def test_voice_processor_removes_temp_files_when_transcription_fails(tmp_path):
    created_paths = []

    def convert(input_path: Path, output_path: Path) -> None:
        created_paths.extend([input_path, output_path])
        output_path.write_bytes(b"wav-bytes")

    class FailingTranscriber:
        def transcribe(self, wav_path):
            raise TranscriptionError("stt failed")

    processor = VoiceProcessor(transcriber=FailingTranscriber(), convert=convert, temp_dir=tmp_path)

    with pytest.raises(VoiceProcessingError):
        processor.process(b"ogg-bytes")

    assert all(not path.exists() for path in created_paths)


def test_voice_processor_raises_empty_transcription_error(tmp_path):
    def convert(input_path: Path, output_path: Path) -> None:
        output_path.write_bytes(b"wav-bytes")

    class EmptyTranscriber:
        def transcribe(self, wav_path):
            return " "

    processor = VoiceProcessor(transcriber=EmptyTranscriber(), convert=convert, temp_dir=tmp_path)

    with pytest.raises(EmptyTranscriptionError):
        processor.process(b"ogg-bytes")
