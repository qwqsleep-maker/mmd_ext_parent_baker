from __future__ import annotations

from dataclasses import dataclass
from math import floor

import bpy
from mathutils import Matrix, Quaternion, Vector

from .cutting import build_cut_segments, build_effective_cut_keys, find_cut_sample_frame
from .external_parent_semantics import (
    decompose_blender_visual_channels,
    ResolvedExternalParentBakePose,
    apply_cut_sample,
    resolve_external_parent_bake_pose,
)
from .protocol import ExternalParentBakeRequest, ExternalParentEvent, ExternalParentTrack
from .scene_query import build_bone_lookup_by_name_j, resolve_model, resolve_root_with_armature


@dataclass(slots=True)
class ArmatureLayout:
    pose_bones: list[bpy.types.PoseBone]
    parent_index: list[int]
    children: list[list[int]]
    rest_local: list[Matrix]
    inv_rest_local: list[Matrix]
    name_to_index: dict[str, int]


@dataclass(slots=True)
class TrackRuntime:
    source_bone_name_j: str
    source_pose_bone_name: str
    source_index: int
    source_rest_matrix_local: Matrix
    events: tuple[ExternalParentEvent, ...]
    cut_segments: list[tuple[float, float]]
    target_lookup: dict[str, "ExternalParentTargetRuntime"]


@dataclass(slots=True)
class ExternalParentTargetRuntime:
    armature_object: bpy.types.Object
    target_pose_bone: bpy.types.PoseBone
    target_rest_matrix_local: Matrix


@dataclass(frozen=True, slots=True)
class DebugContext:
    enabled: bool = False
    source_bone_name_j: str = ""
    frame_start: int = 0
    frame_end: int = -1

    def matches_track(self, source_bone_name_j: str) -> bool:
        return self.enabled and bool(self.source_bone_name_j) and source_bone_name_j == self.source_bone_name_j

    def matches_frame(self, frame: float) -> bool:
        if not self.enabled:
            return False
        lower = min(self.frame_start, self.frame_end)
        upper = max(self.frame_start, self.frame_end)
        return lower <= frame <= upper

    def should_log(self, source_bone_name_j: str, frame: float) -> bool:
        return self.matches_track(source_bone_name_j) and self.matches_frame(frame)


