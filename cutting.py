from __future__ import annotations

from bisect import bisect_left
from typing import Any, Sequence


def build_effective_cut_keys(state_keys: Sequence[tuple[float, bool, Any]]) -> list[float]:
    if not state_keys:
        return []

    effective_keys = [float(state_keys[0][0])]
    prev_state = (bool(state_keys[0][1]), state_keys[0][2])
    for frame, enabled, target in state_keys[1:]:
        current_state = (bool(enabled), target)
        if current_state != prev_state:
            effective_keys.append(float(frame))
        prev_state = current_state
    return effective_keys


def build_cut_segments(pose_keys: Sequence[float], cut_keys: Sequence[float]) -> list[tuple[float, float]]:
    pose_key_list = sorted(float(frame) for frame in set(pose_keys))
    cut_key_list = sorted(float(frame) for frame in set(cut_keys))
    if len(pose_key_list) < 2 or not cut_key_list:
        return []

    pose_key_to_index = {frame: index for index, frame in enumerate(pose_key_list)}
    segments: set[tuple[float, float]] = set()
    for cut_key in cut_key_list:
        exact_index = pose_key_to_index.get(cut_key)
        if exact_index is not None:
            if exact_index > 0:
                segments.add((pose_key_list[exact_index - 1], pose_key_list[exact_index]))
            continue
        insert_index = bisect_left(pose_key_list, cut_key)
        if insert_index <= 0 or insert_index >= len(pose_key_list):
            continue
        segments.add((pose_key_list[insert_index - 1], pose_key_list[insert_index]))

    return sorted(segments)


def find_cut_sample_frame(frame: float, cut_segments: Sequence[tuple[float, float]]) -> float | None:
    for left, right in cut_segments:
        if left < frame < right:
            return float(left)
    return None

