from __future__ import annotations

import bpy

from .scene_models import BoneInfo, ModelInfo, SceneSummary


def collect_scene_summary() -> SceneSummary:
    scene = bpy.context.scene
    fps_base = float(scene.render.fps_base) if scene.render.fps_base else 1.0
    fps = float(scene.render.fps) / fps_base

    models: list[ModelInfo] = []
    roots = sorted(_iter_mmd_root_objects(), key=lambda obj: obj.name)
    for root_object in roots:
        armature_object = _find_armature_child(root_object)
        if armature_object is None:
            continue
        active_action = getattr(getattr(armature_object, "animation_data", None), "action", None)
        bones = sorted(
            (
                BoneInfo(
                    bone_name=pose_bone.name,
                    bone_name_j=_get_pose_bone_name_j(pose_bone),
                    bone_id=int(getattr(getattr(pose_bone, "mmd_bone", None), "bone_id", -1)),
                )
                for pose_bone in armature_object.pose.bones
            ),
            key=lambda bone: (bone.bone_id < 0, bone.bone_id, bone.bone_name),
        )
        models.append(
            ModelInfo(
                root_object_name=root_object.name,
                armature_object_name=armature_object.name,
                active_action_name=getattr(active_action, "name", None),
                bones=bones,
            )
        )

    return SceneSummary(
        frame_start=int(scene.frame_start),
        frame_end=int(scene.frame_end),
        fps=fps,
        models=models,
    )


def resolve_model(root_object_name: str, armature_object_name: str) -> tuple[bpy.types.Object, bpy.types.Object]:
    root_object = bpy.data.objects.get(root_object_name)
    if root_object is None or not _is_mmd_root_object(root_object):
        raise ValueError(f'root object "{root_object_name}" was not found or is not an MMD root')

    armature_object = bpy.data.objects.get(armature_object_name)
    if armature_object is None or armature_object.type != "ARMATURE":
        raise ValueError(f'armature object "{armature_object_name}" was not found')

    resolved_armature = _find_armature_child(root_object)
    if resolved_armature != armature_object:
        raise ValueError(
            f'armature object "{armature_object_name}" does not belong to root object "{root_object_name}"'
        )
    return root_object, armature_object


def resolve_root_with_armature(root_object_name: str) -> tuple[bpy.types.Object, bpy.types.Object]:
    root_object = bpy.data.objects.get(root_object_name)
    if root_object is None or not _is_mmd_root_object(root_object):
        raise ValueError(f'root object "{root_object_name}" was not found or is not an MMD root')

    armature_object = _find_armature_child(root_object)
    if armature_object is None:
        raise ValueError(f'root object "{root_object_name}" does not have an armature child')
    return root_object, armature_object


def build_bone_lookup_by_name_j(armature_object: bpy.types.Object) -> dict[str, bpy.types.PoseBone]:
    lookup: dict[str, bpy.types.PoseBone] = {}
    for pose_bone in armature_object.pose.bones:
        name_j = _get_pose_bone_name_j(pose_bone)
        if name_j in lookup:
            raise ValueError(
                f'armature "{armature_object.name}" has duplicate Japanese bone name "{name_j}"'
            )
        lookup[name_j] = pose_bone
    return lookup


def resolve_pose_bone_by_name_j(armature_object: bpy.types.Object, bone_name_j: str) -> bpy.types.PoseBone:
    lookup = build_bone_lookup_by_name_j(armature_object)
    pose_bone = lookup.get(bone_name_j)
    if pose_bone is None:
        raise ValueError(f'armature "{armature_object.name}" does not contain Japanese bone name "{bone_name_j}"')
    return pose_bone


def _get_pose_bone_name_j(pose_bone: bpy.types.PoseBone) -> str:
    mmd_bone = getattr(pose_bone, "mmd_bone", None)
    name_j = getattr(mmd_bone, "name_j", "") if mmd_bone is not None else ""
    return name_j or pose_bone.name


def _iter_mmd_root_objects():
    for obj in bpy.data.objects:
        if _is_mmd_root_object(obj):
            yield obj


def _is_mmd_root_object(obj: bpy.types.Object | None) -> bool:
    return obj is not None and getattr(obj, "mmd_type", "") == "ROOT"


def _find_armature_child(root_object: bpy.types.Object | None) -> bpy.types.Object | None:
    if not _is_mmd_root_object(root_object):
        return None
    for child in root_object.children:
        if child.type == "ARMATURE":
            return child
    return None