def execute_external_parent_bake(request: ExternalParentBakeRequest) -> dict[str, object]:
    scene = bpy.context.scene
    debug_context = _read_debug_context()
    source_root_object, source_armature_object = resolve_model(
        request.root_object_name,
        request.armature_object_name,
    )
    source_action = getattr(getattr(source_armature_object, "animation_data", None), "action", None)
    if source_action is None:
        raise ValueError(f'armature "{source_armature_object.name}" does not have an active action')
    if source_action.name != request.source_action_name:
        raise ValueError(
            f'armature "{source_armature_object.name}" active action is "{source_action.name}", '
            f'expected "{request.source_action_name}"'
        )

    layout = _build_armature_layout(source_armature_object)
    source_bones_by_name_j = build_bone_lookup_by_name_j(source_armature_object)
    track_runtimes = [
        _build_track_runtime(
            track=track,
            source_action=source_action,
            source_bones_by_name_j=source_bones_by_name_j,
            layout=layout,
            debug_context=debug_context,
        )
        for track in request.tracks
    ]
    if debug_context.enabled and debug_context.source_bone_name_j and not any(
        debug_context.matches_track(runtime.source_bone_name_j) for runtime in track_runtimes
    ):
        available_tracks = ", ".join(f'"{runtime.source_bone_name_j}"' for runtime in track_runtimes) or "<none>"
        _debug_log(
            debug_context,
            debug_context.source_bone_name_j,
            None,
            "config",
            [
                f'No track matched source bone "{debug_context.source_bone_name_j}" in this bake request.',
                f"Available source bones in request: {available_tracks}",
            ],
        )
    baked_frames = list(range(request.frame_start, request.frame_end + 1))
    source_cache_frames = set(float(frame) for frame in baked_frames)
    for runtime in track_runtimes:
        for left_frame, _ in runtime.cut_segments:
            source_cache_frames.add(float(left_frame))
    debug_pose_name_to_source_name_j = {
        runtime.source_pose_bone_name: runtime.source_bone_name_j for runtime in track_runtimes
    }

    frame_restore = float(getattr(scene, "frame_current_final", scene.frame_current))
    output_action = None
    try:
        source_local_channels_by_frame = _capture_source_local_channels(
            scene=scene,
            armature_object=source_armature_object,
            layout=layout,
            frames=sorted(source_cache_frames),
        )

        output_action = bpy.data.actions.new(request.output_action_name)
        output_action.use_fake_user = True
        source_armature_object.animation_data_create()
        source_armature_object.animation_data.action = output_action

        per_bone_locations = {pose_bone.name: [] for pose_bone in layout.pose_bones}
        per_bone_rotations = {pose_bone.name: [] for pose_bone in layout.pose_bones}

        for frame in baked_frames:
            _set_scene_frame(scene, float(frame))
            current_local_channels = dict(source_local_channels_by_frame[float(frame)])
            external_parent_poses: dict[str, ResolvedExternalParentBakePose] = {}

            for runtime in track_runtimes:
                sample_frame = find_cut_sample_frame(float(frame), runtime.cut_segments)
                if sample_frame is not None:
                    current_local_channels = apply_cut_sample(
                        current_local_channels,
                        runtime.source_pose_bone_name,
                        source_local_channels_by_frame[sample_frame][runtime.source_pose_bone_name],
                    )
                    _debug_log(
                        debug_context,
                        runtime.source_bone_name_j,
                        float(frame),
                        "cut-segment",
                        [f"Using left cut-sample frame {sample_frame:g} for source local channels."],
                    )
                state = _resolve_state_at_frame(runtime.events, float(frame))
                if state is None or not state.enabled or state.target_key is None:
                    continue
                target_runtime = runtime.target_lookup[state.target_key]
                source_basis_matrix = _compose_local_matrix(*current_local_channels[runtime.source_pose_bone_name])
                external_parent_poses[runtime.source_pose_bone_name] = _resolve_external_parent_pose(
                    source_armature_object=source_armature_object,
                    runtime=runtime,
                    target_runtime=target_runtime,
                    source_basis_matrix=source_basis_matrix,
                    debug_context=debug_context,
                    debug_frame=float(frame),
                )

            absolute_pose = _build_external_parent_absolute_pose(
                layout=layout,
                local_channels=current_local_channels,
                external_parent_poses=external_parent_poses,
            )
            baked_local_channels = _decompose_blender_visual_absolute_pose(
                layout=layout,
                absolute_pose=absolute_pose,
                debug_context=debug_context,
                debug_frame=float(frame),
                debug_pose_name_to_source_name_j=debug_pose_name_to_source_name_j,
            )
            for pose_bone in layout.pose_bones:
                bone_name = pose_bone.name
                location, rotation = baked_local_channels[bone_name]
                per_bone_locations[bone_name].append(location)
                per_bone_rotations[bone_name].append(rotation)

        _write_baked_action(
            action=output_action,
            frames=baked_frames,
            pose_bones=layout.pose_bones,
            per_bone_locations=per_bone_locations,
            per_bone_rotations=per_bone_rotations,
        )
    except Exception:
        if output_action is not None:
            bpy.data.actions.remove(output_action)
        raise
    finally:
        _set_scene_frame(scene, frame_restore)

    return {
        "root_object_name": source_root_object.name,
        "armature_object_name": source_armature_object.name,
        "output_armature_object_name": source_armature_object.name,
        "output_mode": "original_armature_visual",
        "source_action_name": source_action.name,
        "output_action_name": output_action.name,
        "frame_start": request.frame_start,
        "frame_end": request.frame_end,
        "frame_count": len(baked_frames),
        "baked_bone_count": len(layout.pose_bones),
        "track_count": len(track_runtimes),
    }


