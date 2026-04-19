from __future__ import annotations

from dataclasses import dataclass
from math import sqrt
from typing import Mapping


Vector3 = tuple[float, float, float]
Quaternion4 = tuple[float, float, float, float]
Matrix4 = tuple[
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
    tuple[float, float, float, float],
]
LocalChannels = tuple[Vector3, Quaternion4]


@dataclass(frozen=True, slots=True)
class ResolvedExternalParentState:
    apply_location: bool
    apply_rotation: bool
    target_location: Vector3
    target_rotation: Quaternion4
    target_source_armature_matrix: Matrix4


def apply_cut_sample(
    local_channels: Mapping[str, LocalChannels],
    pose_bone_name: str,
    sampled_channels: LocalChannels,
) -> dict[str, LocalChannels]:
    adjusted = dict(local_channels)
    adjusted[pose_bone_name] = sampled_channels
    return adjusted


def resolve_external_parent_state(
    source_armature_world: Matrix4,
    target_armature_world: Matrix4,
    target_world_matrix: Matrix4,
    target_rest_world_matrix: Matrix4,
    *,
    apply_location: bool = True,
    apply_rotation: bool = True,
) -> ResolvedExternalParentState:
    target_rest_in_armature = multiply_matrices(
        invert_rigid_matrix(target_armature_world),
        target_rest_world_matrix,
    )
    target_rest_rotation_only = _rotation_only_matrix(target_rest_in_armature)
    g_world_matrix = multiply_matrices(
        target_world_matrix,
        invert_rigid_matrix(target_rest_rotation_only),
    )
    target_source_armature_matrix = multiply_matrices(
        invert_rigid_matrix(source_armature_world),
        g_world_matrix,
    )
    return ResolvedExternalParentState(
        apply_location=apply_location,
        apply_rotation=apply_rotation,
        target_location=matrix_to_translation(target_source_armature_matrix),
        target_rotation=normalize_quaternion(matrix_to_quaternion(target_source_armature_matrix)),
        target_source_armature_matrix=target_source_armature_matrix,
    )


def _rotation_only_matrix(matrix: Matrix4) -> Matrix4:
    return compose_matrix((0.0, 0.0, 0.0), matrix_to_quaternion(matrix))


def build_semantic_parent_pose(
    parent_pose: Matrix4,
    resolved_state: ResolvedExternalParentState | None,
) -> Matrix4:
    if resolved_state is None:
        return parent_pose
    semantic_location = matrix_to_translation(parent_pose)
    semantic_rotation = normalize_quaternion(matrix_to_quaternion(parent_pose))
    if resolved_state.apply_location:
        semantic_location = resolved_state.target_location
    if resolved_state.apply_rotation:
        semantic_rotation = resolved_state.target_rotation
    return compose_matrix(semantic_location, semantic_rotation)


def build_semantic_pose(
    *,
    parent_pose: Matrix4,
    rest_local: Matrix4,
    local_location: Vector3,
    local_rotation: Quaternion4,
    resolved_state: ResolvedExternalParentState | None,
) -> Matrix4:
    semantic_parent_pose = build_semantic_parent_pose(parent_pose, resolved_state)
    local_anim = compose_matrix(local_location, local_rotation)
    return multiply_matrices(semantic_parent_pose, multiply_matrices(rest_local, local_anim))


def decompose_local_channels(
    *,
    parent_pose: Matrix4,
    rest_local: Matrix4,
    absolute_pose: Matrix4,
) -> LocalChannels:
    basis = multiply_matrices(
        invert_rigid_matrix(rest_local),
        multiply_matrices(invert_rigid_matrix(parent_pose), absolute_pose),
    )
    return (
        matrix_to_translation(basis),
        normalize_quaternion(matrix_to_quaternion(basis)),
    )


def compose_matrix(location: Vector3, rotation: Quaternion4) -> Matrix4:
    rotation_matrix = quaternion_to_matrix(normalize_quaternion(rotation))
    return (
        (rotation_matrix[0][0], rotation_matrix[0][1], rotation_matrix[0][2], float(location[0])),
        (rotation_matrix[1][0], rotation_matrix[1][1], rotation_matrix[1][2], float(location[1])),
        (rotation_matrix[2][0], rotation_matrix[2][1], rotation_matrix[2][2], float(location[2])),
        (0.0, 0.0, 0.0, 1.0),
    )


def multiply_matrices(left: Matrix4, right: Matrix4) -> Matrix4:
    rows: list[tuple[float, float, float, float]] = []
    for row in range(4):
        values: list[float] = []
        for column in range(4):
            value = 0.0
            for index in range(4):
                value += float(left[row][index]) * float(right[index][column])
            values.append(value)
        rows.append((values[0], values[1], values[2], values[3]))
    return (rows[0], rows[1], rows[2], rows[3])


