from dataclasses import dataclass, field

import numpy as np


@dataclass
class TrackMatch:
    """Result of matching a detected segment to a database track."""
    number: int
    title: str
    artist: str
    start: float          # start time in seconds
    end: float            # end time in seconds
    expected_duration: float   # duration from metadata
    actual_duration: float     # duration from audio
    confidence: float     # 0.0–1.0
    flags: list[str] = field(default_factory=list)


class TrackMatcher:
    """Matches N silence-detected boundaries to M database-provided track durations.

    Primary algorithm: Dynamic Time Warping with Sakoe-Chiba band constraint.
    Fallback: greedy nearest-neighbor matching.
    """

    def __init__(
        self,
        tolerance: float = 3.0,
        gap_seconds: float = 30.0,
        min_segment_duration: float = 15.0,
    ):
        self.tolerance = tolerance
        self.gap_seconds = gap_seconds
        self.min_segment_duration = min_segment_duration

    def _merge_short_segments(
        self, boundaries: list[float], total_duration: float
    ) -> list[float]:
        """Remove spurious boundaries that create segments shorter than the threshold.

        Very short detected segments are usually quiet passages inside a real
        track rather than separate tracks. Merging them before DTW prevents the
        aligner from getting derailed by false-positive silence detections.
        """
        boundaries = list(boundaries)
        changed = True
        while changed and boundaries:
            changed = False
            starts = [0.0] + boundaries + [total_duration]
            durations = [starts[i + 1] - starts[i] for i in range(len(starts) - 1)]
            for i, duration in enumerate(durations):
                if duration < self.min_segment_duration:
                    if i + 1 < len(durations):
                        boundaries = boundaries[:i] + boundaries[i + 1 :]
                    elif i > 0:
                        boundaries = boundaries[: i - 1] + boundaries[i:]
                    changed = True
                    break
        return boundaries

    def match(
        self,
        boundaries: list[float],
        track_durations: list[float],
        track_titles: list[str],
        track_artists: list[str],
        total_duration: float,
    ) -> list[TrackMatch]:
        """Match detected boundaries to expected track durations.

        Args:
            boundaries: Detected boundary timestamps in seconds.
            track_durations: Expected track durations from metadata.
            track_titles: Track titles from metadata.
            track_artists: Track artists from metadata.
            total_duration: Total duration of the audio file.
        """
        boundaries = self._merge_short_segments(boundaries, total_duration)

        # Build expected boundaries by accumulating track durations
        expected_starts = self._durations_to_boundaries(track_durations)

        matches = self._dtw_match(boundaries, expected_starts, total_duration)

        # Fill in titles and artists
        for match in matches:
            idx = match.number - 1
            if 0 <= idx < len(track_titles):
                match.title = track_titles[idx]
            if 0 <= idx < len(track_artists):
                match.artist = track_artists[idx]

        return matches

    def _durations_to_boundaries(self, durations: list[float]) -> list[float]:
        """Convert track durations to expected boundary timestamps."""
        starts = [0.0]
        cumsum = 0.0
        for d in durations[:-1]:
            cumsum += d
            starts.append(cumsum)
        return starts

    def _dtw_match(
        self,
        boundaries: list[float],
        expected_starts: list[float],
        total_duration: float,
    ) -> list[TrackMatch]:
        """DTW-based alignment of N detected boundaries to M expected track starts."""
        if not boundaries and not expected_starts:
            return []

        n = len(boundaries) + 1  # segments
        m = len(expected_starts)  # expected tracks

        if n == 1:
            return self._single_track_match(expected_starts, total_duration)

        # Build actual segment durations from boundaries
        actual_starts = [0.0] + list(boundaries)
        actual_ends = list(boundaries) + [total_duration]
        actual_durations = [actual_ends[i] - actual_starts[i] for i in range(n)]

        expected_durations = []
        for i in range(m):
            end = expected_starts[i + 1] if i + 1 < len(expected_starts) else total_duration
            expected_durations.append(end - expected_starts[i])

        cost = np.zeros((n, m))
        for i in range(n):
            for j in range(m):
                expected = expected_durations[j]
                relative_diff = abs(actual_durations[i] - expected) / max(expected, 1.0)
                cost[i, j] = relative_diff

        dtw_matrix = np.full((n + 1, m + 1), np.inf)
        dtw_matrix[0, 0] = 0

        skip_segment_cost = 0.5
        share_segment_cost = 0.05

        for i in range(1, n + 1):
            for j in range(1, m + 1):
                match_cost = dtw_matrix[i - 1, j - 1] + cost[i - 1, j - 1]
                skip_actual = dtw_matrix[i - 1, j] + skip_segment_cost
                share_actual = dtw_matrix[i, j - 1] + share_segment_cost
                dtw_matrix[i, j] = min(match_cost, skip_actual, share_actual)

        alignment: list[int] = [-1] * m
        i, j = n, m
        while i > 0 and j > 0:
            current = dtw_matrix[i, j]
            match_prev = dtw_matrix[i - 1, j - 1] + cost[i - 1, j - 1]
            skip_prev = dtw_matrix[i - 1, j] + skip_segment_cost
            share_prev = dtw_matrix[i, j - 1] + share_segment_cost
            best = min(match_prev, skip_prev, share_prev)
            if best == match_prev:
                alignment[j - 1] = i - 1
                i -= 1
                j -= 1
            elif best == skip_prev:
                i -= 1
            else:
                alignment[j - 1] = i - 1
                j -= 1

        matches: list[TrackMatch] = []
        run_start = 0
        while run_start < m:
            seg_idx = alignment[run_start]
            run_end = run_start + 1
            while run_end < m and alignment[run_end] == seg_idx:
                run_end += 1

            seg_start = actual_starts[seg_idx]
            seg_end = actual_ends[seg_idx]
            seg_duration = seg_end - seg_start

            expected_sum = sum(expected_durations[k] for k in range(run_start, run_end))
            offset = 0.0
            for k in range(run_start, run_end):
                ratio = expected_durations[k] / max(expected_sum, 1.0)
                track_start = seg_start + offset
                track_end = seg_start + offset + ratio * seg_duration
                actual_dur = track_end - track_start
                dur_diff = abs(actual_dur - expected_durations[k])
                confidence = max(0.0, 1.0 - (dur_diff / self.tolerance) ** 2)
                flags: list[str] = []
                if dur_diff > self.tolerance:
                    flags.append("duration_mismatch")
                if run_end - run_start > 1:
                    flags.append("shared_segment")
                matches.append(
                    TrackMatch(
                        number=k + 1,
                        title="",
                        artist="",
                        start=track_start,
                        end=track_end,
                        expected_duration=expected_durations[k],
                        actual_duration=actual_dur,
                        confidence=confidence,
                        flags=flags,
                    )
                )
                offset += ratio * seg_duration

            run_start = run_end

        # Handle extra segments (N > M) or missing tracks (N < M)
        if n > m:
            for match in matches:
                match.flags.append("extra_segment")
        elif n < m:
            for match in matches:
                match.flags.append("missing_track")

        # Segment count bonus/penalty
        count_penalty = abs(n - m) * 0.1
        for match in matches:
            match.confidence = max(0.0, match.confidence - count_penalty)

        return matches

    def _greedy_match(
        self,
        boundaries: list[float],
        expected_starts: list[float],
        total_duration: float,
    ) -> list[TrackMatch]:
        """Greedy nearest-neighbor matching fallback."""
        n = len(boundaries) + 1
        actual_starts = [0.0] + list(boundaries)
        actual_ends = list(boundaries) + [total_duration]
        m = len(expected_starts)

        matches: list[TrackMatch] = []
        for j, expected_start in enumerate(expected_starts):
            # Find nearest detected boundary
            best_i = 0
            best_dist = float("inf")
            for i, actual_start in enumerate(actual_starts):
                dist = abs(actual_start - expected_start)
                if dist < best_dist:
                    best_dist = dist
                    best_i = i

            if best_dist <= self.tolerance:
                confidence = max(0.0, 1.0 - (best_dist / self.tolerance) ** 2)
            else:
                confidence = max(0.0, 1.0 - (best_dist / (self.tolerance * 3)) ** 2)

            matches.append(
                TrackMatch(
                    number=j + 1,
                    title="",
                    artist="",
                    start=actual_starts[best_i],
                    end=actual_ends[best_i],
                    expected_duration=(
                        expected_starts[j + 1] if j + 1 < len(expected_starts) else total_duration
                    ) - expected_start,
                    actual_duration=actual_ends[best_i] - actual_starts[best_i],
                    confidence=confidence,
                    flags=[],
                )
            )

        if n > m:
            for match in matches:
                match.flags.append("extra_segment")
        elif n < m:
            for match in matches:
                match.flags.append("missing_track")

        return matches

    def _single_track_match(
        self, expected_starts: list[float], total_duration: float
    ) -> list[TrackMatch]:
        """Handle the single-track (no boundaries detected) case."""
        matches: list[TrackMatch] = []
        for j, start in enumerate(expected_starts):
            end = (
                expected_starts[j + 1]
                if j + 1 < len(expected_starts)
                else total_duration
            )
            matches.append(
                TrackMatch(
                    number=j + 1,
                    title="",
                    artist="",
                    start=start,
                    end=end,
                    expected_duration=end - start,
                    actual_duration=end - start,
                    confidence=0.5,  # low confidence — no boundaries
                    flags=["no_boundaries"],
                )
            )
        return matches

    def refine_boundaries(
        self,
        boundaries: list[float],
        expected_starts: list[float],
        rms_list: np.ndarray,
        sample_rate: int,
    ) -> list[float]:
        """Refine each boundary by searching for lowest-RMS frame near expected positions.

        Searches within ±gap_seconds of each expected boundary for the frame
        with the lowest RMS value.
        """
        if rms_list is None or len(rms_list) == 0:
            return list(boundaries)

        frame_duration = 1.0 / sample_rate  # approximate — RMS hop may differ
        gap_frames = int(self.gap_seconds / frame_duration) if frame_duration > 0 else 0

        refined: list[float] = []
        for boundary in boundaries:
            best_time = boundary
            if gap_frames > 0 and len(rms_list) > 0:
                center_frame = int(boundary / frame_duration)
                start_frame = max(0, center_frame - gap_frames)
                end_frame = min(len(rms_list), center_frame + gap_frames)

                if start_frame < end_frame:
                    window = rms_list[start_frame:end_frame]
                    min_idx = int(np.argmin(window))
                    best_time = (start_frame + min_idx) * frame_duration

            refined.append(best_time)

        return refined

    def detect_htoa(
        self,
        boundaries: list[float],
        total_duration: float,
        min_htoa_sec: float = 10.0,
    ) -> bool:
        """Detect HTOA (Hidden Track One Audio) before first boundary."""
        if not boundaries:
            return False
        return boundaries[0] >= min_htoa_sec

    def filter_false_positives(
        self,
        boundaries: list[float],
        expected_starts: list[float],
    ) -> list[float]:
        """Remove detected silences not near any expected track boundary."""
        return [
            b
            for b in boundaries
            if any(abs(b - es) <= self.tolerance for es in expected_starts)
        ]