def _build_track_runtime(
    track: ExternalParentTrack,
    source_action: bpy.types.Action,
    source_bones_by_name_j: dict[str, bpy.types.PoseBone],
    layout: ArmatureLayout,
    debug_context: DebugContext,
) -> TrackRuntime:
    source_pose_bone = source_bones_by_name_j.get(track.source_bone_name_j)
    if source_pose_bone is None:
        raise ValueError(f'source armature does not contain Japanese bone name "{track.source_bone_name_j}"')

    pose_keys = _collect_pose_keyframes(source_action, source_pose_bone.name)
    state_keys = [(event.frame, event.enabled, event.target_key) for event in track.events]
    cut_keys = build_effective_cut_keys(state_keys)
    cut_segments = build_cut_segments(pose_keys, cut_keys)

    target_lookup: dict[str, ExternalParentTargetRuntime] = {}
    for event in track.events:
        if not event.enabled or event.target_key is None:
            continue
        if event.target_key in target_lookup:
            continue
        _, target_armature_object = resolve_root_with_armature(event.target_root_object_name or "")
        target_bones_by_name_j = build_bone_lookup_by_name_j(target_armature_object)
        target_pose_bone = target_bones_by_name_j.get(event.target_bone_name_j or "")
        if target_pose_bone is None:
            raise ValueError(
                f'armature "{target_armature_object.name}" does not contain Japanese bone name '
                f'"{event.target_bone_name_j}"'
            )
        target_lookup[event.target_key] = _build_external_parent_target_runtime(
            target_armature_object=target_armature_object,
            target_pose_bone=target_pose_bone,
        )

    if debug_context.matches_track(track.source_bone_name_j):
        target_lines = [
            f'event frame={event.frame:g} enabled={event.enabled} target_root="{event.target_root_object_name}" '
            f'target_bone_name_j="{event.target_bone_name_j}"'
            for event in track.events
        ]
        _debug_log(
            debug_context,
            track.source_bone_name_j,
            None,
            "track-runtime",
            [
                f'source_bone_name_j="{track.source_bone_name_j}" source_pose_bone="{source_pose_bone.name}"',
                f"cut_segments={cut_segments}",
                *target_lines,
            ],
        )

    return TrackRuntime(
        source_bone_name_j=track.source_bone_name_j,
        source_pose_bone_name=source_pose_bone.name,
        source_index=layout.name_to_index[source_pose_bone.name],
        source_rest_matrix_local=source_pose_bone.bone.matrix_local.copy(),
        events=track.events,
        cut_segments=cut_segments,
        target_lookup=target_lookup,
    )


def _build_external_parent_target_runtime(
    target_armature_object: bpy.types.Object,
    target_pose_bone: bpy.types.PoseBone,
) -> ExternalParentTargetRuntime:
    return ExternalParentTargetRuntime(
        armature_object=target_armature_object,
        target_pose_bone=target_pose_bone,
        target_rest_matrix_local=target_pose_bone.bone.matrix_local.copy(),
    )


def _bone_rest_local_matrix(
    data_bones,
    pose_bone: bpy.types.PoseBone,
) -> Matrix:
    parent_pose_bone = pose_bone.parent
    current_rest = data_bones[pose_bone.name].matrix_local
    if parent_pose_bone is None:
        return current_rest.copy()
    parent_rest = data_bones[parent_pose_bone.name].matrix_local
    return parent_rest.inverted() @ current_rest


def _build_armature_layout(armature_object: bpy.types.Object) -> ArmatureLayout:
    pose_bones = list(armature_object.pose.bones)
    name_to_index = {pose_bone.name: index for index, pose_bone in enumerate(pose_bones)}
    parent_index = [-1] * len(pose_bones)
    children = [[] for _ in pose_bones]
    rest_local = [Matrix.Identity(4) for _ in pose_bones]
    inv_rest_local = [Matrix.Identity(4) for _ in pose_bones]

    data_bones = armature_object.data.bones
    for index, pose_bone in enumerate(pose_bones):
        parent_pose_bone = pose_bone.parent
        if parent_pose_bone is not None:
            parent_idx = name_to_index[parent_pose_bone.name]
            parent_index[index] = parent_idx
            children[parent_idx].append(index)
        rest_matrix = _bone_rest_local_matrix(data_bones, pose_bone)
        rest_local[index] = rest_matrix
        try:
            inv_rest_local[index] = rest_matrix.inverted()
        except Exception:
            inv_rest_local[index] = Matrix.Identity(4)

    return ArmatureLayout(
        pose_bones=pose_bones,
        parent_index=parent_index,
        children=children,
        rest_local=rest_local,
        inv_rest_local=inv_rest_local,
        name_to_index=name_to_index,
    )


def _capture_source_local_channels(
    scene: bpy.types.Scene,
    armature_object: bpy.types.Object,
    layout: ArmatureLayout,
    frames: list[float],
) -> dict[float, dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]]]:
    cache: dict[float, dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]]] = {}
    for frame in frames:
        _set_scene_frame(scene, frame)
        cache[frame] = _capture_visible_local_channels(armature_object, layout)
    return cache


