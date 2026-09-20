import json
import math
from pathlib import Path
import shutil
import struct
import subprocess
from typing import Optional

class AudioInspectionResult:
    def __init__(
        self,
        hasAudioTrack: bool,
        hasUsableSpeech: bool,
        detectedLanguage: Optional[str] = None
    ) -> None:
        self.hasAudioTrack = hasAudioTrack
        self.hasUsableSpeech = hasUsableSpeech
        self.detectedLanguage = detectedLanguage

class AudioDetector:
    """
    Inspects actual video audio streams and distinguishes speech from silence or non speech tones.
    Analyzes decoded audio signals rather than relying on file names.
    An audio track alone is not proof of narration.
    """

    def __init__(
        self,
        ffmpegPath: Optional[str] = None,
        ffprobePath: Optional[str] = None
    ) -> None:
        self.ffmpegPath = ffmpegPath or shutil.which("ffmpeg")
        self.ffprobePath = ffprobePath or shutil.which("ffprobe")

    def inspectAudio(self, localFilePath: Path) -> AudioInspectionResult:
        if not localFilePath.is_file():
            return AudioInspectionResult(hasAudioTrack=False, hasUsableSpeech=False)

        # Check if audio stream exists via ffprobe or container inspection
        hasAudioStream = False
        if self.ffprobePath:
            try:
                cmd = [
                    self.ffprobePath,
                    "-v", "error",
                    "-show_entries", "stream=codec_type",
                    "-of", "json",
                    str(localFilePath)
                ]
                proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
                if proc.returncode == 0 and proc.stdout:
                    info = json.loads(proc.stdout)
                    for stream in info.get("streams", []):
                        if stream.get("codec_type") == "audio":
                            hasAudioStream = True
                            break
            except Exception:
                hasAudioStream = False

        if not hasAudioStream and self.ffmpegPath:
            # Fallback probe with ffmpeg decode test
            try:
                testCmd = [
                    self.ffmpegPath,
                    "-v", "error",
                    "-i", str(localFilePath),
                    "-f", "s16le",
                    "-ac", "1",
                    "-ar", "16000",
                    "-t", "0.5",
                    "-"
                ]
                proc = subprocess.run(testCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
                if proc.returncode == 0 and len(proc.stdout) > 0:
                    hasAudioStream = True
            except Exception:
                hasAudioStream = False

        if not hasAudioStream:
            return AudioInspectionResult(hasAudioTrack=False, hasUsableSpeech=False)

        # Inspect decoded PCM stream for acoustic speech characteristics
        hasSpeech = self._analyzeAcousticSpeech(localFilePath)
        return AudioInspectionResult(
            hasAudioTrack=True,
            hasUsableSpeech=hasSpeech,
            detectedLanguage="enIN" if hasSpeech else None
        )

    def _analyzeAcousticSpeech(self, localFilePath: Path) -> bool:
        if not self.ffmpegPath:
            return False

        try:
            # Decode the complete clip. Video validation caps input duration at 180 seconds,
            # so full-clip inspection remains bounded while still detecting delayed speech.
            decodeCmd = [
                self.ffmpegPath,
                "-v", "error",
                "-i", str(localFilePath),
                "-f", "s16le",
                "-ac", "1",
                "-ar", "16000",
                "-"
            ]
            proc = subprocess.run(decodeCmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            rawPcm = proc.stdout
            if not rawPcm or len(rawPcm) < 3200:
                return False

            sampleCount = len(rawPcm) // 2
            samples = struct.unpack(f"<{sampleCount}h", rawPcm)

            # Overall root mean square amplitude
            overallRms = math.sqrt(sum(s * s for s in samples) / len(samples))
            if overallRms < 100.0:
                # Signal is essentially silence or low noise floor
                return False

            # Inspect 100 millisecond chunks (1600 samples per chunk at 16kHz)
            chunkSize = 1600
            chunks = [
                samples[i : i + chunkSize]
                for i in range(0, len(samples), chunkSize)
                if len(samples[i : i + chunkSize]) == chunkSize
            ]
            if not chunks:
                return False

            # Chunk energy and variance across chunks
            chunkRms = [math.sqrt(sum(s * s for s in c) / len(c)) for c in chunks]
            meanChunkRms = sum(chunkRms) / len(chunkRms)
            varRms = sum((r - meanChunkRms) ** 2 for r in chunkRms) / len(chunkRms)

            # Zero crossing rate per chunk
            zcrs = []
            for c in chunks:
                crossings = sum(
                    1
                    for j in range(1, len(c))
                    if (c[j] >= 0 and c[j - 1] < 0) or (c[j] < 0 and c[j - 1] >= 0)
                )
                zcrs.append(crossings / len(c))

            meanZcr = sum(zcrs) / len(zcrs)
            varZcr = sum((z - meanZcr) ** 2 for z in zcrs) / len(zcrs)

            # Pure stationary tones have near zero ZCR variance and flat amplitude envelope
            isStationaryTone = varZcr < 0.001 or (varRms / (meanChunkRms ** 2 + 1e-6)) < 0.02

            # Speech exhibits syllabic energy variance and zero crossing shifts between voiced and unvoiced
            isSpeech = not isStationaryTone and varZcr >= 0.002 and varRms > 10000.0

            return isSpeech
        except Exception:
            return False
