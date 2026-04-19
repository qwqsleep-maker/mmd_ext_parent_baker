from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Iterable, Mapping


@dataclass(frozen=True, slots=True)
class ExternalParentEvent:
    frame: float
    enabled: bool
    target_root_object_name: str | None
    target_bone_name_j: str | None

    @property
    def target_key(self) -> str | None:
        if not self.enabled:
            return None
        return f"{self.target_root_object_name}\0{self.target_bone_name_j}"


@dataclass(frozen=True, slots=True)
class ExternalParentTrack:
    source_bone_name_j: str
    events: tuple[ExternalParentEvent, ...]


@dataclass(frozen=True, slots=True)
class ExternalParentBakeRequest:
    root_object_name: str
    armature_object_name: str
    source_action_name: str
    frame_start: int
    frame_end: int
    output_action_name: str
    tracks: tuple[ExternalParentTrack, ...]


def parse_bake_request(payload: Mapping[str, Any]) -> ExternalParentBakeRequest:
    root_object_name = _read_required_string(payload, "root_object_name")
    armature_object_name = _read_required_string(payload, "armature_object_name")
    source_action_name = _read_required_string(payload, "source_action_name")
    frame_start = _read_required_int(payload, "frame_start")
    frame_end = _read_required_int(payload, "frame_end")
    if frame_end < frame_start:
        raise ValueError("frame_end must be greater than or equal to frame_start")

    output_action_name = _read_optional_string(payload, "output_action_name")
    if not output_action_name:
        output_action_name = f"{source_action_name}__extparent_baked"

    raw_tracks = payload.get("tracks")
    if not isinstance(raw_tracks, Iterable) or isinstance(raw_tracks, (str, bytes, bytearray)):
        raise ValueError("tracks must be a non-empty list")

    tracks: list[ExternalParentTrack] = []
    seen_source_bones: set[str] = set()
    for raw_track in raw_tracks:
        if not isinstance(raw_track, Mapping):
            raise ValueError("track must be an object")
        source_bone_name_j = _read_required_string(raw_track, "source_bone_name_j")
        if source_bone_name_j in seen_source_bones:
            raise ValueError(f"duplicate source_bone_name_j: {source_bone_name_j}")
        seen_source_bones.add(source_bone_name_j)
        tracks.append(
            ExternalParentTrack(
                source_bone_name_j=source_bone_name_j,
                events=_parse_track_events(raw_track),
            )
        )

    if not tracks:
        raise ValueError("tracks must contain at least one track")

    return ExternalParentBakeRequest(
        root_object_name=root_object_name,
        armature_object_name=armature_object_name,
        source_action_name=source_action_name,
        frame_start=frame_start,
        frame_end=frame_end,
        output_action_name=output_action_name,
        tracks=tuple(tracks),
    )


def _parse_track_events(track_payload: Mapping[str, Any]) -> tuple[ExternalParentEvent, ...]:
    raw_events = track_payload.get("events")
    if not isinstance(raw_events, Iterable) or isinstance(raw_events, (str, bytes, bytearray)):
        raise ValueError("track events must be a non-empty list")

    deduped: dict[float, ExternalParentEvent] = {}
    for raw_event in raw_events:
        if not isinstance(raw_event, Mapping):
            raise ValueError("event must be an object")
        frame = _read_required_number(raw_event, "frame")
        enabled = _read_required_bool(raw_event, "enabled")
        target_root_object_name = _read_optional_string(raw_event, "target_root_object_name")
        target_bone_name_j = _read_optional_string(raw_event, "target_bone_name_j")
        if enabled and (not target_root_object_name or not target_bone_name_j):
            raise ValueError("enabled external-parent event requires target_root_object_name and target_bone_name_j")
        if not enabled:
            target_root_object_name = None
            target_bone_name_j = None
        deduped[frame] = ExternalParentEvent(
            frame=frame,
            enabled=enabled,
            target_root_object_name=target_root_object_name,
            target_bone_name_j=target_bone_name_j,
        )

    if not deduped:
        raise ValueError("track must contain at least one event")

    return tuple(event for _, event in sorted(deduped.items(), key=lambda item: item[0]))


def _read_required_string(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return value.strip()


def _read_optional_string(payload: Mapping[str, Any], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string when provided")
    value = value.strip()
    return value or None


def _read_required_bool(payload: Mapping[str, Any], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _read_required_number(payload: Mapping[str, Any], key: str) -> float:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    value = float(value)
    if not isfinite(value):
        raise ValueError(f"{key} must be finite")
    return value


def _read_required_int(payload: Mapping[str, Any], key: str) -> int:
    value = _read_required_number(payload, key)
    if int(round(value)) != value:
        raise ValueError(f"{key} must be an integer frame")
    return int(value)