def _capture_visible_local_channels(
    armature_object: bpy.types.Object,
    layout: ArmatureLayout,
) -> dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]]:
    _ = armature_object
    visible_local_channels: dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]] = {}
    identity = Matrix.Identity(4)
    for index, pose_bone in enumerate(layout.pose_bones):
        parent_pose = identity
        if layout.parent_index[index] >= 0:
            parent_pose = layout.pose_bones[layout.parent_index[index]].matrix.copy()
        _, location_values, rotation_values = _extract_local_pose_channels(
            inv_rest_local=layout.inv_rest_local[index],
            parent_pose=parent_pose,
            pose_matrix=pose_bone.matrix,
        )
        visible_local_channels[pose_bone.name] = (
            location_values,
            rotation_values,
        )
    return visible_local_channels


def _extract_local_pose_channels(
    *,
    inv_rest_local: Matrix,
    parent_pose: Matrix,
    pose_matrix: Matrix,
) -> tuple[Matrix, tuple[float, float, float], tuple[float, float, float, float]]:
    basis = inv_rest_local @ _safe_inverted(parent_pose) @ pose_matrix
    location = basis.to_translation()
    rotation = _safe_quaternion(basis.to_quaternion())
    return (
        basis,
        (float(location.x), float(location.y), float(location.z)),
        (float(rotation.w), float(rotation.x), float(rotation.y), float(rotation.z)),
    )


def _compose_local_matrix(
    location_values: tuple[float, float, float],
    rotation_values: tuple[float, float, float, float],
) -> Matrix:
    return Matrix.Translation(Vector(location_values)) @ _safe_quaternion(rotation_values).to_matrix().to_4x4()


def _build_external_parent_absolute_pose(
    layout: ArmatureLayout,
    local_channels: dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]],
    external_parent_poses: dict[str, ResolvedExternalParentBakePose],
) -> list[Matrix]:
    absolute_pose = [Matrix.Identity(4) for _ in layout.pose_bones]
    identity = Matrix.Identity(4)

    def visit(index: int, parent_pose: Matrix) -> None:
        pose_bone = layout.pose_bones[index]
        resolved_pose = external_parent_poses.get(pose_bone.name)
        if resolved_pose is not None:
            absolute_pose[index] = _rows_to_matrix(resolved_pose.source_armature_matrix)
        else:
            local_matrix = _compose_local_matrix(*local_channels[pose_bone.name])
            absolute_pose[index] = parent_pose @ layout.rest_local[index] @ local_matrix
        for child_index in layout.children[index]:
            visit(child_index, absolute_pose[index])

    for index, parent_idx in enumerate(layout.parent_index):
        if parent_idx < 0:
            visit(index, identity)
    return absolute_pose


def _decompose_blender_visual_absolute_pose(
    layout: ArmatureLayout,
    absolute_pose: list[Matrix],
    debug_context: DebugContext,
    debug_frame: float,
    debug_pose_name_to_source_name_j: dict[str, str],
) -> dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]]:
    local_channels: dict[str, tuple[tuple[float, float, float], tuple[float, float, float, float]]] = {}
    identity = Matrix.Identity(4)
    for index, pose_bone in enumerate(layout.pose_bones):
        parent_pose = identity
        if layout.parent_index[index] >= 0:
            parent_pose = absolute_pose[layout.parent_index[index]]
        channels = decompose_blender_visual_channels(
            parent_pose=_matrix_to_rows(parent_pose),
            rest_local=_matrix_to_rows(layout.rest_local[index]),
            absolute_pose=_matrix_to_rows(absolute_pose[index]),
        )
        location_values = channels.location
        rotation_values = channels.rotation
        rotation = _safe_quaternion(rotation_values)
        local_basis = Matrix.Translation(Vector(location_values)) @ rotation.to_matrix().to_4x4()
        debug_source_bone_name_j = debug_pose_name_to_source_name_j.get(pose_bone.name)
        if debug_source_bone_name_j and debug_context.should_log(debug_source_bone_name_j, debug_frame):
            blender_replayed_pose = parent_pose @ layout.rest_local[index] @ local_basis
            blender_replay_delta = _safe_inverted(absolute_pose[index]) @ blender_replayed_pose
            _debug_log(
                debug_context,
                debug_source_bone_name_j,
                debug_frame,
                "blender-visual-decompose",
                [
                    f"parent_pose={_format_matrix(parent_pose)}",
                    f"full_rest_local={_format_matrix(layout.rest_local[index])}",
                    f"semantic_absolute_location={_format_vector(absolute_pose[index].to_translation())}",
                    f"semantic_absolute_rotation={_format_quaternion(absolute_pose[index].to_quaternion())}",
                    f"blender_local_location={_format_vector(location_values)}",
                    f"blender_local_rotation={_format_quaternion(rotation_values)}",
                    f"blender_replayed_pose={_format_matrix(blender_replayed_pose)}",
                    f"blender_replay_delta={_format_matrix(blender_replay_delta)}",
                ],
            )
        local_channels[pose_bone.name] = (
            (float(location_values[0]), float(location_values[1]), float(location_values[2])),
            (float(rotation_values[0]), float(rotation_values[1]), float(rotation_values[2]), float(rotation_values[3])),
        )
    return local_channels


