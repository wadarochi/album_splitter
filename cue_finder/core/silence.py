import numpy as np
import soundfile

from cue_finder.core.slicer import Slicer


class SilenceDetector:
    """Silence-based track boundary detection using the slicer2 RMS algorithm.

    Wraps the existing Slicer class from audio-slicer with a timestamp-oriented API.
    Input: audio file path + detection parameters
    Output: list of boundary timestamps in seconds
    """

    def __init__(
        self,
        threshold: float = -40.0,
        min_length: int = 5000,
        min_interval: int = 300,
        hop_size: int = 10,
        max_sil_kept: int = 500,
    ):
        if not min_length >= min_interval >= hop_size:
            raise ValueError(
                "The following condition must be satisfied: "
                "min_length >= min_interval >= hop_size"
            )
        if not max_sil_kept >= hop_size:
            raise ValueError(
                "The following condition must be satisfied: "
                "max_sil_kept >= hop_size"
            )
        self.threshold = threshold
        self.min_length = min_length
        self.min_interval = min_interval
        self.hop_size = hop_size
        self.max_sil_kept = max_sil_kept

    def detect_boundaries(self, audio_path: str) -> list[float]:
        """Detect track boundary timestamps from an audio file.

        Returns a list of boundary timestamps in seconds. Each boundary
        represents the start of a silence region that separates two tracks.
        The first track is implicitly assumed to start at 0.0 seconds.

        For a 3-track album with silence gaps at 3:30 and 7:15,
        returns [210.0, 435.0] (2 boundaries for 3 tracks).
        """
        ranges, sample_rate = self._get_ranges(audio_path)

        if len(ranges) <= 1:
            return []

        # Extract boundaries: each range's start (except first) is a boundary
        boundaries: list[float] = []
        for i in range(1, len(ranges)):
            start_sample = ranges[i][0]
            boundaries.append(start_sample / sample_rate)

        return boundaries

    def _get_ranges(self, audio_path: str) -> tuple[list[tuple[int, int]], int]:
        """Get slice ranges (sample positions) from an audio file.

        Returns (ranges, sample_rate) where ranges are (start_sample, end_sample) tuples.
        """
        with soundfile.SoundFile(audio_path) as source_file:
            sample_rate = source_file.samplerate
            total_samples = len(source_file)

            slicer = Slicer(
                sr=sample_rate,
                threshold=self.threshold,
                min_length=self.min_length,
                min_interval=self.min_interval,
                hop_size=self.hop_size,
                max_sil_kept=self.max_sil_kept,
            )

            # Quick check: file too short to split
            if (total_samples + slicer.hop_size - 1) // slicer.hop_size <= slicer.min_length:
                return [(0, total_samples)], sample_rate

            rms_list = self._build_rms_list_from_file(source_file, slicer)
            ranges = slicer.slice_ranges_from_rms(rms_list, total_samples)
            return ranges, sample_rate

    @staticmethod
    def _build_rms_list_from_file(
        source_file: soundfile.SoundFile,
        slicer: Slicer,
        read_size: int = 131072,
    ) -> np.ndarray:
        """Streaming RMS calculation adapted from audio-slicer's slicing_tasks.py.

        Reads audio in blocks, accumulates RMS values with frame overlap handling.
        Peak memory usage is bounded regardless of file size.
        """
        source_file.seek(0)
        pad = slicer.win_size // 2
        buffer = np.zeros(pad, dtype=np.float32)
        rms_parts: list[np.ndarray] = []

        while True:
            chunk = source_file.read(read_size, dtype="float32", always_2d=True)
            if len(chunk) == 0:
                break
            # Downmix stereo to mono
            mono = chunk.mean(axis=1, dtype=np.float32)
            buffer = np.concatenate((buffer, mono.astype(np.float32, copy=False)))
            values, buffer = SilenceDetector._consume_rms_frames(buffer, slicer)
            if values.size:
                rms_parts.append(values)

        buffer = np.concatenate((buffer, np.zeros(pad, dtype=np.float32)))
        values, _ = SilenceDetector._consume_rms_frames(buffer, slicer)
        if values.size:
            rms_parts.append(values)

        if not rms_parts:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(rms_parts)

    @staticmethod
    def _consume_rms_frames(
        buffer: np.ndarray, slicer: Slicer
    ) -> tuple[np.ndarray, np.ndarray]:
        """Consume available RMS frames from the buffer.
        
        Uses sliding window over the buffer to compute RMS values.
        Returns (rms_values, remaining_buffer).
        """
        if buffer.shape[0] < slicer.win_size:
            return np.zeros(0, dtype=np.float32), buffer

        usable = ((buffer.shape[0] - slicer.win_size) // slicer.hop_size) + 1
        window_view = np.lib.stride_tricks.sliding_window_view(buffer, slicer.win_size)
        windows = window_view[:: slicer.hop_size][:usable]
        rms_values = np.sqrt(
            np.mean(np.abs(windows) ** 2, axis=1, dtype=np.float64)
        ).astype(np.float32)
        remaining = buffer[usable * slicer.hop_size :]
        return rms_values, remaining
