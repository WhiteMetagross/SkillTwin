from dataclasses import dataclass
import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
from typing import List, Optional

from .errors import AudioInspectionError, RuntimeConfigurationError


@dataclass(frozen=True)
class AudioInspectionResult:
    hasAudioTrack: bool
    hasUsableSpeech: bool
    detectedLanguage: Optional[str] = None
    inspectedDurationMs: int = 0


class AudioDetector:
    """Inspects the complete decoded audio stream without buffering it all in memory."""

    SAMPLE_RATE = 16000
    CHUNK_SAMPLES = 1600
    READ_BYTES = CHUNK_SAMPLES * 2 * 10
    MAX_INSPECTION_SECONDS = 181

    def __init__(
        self,
        ffmpegPath: Optional[str] = None,
        ffprobePath: Optional[str] = None,
    ) -> None:
        self.ffmpegPath = ffmpegPath or shutil.which("ffmpeg")
        self.ffprobePath = ffprobePath or shutil.which("ffprobe")

    def validateDependencies(self) -> None:
        missing = []
        if not self.ffmpegPath or not Path(self.ffmpegPath).is_file():
            missing.append("ffmpeg")
        if not self.ffprobePath or not Path(self.ffprobePath).is_file():
            missing.append("ffprobe")
        if missing:
            raise RuntimeConfigurationError(
                "Required media binaries are unavailable: " + ", ".join(missing)
            )

    def inspectAudio(self, localFilePath: Path) -> AudioInspectionResult:
        if not localFilePath.is_file():
            raise FileNotFoundError(f"Media file not found for audio inspection: {localFilePath}")
        self.validateDependencies()

        command = [
            str(self.ffprobePath), "-v", "error", "-select_streams", "a",
            "-show_entries", "stream=codec_type", "-of", "json", str(localFilePath),
        ]
        try:
            probe = subprocess.run(
                command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=False, timeout=30,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise AudioInspectionError(f"ffprobe failed for {localFilePath}: {exc}") from exc
        if probe.returncode != 0:
            detail = probe.stderr.strip()[:500]
            raise AudioInspectionError(f"ffprobe could not inspect audio: {detail or 'unknown error'}")
        try:
            streams = json.loads(probe.stdout or "{}").get("streams", [])
        except (json.JSONDecodeError, AttributeError) as exc:
            raise AudioInspectionError("ffprobe returned malformed audio metadata") from exc
        if not any(stream.get("codec_type") == "audio" for stream in streams):
            return AudioInspectionResult(False, False, inspectedDurationMs=0)

        hasSpeech, inspectedDurationMs = self._analyzeAcousticSpeech(localFilePath)
        return AudioInspectionResult(
            hasAudioTrack=True,
            hasUsableSpeech=hasSpeech,
            inspectedDurationMs=inspectedDurationMs,
        )

    def _analyzeAcousticSpeech(self, localFilePath: Path) -> tuple[bool, int]:
        decodeCommand = [
            str(self.ffmpegPath), "-nostdin", "-v", "error", "-i", str(localFilePath),
            "-map", "0:a:0", "-f", "s16le", "-ac", "1", "-ar", str(self.SAMPLE_RATE), "-",
        ]
        try:
            process = subprocess.Popen(
                decodeCommand,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except OSError as exc:
            raise AudioInspectionError(f"ffmpeg could not start: {exc}") from exc

        if process.stdout is None or process.stderr is None:
            process.kill()
            raise AudioInspectionError("ffmpeg did not expose audio output streams")

        chunkRms: List[float] = []
        chunkZcr: List[float] = []
        totalSamples = 0
        totalSquare = 0
        carry = b""
        try:
            while True:
                block = process.stdout.read(self.READ_BYTES)
                if not block:
                    break
                if totalSamples * 2 + len(carry) + len(block) > (
                    self.MAX_INSPECTION_SECONDS * self.SAMPLE_RATE * 2
                ):
                    raise AudioInspectionError("Decoded audio exceeds the bounded inspection duration")
                carry += block
                usableBytes = (len(carry) // (self.CHUNK_SAMPLES * 2)) * (self.CHUNK_SAMPLES * 2)
                for offset in range(0, usableBytes, self.CHUNK_SAMPLES * 2):
                    rawChunk = carry[offset : offset + self.CHUNK_SAMPLES * 2]
                    samples = struct.unpack(f"<{self.CHUNK_SAMPLES}h", rawChunk)
                    squareSum = sum(sample * sample for sample in samples)
                    rms = math.sqrt(squareSum / self.CHUNK_SAMPLES)
                    crossings = sum(
                        1 for index in range(1, len(samples))
                        if (samples[index] >= 0 > samples[index - 1])
                        or (samples[index] < 0 <= samples[index - 1])
                    )
                    chunkRms.append(rms)
                    chunkZcr.append(crossings / self.CHUNK_SAMPLES)
                    totalSquare += squareSum
                    totalSamples += self.CHUNK_SAMPLES
                carry = carry[usableBytes:]
            stderr = process.stderr.read(4096).decode("utf-8", errors="replace")
            returnCode = process.wait(timeout=30)
        except Exception as exc:
            process.kill()
            process.wait()
            if isinstance(exc, AudioInspectionError):
                raise
            raise AudioInspectionError(f"Failed while decoding complete audio stream: {exc}") from exc
        finally:
            process.stdout.close()
            process.stderr.close()

        if returnCode != 0:
            raise AudioInspectionError(f"ffmpeg audio decode failed: {stderr.strip()[:500]}")
        inspectedDurationMs = int((totalSamples / self.SAMPLE_RATE) * 1000)
        if totalSamples < self.CHUNK_SAMPLES or not chunkRms:
            return False, inspectedDurationMs

        overallRms = math.sqrt(totalSquare / totalSamples)
        if overallRms < 100.0:
            return False, inspectedDurationMs

        # Evaluate active chunks so speech late in a mostly silent clip is not diluted.
        active = [
            (rms, chunkZcr[index])
            for index, rms in enumerate(chunkRms)
            if rms >= 300.0
        ]
        if len(active) < 3:
            return False, inspectedDurationMs
        activeRms = [item[0] for item in active]
        activeZcr = [item[1] for item in active]
        meanRms = sum(activeRms) / len(activeRms)
        varianceRms = sum((value - meanRms) ** 2 for value in activeRms) / len(activeRms)
        meanZcr = sum(activeZcr) / len(activeZcr)
        varianceZcr = sum((value - meanZcr) ** 2 for value in activeZcr) / len(activeZcr)

        relativeEnergyVariance = varianceRms / (meanRms ** 2 + 1e-6)
        stationaryTone = varianceZcr < 0.001 or relativeEnergyVariance < 0.02
        speech = not stationaryTone and varianceZcr >= 0.002 and varianceRms > 10000.0
        return speech, inspectedDurationMs