def invert_rigid_matrix(matrix: Matrix4) -> Matrix4:
    rotation = (
        (float(matrix[0][0]), float(matrix[0][1]), float(matrix[0][2])),
        (float(matrix[1][0]), float(matrix[1][1]), float(matrix[1][2])),
        (float(matrix[2][0]), float(matrix[2][1]), float(matrix[2][2])),
    )
    translation = matrix_to_translation(matrix)
    rotation_transpose = (
        (rotation[0][0], rotation[1][0], rotation[2][0]),
        (rotation[0][1], rotation[1][1], rotation[2][1]),
        (rotation[0][2], rotation[1][2], rotation[2][2]),
    )
    inverted_translation = (
        -(rotation_transpose[0][0] * translation[0] + rotation_transpose[0][1] * translation[1] + rotation_transpose[0][2] * translation[2]),
        -(rotation_transpose[1][0] * translation[0] + rotation_transpose[1][1] * translation[1] + rotation_transpose[1][2] * translation[2]),
        -(rotation_transpose[2][0] * translation[0] + rotation_transpose[2][1] * translation[1] + rotation_transpose[2][2] * translation[2]),
    )
    return (
        (rotation_transpose[0][0], rotation_transpose[0][1], rotation_transpose[0][2], inverted_translation[0]),
        (rotation_transpose[1][0], rotation_transpose[1][1], rotation_transpose[1][2], inverted_translation[1]),
        (rotation_transpose[2][0], rotation_transpose[2][1], rotation_transpose[2][2], inverted_translation[2]),
        (0.0, 0.0, 0.0, 1.0),
    )


def matrix_to_translation(matrix: Matrix4) -> Vector3:
    return (float(matrix[0][3]), float(matrix[1][3]), float(matrix[2][3]))


def matrix_to_quaternion(matrix: Matrix4) -> Quaternion4:
    m00 = float(matrix[0][0])
    m01 = float(matrix[0][1])
    m02 = float(matrix[0][2])
    m10 = float(matrix[1][0])
    m11 = float(matrix[1][1])
    m12 = float(matrix[1][2])
    m20 = float(matrix[2][0])
    m21 = float(matrix[2][1])
    m22 = float(matrix[2][2])
    trace = m00 + m11 + m22
    if trace > 0.0:
        scale = sqrt(trace + 1.0) * 2.0
        w = 0.25 * scale
        x = (m21 - m12) / scale
        y = (m02 - m20) / scale
        z = (m10 - m01) / scale
    elif m00 > m11 and m00 > m22:
        scale = sqrt(1.0 + m00 - m11 - m22) * 2.0
        w = (m21 - m12) / scale
        x = 0.25 * scale
        y = (m01 + m10) / scale
        z = (m02 + m20) / scale
    elif m11 > m22:
        scale = sqrt(1.0 + m11 - m00 - m22) * 2.0
        w = (m02 - m20) / scale
        x = (m01 + m10) / scale
        y = 0.25 * scale
        z = (m12 + m21) / scale
    else:
        scale = sqrt(1.0 + m22 - m00 - m11) * 2.0
        w = (m10 - m01) / scale
        x = (m02 + m20) / scale
        y = (m12 + m21) / scale
        z = 0.25 * scale
    return normalize_quaternion((w, x, y, z))


def quaternion_to_matrix(quaternion: Quaternion4) -> tuple[tuple[float, float, float], tuple[float, float, float], tuple[float, float, float]]:
    w, x, y, z = normalize_quaternion(quaternion)
    xx = x * x
    yy = y * y
    zz = z * z
    xy = x * y
    xz = x * z
    yz = y * z
    wx = w * x
    wy = w * y
    wz = w * z
    return (
        (1.0 - 2.0 * (yy + zz), 2.0 * (xy - wz), 2.0 * (xz + wy)),
        (2.0 * (xy + wz), 1.0 - 2.0 * (xx + zz), 2.0 * (yz - wx)),
        (2.0 * (xz - wy), 2.0 * (yz + wx), 1.0 - 2.0 * (xx + yy)),
    )


def normalize_quaternion(quaternion: Quaternion4) -> Quaternion4:
    w, x, y, z = (float(quaternion[0]), float(quaternion[1]), float(quaternion[2]), float(quaternion[3]))
    magnitude = sqrt(w * w + x * x + y * y + z * z)
    if magnitude == 0.0:
        return (1.0, 0.0, 0.0, 0.0)
    return (w / magnitude, x / magnitude, y / magnitude, z / magnitude)


def invert_quaternion(quaternion: Quaternion4) -> Quaternion4:
    w, x, y, z = normalize_quaternion(quaternion)
    return (w, -x, -y, -z)


def multiply_quaternions(left: Quaternion4, right: Quaternion4) -> Quaternion4:
    lw, lx, ly, lz = normalize_quaternion(left)
    rw, rx, ry, rz = normalize_quaternion(right)
    return normalize_quaternion(
        (
            lw * rw - lx * rx - ly * ry - lz * rz,
            lw * rx + lx * rw + ly * rz - lz * ry,
            lw * ry - lx * rz + ly * rw + lz * rx,
            lw * rz + lx * ry - ly * rx + lz * rw,
        )
    )
