import io
import math
from pathlib import Path
import struct

import pytest

from mediaIntelligence.audioDetector import AudioDetector
from mediaIntelligence.errors import RuntimeConfigurationError


class FakeProcess:
    def __init__(self, pcm: bytes, returnCode: int = 0) -> None:
        self.stdout = io.BytesIO(pcm)
        self.stderr = io.BytesIO(b"" if returnCode == 0 else b"decode failed")
        self.returnCode = returnCode

    def wait(self, timeout: int | None = None) -> int:
        return self.returnCode

    def kill(self) -> None:
        self.returnCode = -9


def pcmChunk(frequency: float, amplitude: int, phase: float = 0.0) -> bytes:
    samples = [
        int(amplitude * math.sin(2 * math.pi * frequency * index / 16000 + phase))
        for index in range(1600)
    ]
    return struct.pack("<1600h", *samples)


def analyze(monkeypatch: pytest.MonkeyPatch, pcm: bytes) -> tuple[bool, int]:
    monkeypatch.setattr("subprocess.Popen", lambda *_args, **_kwargs: FakeProcess(pcm))
    detector = AudioDetector(ffmpegPath="ffmpeg", ffprobePath="ffprobe")
    return detector._analyzeAcousticSpeech(Path("video.mp4"))


def testSilentAudioIsNotSpeech(monkeypatch: pytest.MonkeyPatch) -> None:
    speech, duration = analyze(monkeypatch, b"\x00\x00" * 1600 * 20)
    assert speech is False
    assert duration == 2000


def testStationaryToneOnlyAudioIsNotSpeech(monkeypatch: pytest.MonkeyPatch) -> None:
    tone = pcmChunk(440, 12000) * 20
    speech, duration = analyze(monkeypatch, tone)
    assert speech is False
    assert duration == 2000


@pytest.mark.parametrize("language", ["English", "Hindi"])
def testNormalNarratedAcousticsDetectedRegardlessOfLanguage(
    monkeypatch: pytest.MonkeyPatch, language: str,
) -> None:
    del language
    speechLike = b"".join(
        pcmChunk(180 if index % 2 == 0 else 900, 6000 if index % 3 else 18000, index / 7)
        for index in range(30)
    )
    speech, duration = analyze(monkeypatch, speechLike)
    assert speech is True
    assert duration == 3000


def testSpeechBeginningAfterThirtySecondsIsInspected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    silence = b"\x00\x00" * 1600 * 310
    lateSpeech = b"".join(
        pcmChunk(170 if index % 2 == 0 else 1000, 8000 if index % 3 else 20000, index / 5)
        for index in range(30)
    )
    speech, duration = analyze(monkeypatch, silence + lateSpeech)
    assert duration == 34000
    assert speech is True


def testMissingFfmpegAndFfprobeFailInsteadOfReportingSilence(tmp_path: Path) -> None:
    detector = AudioDetector(
        ffmpegPath=str(tmp_path / "missing-ffmpeg"),
        ffprobePath=str(tmp_path / "missing-ffprobe"),
    )
    with pytest.raises(RuntimeConfigurationError, match="ffmpeg.*ffprobe"):
        detector.validateDependencies()
