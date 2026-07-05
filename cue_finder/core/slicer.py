"""RMS-based audio slicer for silence detection.

Integrated from the audio-slicer project (https://github.com/flutydeer/audio-slicer)
Copyright (c) 2022 Team OpenVPI, MIT License.
"""

import numpy as np


# This function is obtained from librosa.
def get_rms(
    y,
    *,
    frame_length=2048,
    hop_length=512,
    pad_mode="constant",
):
    padding = (int(frame_length // 2), int(frame_length // 2))
    y = np.pad(y, padding, mode=pad_mode)

    axis = -1
    # put our new within-frame axis at the end for now
    out_strides = y.strides + tuple([y.strides[axis]])
    # Reduce the shape on the framing axis
    x_shape_trimmed = list(y.shape)
    x_shape_trimmed[axis] -= frame_length - 1
    out_shape = tuple(x_shape_trimmed) + tuple([frame_length])
    xw = np.lib.stride_tricks.as_strided(
        y, shape=out_shape, strides=out_strides
    )
    if axis < 0:
        target_axis = axis - 1
    else:
        target_axis = axis + 1
    xw = np.moveaxis(xw, -1, target_axis)
    # Downsample along the target axis
    slices = [slice(None)] * xw.ndim
    slices[axis] = slice(0, None, hop_length)
    x = xw[tuple(slices)]

    # Calculate power
    power = np.mean(np.abs(x) ** 2, axis=-2, keepdims=True)

    return np.sqrt(power)


class Slicer:
    def __init__(self,
                 sr: int,
                 threshold: float = -40.,
                 min_length: int = 5000,
                 min_interval: int = 300,
                 hop_size: int = 20,
                 max_sil_kept: int = 5000):
        if not min_length >= min_interval >= hop_size:
            raise ValueError('The following condition must be satisfied: min_length >= min_interval >= hop_size')
        if not max_sil_kept >= hop_size:
            raise ValueError('The following condition must be satisfied: max_sil_kept >= hop_size')
        min_interval = sr * min_interval / 1000
        self.threshold = 10 ** (threshold / 20.)
        self.hop_size = round(sr * hop_size / 1000)
        self.win_size = min(round(min_interval), 4 * self.hop_size)
        self.min_length = round(sr * min_length / 1000 / self.hop_size)
        self.min_interval = round(min_interval / self.hop_size)
        self.max_sil_kept = round(sr * max_sil_kept / 1000 / self.hop_size)

    def _apply_slice(self, waveform, begin, end):
        if len(waveform.shape) > 1:
            return waveform[:, begin * self.hop_size: min(waveform.shape[1], end * self.hop_size)]
        else:
            return waveform[begin * self.hop_size: min(waveform.shape[0], end * self.hop_size)]

    def _frame_to_sample(self, frame_index: int, total_samples: int) -> int:
        return min(total_samples, frame_index * self.hop_size)

    def slice_ranges(self, waveform):
        if len(waveform.shape) > 1:
            samples = waveform.mean(axis=0)
            total_samples = waveform.shape[1]
        else:
            samples = waveform
            total_samples = waveform.shape[0]
        if (samples.shape[0] + self.hop_size - 1) // self.hop_size <= self.min_length:
            return [(0, total_samples)]

        rms_list = get_rms(
            y=samples,
            frame_length=self.win_size,
            hop_length=self.hop_size,
        ).squeeze(0)
        return self.slice_ranges_from_rms(rms_list, total_samples)

    def slice_ranges_from_rms(self, rms_list, total_samples):
        if rms_list.shape[0] == 0:
            return [(0, total_samples)]

        total_frames = rms_list.shape[0]
        if total_frames <= self.min_length:
            return [(0, total_samples)]

        sil_tags = []
        silence_start = None
        clip_start = 0
        for i, rms in enumerate(rms_list):
            # Keep looping while frame is silent.
            if rms < self.threshold:
                # Record start of silent frames.
                if silence_start is None:
                    silence_start = i
                continue
            # Keep looping while frame is not silent and silence start has not been recorded.
            if silence_start is None:
                continue
            # Clear recorded silence start if interval is not enough or clip is too short
            is_leading_silence = silence_start == 0 and i > self.max_sil_kept
            need_slice_middle = i - silence_start >= self.min_interval and i - clip_start >= self.min_length
            if not is_leading_silence and not need_slice_middle:
                silence_start = None
                continue
            # Need slicing. Record the range of silent frames to be removed.
            if i - silence_start <= self.max_sil_kept:
                pos = rms_list[silence_start: i + 1].argmin() + silence_start
                if silence_start == 0:
                    sil_tags.append((0, pos))
                else:
                    sil_tags.append((pos, pos))
                clip_start = pos
            elif i - silence_start <= self.max_sil_kept * 2:
                pos = rms_list[i - self.max_sil_kept: silence_start + self.max_sil_kept + 1].argmin()
                pos += i - self.max_sil_kept
                pos_l = rms_list[silence_start: silence_start + self.max_sil_kept + 1].argmin() + silence_start
                pos_r = rms_list[i - self.max_sil_kept: i + 1].argmin() + i - self.max_sil_kept
                if silence_start == 0:
                    sil_tags.append((0, pos_r))
                    clip_start = pos_r
                else:
                    sil_tags.append((min(pos_l, pos), max(pos_r, pos)))
                    clip_start = max(pos_r, pos)
            else:
                pos_l = rms_list[silence_start: silence_start + self.max_sil_kept + 1].argmin() + silence_start
                pos_r = rms_list[i - self.max_sil_kept: i + 1].argmin() + i - self.max_sil_kept
                if silence_start == 0:
                    sil_tags.append((0, pos_r))
                else:
                    sil_tags.append((pos_l, pos_r))
                clip_start = pos_r
            silence_start = None
        # Deal with trailing silence.
        if silence_start is not None and total_frames - silence_start >= self.min_interval:
            silence_end = min(total_frames, silence_start + self.max_sil_kept)
            pos = rms_list[silence_start: silence_end + 1].argmin() + silence_start
            sil_tags.append((pos, total_frames + 1))

        # Convert silent tags to sample ranges for the kept clips.
        if len(sil_tags) == 0:
            return [(0, total_samples)]

        ranges = []
        if sil_tags[0][0] > 0:
            ranges.append((0, self._frame_to_sample(sil_tags[0][0], total_samples)))
        for i in range(len(sil_tags) - 1):
            ranges.append(
                (
                    self._frame_to_sample(sil_tags[i][1], total_samples),
                    self._frame_to_sample(sil_tags[i + 1][0], total_samples),
                )
            )
        if sil_tags[-1][1] < total_frames:
            ranges.append((self._frame_to_sample(sil_tags[-1][1], total_samples), total_samples))
        return ranges

    def slice(self, waveform):
        ranges = self.slice_ranges(waveform)
        if len(waveform.shape) > 1:
            return [waveform[:, begin:end] for begin, end in ranges]
        return [waveform[begin:end] for begin, end in ranges]
