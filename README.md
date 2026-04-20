# MMD External Parent Baker

MMD External Parent Baker is a Blender add-on for baking MMD-style external parent behavior into a normal Blender Action. It is designed for scenes imported with `mmd_tools` and is typically used together with the companion web editor:

[mmd_ext_parent_baker_web](https://github.com/qwqsleep-maker/mmd_ext_parent_baker_web)

## 中文说明

### 功能

这个 add-on 在 Blender 内启动一个本地 HTTP 服务，供 Web UI 查询场景模型、编辑 external parent 轨道，并把结果烘焙成原 source armature 上可直接播放的 Action。

当前输出模式是：

```text
output_mode = original_armature_visual
```

也就是说，烘焙结果会写回原模型骨架，不创建 helper 骨架，不修改 rest pose，不添加 constraint 或 driver。

### 环境要求

- Blender 4.0+
- 已安装并使用 `mmd_tools` 导入 MMD/PMX/VMD 场景
- 可选：配套 Web UI 仓库 `mmd_ext_parent_baker_web`

### 安装

把整个 `mmd_ext_parent_baker` 目录复制到 Blender add-ons 目录，例如：

```powershell
Copy-Item -Recurse "E:\blender code\mmd_ext_parent_baker" "$env:APPDATA\Blender Foundation\Blender\4.5\scripts\addons\mmd_ext_parent_baker"
```

然后在 Blender 中启用：

1. 打开 `Edit > Preferences > Add-ons`
2. 搜索 `MMD External Parent Baker`
3. 勾选启用 add-on

启用后，3D View 右侧 N 面板会出现 `MMD Ext Parent` 标签页。

### 启动服务

默认服务地址：

```text
http://127.0.0.1:37601
```

启动方式：

1. 在 Blender 中打开包含 mmd_tools 模型的场景
2. 打开 3D View 右侧 `MMD Ext Parent` 面板
3. 确认 `HTTP Service` 为 Running
4. 如果没有自动启动，点击 `Start` 或 `Restart`

也可以在 Add-on Preferences 中调整：

- `Host`
- `Port`
- `Auto Start Server`
- `Enable Bake Debug Logging`
- `Debug Source Bone Name (MMD)`
- `Debug Frame Start / End`

### Web UI 使用流程

推荐使用配套前端：

[mmd_ext_parent_baker_web](https://github.com/qwqsleep-maker/mmd_ext_parent_baker_web)

基本流程：

1. 在 Blender 中启动本 add-on 的 HTTP 服务
2. 启动 Web UI
3. 点击 `Refresh Scene`
4. 选择 Source Model 和 Source Action
5. 添加 track，选择 source bone
6. 添加 keyframe，选择 target root 和 target bone
7. 点击 `Bake External Parent`
8. 在 Blender 中播放生成的 output Action

### API

服务提供两个接口：

```http
GET /scene
```

返回当前 Blender 场景中的 MMD 模型、骨骼和帧范围。

```http
POST /bake/external-parent
```

提交 external-parent bake 请求。请求中的帧号必须是 Blender 真实帧；如果使用 Web UI 的 MMD Frames 模式，Web UI 会在提交前自动转换。

### 算法语义

核心 external parent 计算方式：

1. 取 target 当前真实世界矩阵：

```text
target_world = target_armature_world @ target_pose_matrix
```

2. 取 target bone 的 absolute rest rotation，并从 target 当前旋转中剥掉：

```text
external_parent_rotation = target_world_rotation * inverse(target_absolute_rest_rotation)
```

3. 保留 target 当前 world location，与剥离后的 rotation 组合成 external parent pose。

4. 再乘 source bone 的 absolute rest rotation-only 和 source 当前 pose basis：

```text
source_world = external_parent_pose @ source_absolute_rest_rotation_only @ source_basis
```

5. 转回 source armature space，并分解为原 Blender 骨架可播放的 local channels。

这个策略不修改原模型 rest pose，也不会把 target 的 Blender rest 方向误当成 MMD pose rotation。

### Debug

如果 bake 结果不符合预期，可以在 Add-on Preferences 中开启：

- `Enable Bake Debug Logging`
- `Debug Source Bone Name (MMD)`
- `Debug Frame Start`
- `Debug Frame End`

控制台会输出：

- `target_world_matrix`
- `target_rest_matrix_local`
- `target_rest_rotation_inverse`
- `external_parent_pose`
- `source_rest_matrix_local`
- `source_rest_rotation_only`
- `source_basis_no_rest`
- `source_world_matrix`
- `source_armature_pose`
- `blender_local_location / blender_local_rotation`
- `blender_replayed_pose / blender_replay_delta`

`blender_replay_delta` 接近 identity 时，表示写回原骨架后的播放结果与语义目标一致。

## English

### What It Does

This add-on starts a local HTTP service inside Blender. A companion web UI can query the current mmd_tools scene, edit external-parent tracks, and bake the result into a normal playable Action on the original source armature.

The current output mode is:

```text
output_mode = original_armature_visual
```

The bake writes to the original armature. It does not modify rest pose, create helper rigs, constraints, or drivers.

### Requirements

- Blender 4.0+
- `mmd_tools` scene import workflow
- Optional companion web UI: [mmd_ext_parent_baker_web](https://github.com/qwqsleep-maker/mmd_ext_parent_baker_web)

### Installation

Copy the full `mmd_ext_parent_baker` folder into Blender's add-ons directory, for example:

```powershell
Copy-Item -Recurse "E:\blender code\mmd_ext_parent_baker" "$env:APPDATA\Blender Foundation\Blender\4.5\scripts\addons\mmd_ext_parent_baker"
```

Then enable it in Blender:

1. Open `Edit > Preferences > Add-ons`
2. Search for `MMD External Parent Baker`
3. Enable the add-on

The `MMD Ext Parent` panel appears in the 3D View sidebar.

### Start The Service

Default service URL:

```text
http://127.0.0.1:37601
```

Use the `MMD Ext Parent` panel to start, stop, or restart the local HTTP service. The service must be running before the web UI can connect.

### Companion Web UI

Use the companion project for editing and submitting bake requests:

[mmd_ext_parent_baker_web](https://github.com/qwqsleep-maker/mmd_ext_parent_baker_web)

Basic workflow:

1. Start the add-on HTTP service in Blender
2. Open the web UI
3. Click `Refresh Scene`
4. Select a source model and source action
5. Add an external-parent track for a source bone
6. Add keyframes and select target root/bone pairs
7. Click `Bake External Parent`
8. Play the generated output Action in Blender

### API

```http
GET /scene
```

Returns scene frame range, MMD models, armatures, actions, and bones.

```http
POST /bake/external-parent
```

Bakes external-parent tracks. Submitted frame numbers are Blender frame numbers. If you use MMD frame mode in the web UI, the UI converts them before sending the request.

### Algorithm

The bake uses the target's current world matrix, strips only the target bone's absolute rest rotation, then applies the source bone's absolute rest rotation-only and current source basis:

```text
external_parent_rotation = target_world_rotation * inverse(target_absolute_rest_rotation)
source_world = external_parent_pose @ source_absolute_rest_rotation_only @ source_basis
```

The result is converted back to source armature space and decomposed into Blender local channels that can be played directly on the original armature.

### Debugging

Enable bake debug logging in Add-on Preferences to inspect target/source matrices and replay deltas for a specific source bone and frame range.
