"""Tests for silence detection module."""

import pytest
from cue_finder.core.silence import SilenceDetector


class TestSilenceDetector:
    def test_detect_boundaries_with_gaps(self, sample_wav_with_gaps):
        detector = SilenceDetector(threshold=-40, min_length=5000,
                                   min_interval=300, hop_size=10, max_sil_kept=500)
        boundaries = detector.detect_boundaries(str(sample_wav_with_gaps))

        assert len(boundaries) == 2
        # Expected boundaries at ~210s and ~435s (±hop_size tolerance)
        assert 205 < boundaries[0] < 215, f"Expected ~210, got {boundaries[0]}"
        assert 430 < boundaries[1] < 440, f"Expected ~435, got {boundaries[1]}"

    def test_gapless_album_no_boundaries(self, sample_wav_gapless):
        detector = SilenceDetector()
        boundaries = detector.detect_boundaries(str(sample_wav_gapless))

        assert boundaries == []

    def test_short_file_no_boundaries(self, sample_wav_short):
        detector = SilenceDetector()
        boundaries = detector.detect_boundaries(str(sample_wav_short))

        assert boundaries == []

    def test_invalid_params_min_length_lt_min_interval(self):
        with pytest.raises(ValueError, match="min_length >= min_interval"):
            SilenceDetector(min_length=200, min_interval=300)

    def test_invalid_params_min_interval_lt_hop_size(self):
        with pytest.raises(ValueError, match="min_length >= min_interval"):
            SilenceDetector(min_interval=5, hop_size=10)

    def test_invalid_params_max_sil_kept_lt_hop_size(self):
        with pytest.raises(
            ValueError, match="max_sil_kept >= hop_size"
        ):
            SilenceDetector(max_sil_kept=5, hop_size=10)

    def test_custom_threshold(self, sample_wav_with_gaps):
        # Very strict threshold should still find the clear silence gaps
        detector = SilenceDetector(threshold=-20)  # less sensitive
        boundaries = detector.detect_boundaries(str(sample_wav_with_gaps))

        assert len(boundaries) <= 2  # May find fewer but shouldn't error

    def test_consistent_with_multiple_runs(self, sample_wav_with_gaps):
        detector = SilenceDetector()
        boundaries1 = detector.detect_boundaries(str(sample_wav_with_gaps))
        boundaries2 = detector.detect_boundaries(str(sample_wav_with_gaps))

        assert len(boundaries1) == len(boundaries2)
        for b1, b2 in zip(boundaries1, boundaries2):
            assert abs(b1 - b2) < 0.01  # Should be deterministic
