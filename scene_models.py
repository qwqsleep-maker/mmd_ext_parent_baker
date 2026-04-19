from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class BoneInfo:
    bone_name: str
    bone_name_j: str
    bone_id: int

    def to_payload(self) -> dict[str, object]:
        return {
            "bone_name": self.bone_name,
            "bone_name_j": self.bone_name_j,
            "bone_id": self.bone_id,
        }


@dataclass(frozen=True, slots=True)
class ModelInfo:
    root_object_name: str
    armature_object_name: str
    active_action_name: str | None
    bones: list[BoneInfo] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "root_object_name": self.root_object_name,
            "armature_object_name": self.armature_object_name,
            "active_action_name": self.active_action_name,
            "bones": [bone.to_payload() for bone in self.bones],
        }


@dataclass(frozen=True, slots=True)
class SceneSummary:
    frame_start: int
    frame_end: int
    fps: float
    models: list[ModelInfo] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "frame_start": self.frame_start,
            "frame_end": self.frame_end,
            "fps": self.fps,
            "models": [model.to_payload() for model in self.models],
        }