def _write_baked_action(
    action: bpy.types.Action,
    frames: list[int],
    pose_bones: list[bpy.types.PoseBone],
    per_bone_locations: dict[str, list[tuple[float, float, float]]],
    per_bone_rotations: dict[str, list[tuple[float, float, float, float]]],
) -> None:
    for pose_bone in pose_bones:
        bone_name = pose_bone.name
        location_path = f'pose.bones["{bone_name}"].location'
        rotation_path = f'pose.bones["{bone_name}"].rotation_quaternion'
        for axis in range(3):
            _write_curve(
                action=action,
                data_path=location_path,
                index=axis,
                group_name=bone_name,
                frames=frames,
                values=[sample[axis] for sample in per_bone_locations[bone_name]],
            )
        for axis in range(4):
            _write_curve(
                action=action,
                data_path=rotation_path,
                index=axis,
                group_name=bone_name,
                frames=frames,
                values=[sample[axis] for sample in per_bone_rotations[bone_name]],
            )


def _write_curve(
    action: bpy.types.Action,
    data_path: str,
    index: int,
    group_name: str,
    frames: list[int],
    values: list[float],
) -> None:
    fcurve = action.fcurves.new(data_path=data_path, index=index, action_group=group_name)
    fcurve.keyframe_points.add(len(frames))

    coordinates: list[float] = []
    for frame, value in zip(frames, values):
        coordinates.extend((float(frame), float(value)))
    fcurve.keyframe_points.foreach_set("co", coordinates)
    for keyframe_point in fcurve.keyframe_points:
        keyframe_point.interpolation = "LINEAR"
    fcurve.update()


def _collect_pose_keyframes(action: bpy.types.Action, bone_name: str) -> list[float]:
    location_path = f'pose.bones["{bone_name}"].location'
    rotation_paths = {
        f'pose.bones["{bone_name}"].rotation_quaternion',
        f'pose.bones["{bone_name}"].rotation_euler',
        f'pose.bones["{bone_name}"].rotation_axis_angle',
    }
    frames = set()
    for fcurve in action.fcurves:
        if fcurve.data_path == location_path or fcurve.data_path in rotation_paths:
            frames.update(float(keyframe.co.x) for keyframe in fcurve.keyframe_points)
    return sorted(frames)


def _resolve_state_at_frame(events: tuple[ExternalParentEvent, ...], frame: float) -> ExternalParentEvent | None:
    current_event = None
    for event in events:
        if event.frame <= frame:
            current_event = event
        else:
            break
    return current_event


def _resolve_external_parent_pose(
    source_armature_object: bpy.types.Object,
    runtime: TrackRuntime,
    target_runtime: ExternalParentTargetRuntime,
    source_basis_matrix: Matrix,
    debug_context: DebugContext,
    debug_frame: float,
) -> ResolvedExternalParentBakePose:
    target_armature_object = target_runtime.armature_object
    target_pose_bone = target_runtime.target_pose_bone
    target_world_matrix = target_armature_object.matrix_world @ target_pose_bone.matrix
    resolved_pose = resolve_external_parent_bake_pose(
        source_armature_world=_matrix_to_rows(source_armature_object.matrix_world),
        target_world_matrix=_matrix_to_rows(target_world_matrix),
        target_bone_rest_matrix=_matrix_to_rows(target_runtime.target_rest_matrix_local),
        source_bone_rest_matrix=_matrix_to_rows(runtime.source_rest_matrix_local),
        source_basis_matrix=_matrix_to_rows(source_basis_matrix),
    )
    if debug_context.should_log(runtime.source_bone_name_j, debug_frame):
        _debug_log(
            debug_context,
            runtime.source_bone_name_j,
            debug_frame,
            "external-parent-pose",
            [
                f'target_pose_bone="{target_pose_bone.name}" target_root="{target_armature_object.parent.name if target_armature_object.parent else ""}"',
                f"target_world_matrix={_format_matrix(target_world_matrix)}",
                f"target_rest_matrix_local={_format_matrix(target_runtime.target_rest_matrix_local)}",
                f"target_rest_rotation_inverse={_format_quaternion(resolved_pose.target_rest_rotation_inverse)}",
                f"external_parent_pose={_format_matrix(_rows_to_matrix(resolved_pose.external_parent_world_matrix))}",
                f"source_rest_matrix_local={_format_matrix(runtime.source_rest_matrix_local)}",
                f"source_rest_rotation_only={_format_matrix(_rows_to_matrix(resolved_pose.source_rest_rotation_only_matrix))}",
                f"source_basis_no_rest={_format_matrix(source_basis_matrix)}",
                f"source_world_matrix={_format_matrix(_rows_to_matrix(resolved_pose.source_world_matrix))}",
                f"source_armature_pose={_format_matrix(_rows_to_matrix(resolved_pose.source_armature_matrix))}",
            ],
        )
    return resolved_pose


def _safe_quaternion(values: Quaternion | tuple[float, float, float, float]) -> Quaternion:
    quaternion = values.copy() if isinstance(values, Quaternion) else Quaternion(values)
    if quaternion.magnitude == 0.0:
        quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
    try:
        quaternion.normalize()
    except Exception:
        quaternion = Quaternion((1.0, 0.0, 0.0, 0.0))
    return quaternion


def _safe_inverted(matrix: Matrix) -> Matrix:
    try:
        return matrix.inverted()
    except Exception:
        return Matrix.Identity(4)


def _matrix_to_rows(matrix: Matrix) -> tuple[tuple[float, float, float, float], ...]:
    return tuple(
        tuple(float(matrix[row][column]) for column in range(4))
        for row in range(4)
    )


def _rows_to_matrix(rows: tuple[tuple[float, float, float, float], ...]) -> Matrix:
    return Matrix(rows)


def _set_scene_frame(scene: bpy.types.Scene, frame: float) -> None:
    whole_frame = floor(frame)
    subframe = float(frame) - float(whole_frame)
    scene.frame_set(whole_frame, subframe=subframe)
    bpy.context.view_layer.update()


def _read_debug_context() -> DebugContext:
    preferences = getattr(bpy.context, "preferences", None)
    addons = getattr(preferences, "addons", None)
    addon = addons.get(__package__) if addons is not None else None
    addon_preferences = getattr(addon, "preferences", None) if addon is not None else None
    if addon_preferences is None:
        return DebugContext()
    return DebugContext(
        enabled=bool(getattr(addon_preferences, "debug_bake_logging", False)),
        source_bone_name_j=str(getattr(addon_preferences, "debug_source_bone_name_j", "")).strip(),
        frame_start=int(getattr(addon_preferences, "debug_frame_start", 0)),
        frame_end=int(getattr(addon_preferences, "debug_frame_end", -1)),
    )


def _debug_log(
    debug_context: DebugContext,
    source_bone_name_j: str,
    frame: float | None,
    stage: str,
    lines: list[str],
) -> None:
    if not debug_context.enabled:
        return
    if source_bone_name_j != debug_context.source_bone_name_j:
        return
    if frame is not None and not debug_context.matches_frame(frame):
        return
    frame_label = "setup" if frame is None else f"{frame:g}"
    print(f"[mmd_ext_parent_baker][debug][source={source_bone_name_j}][frame={frame_label}][stage={stage}]")
    for line in lines:
        print(f"  {line}")


def _format_vector(values: Vector | tuple[float, float, float]) -> str:
    vector = values.copy() if isinstance(values, Vector) else Vector(values)
    return f"({float(vector.x):.6f}, {float(vector.y):.6f}, {float(vector.z):.6f})"


def _format_quaternion(values: Quaternion | tuple[float, float, float, float]) -> str:
    quaternion = _safe_quaternion(values)
    try:
        euler = quaternion.to_euler("XYZ")
    except Exception:
        euler = quaternion.to_euler()
    return (
        f'quat=({float(quaternion.w):.6f}, {float(quaternion.x):.6f}, '
        f'{float(quaternion.y):.6f}, {float(quaternion.z):.6f}) '
        f'euler_xyz=({float(euler.x):.6f}, {float(euler.y):.6f}, {float(euler.z):.6f})'
    )


def _format_matrix(matrix: Matrix) -> str:
    rows = " ".join(
        "[" + ", ".join(f"{float(matrix[row][column]):.6f}" for column in range(4)) + "]"
        for row in range(4)
    )
    return f"rows={rows} loc={_format_vector(matrix.to_translation())} {_format_quaternion(matrix.to_quaternion())}"
