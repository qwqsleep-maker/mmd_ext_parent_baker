# MMD External Parent Baker

MMD External Parent Baker is a Blender add-on that bakes MMD-style external parent behavior into a normal playable Blender Action on the original armature.

The companion web editor source lives here:

[mmd_ext_parent_baker_web](https://github.com/qwqsleep-maker/mmd_ext_parent_baker_web)

## 中文说明

### 项目定位

这个仓库现在是 **add-on 源码仓库**，不是默认的最终安装包。

最终用户推荐的安装方式是：

- 到 GitHub Releases 下载打包好的 add-on zip
- 在 Blender 中安装 release 资产

源码仓库本身不再承诺“克隆后直接就是完整可安装包”。发布时需要先构建 web 前端，再把构建产物一起打进 release zip。

### 功能概览

这个 add-on 会在 Blender 内启动两个本地 HTTP 服务：

- API 服务：提供场景查询和 external parent 烘焙接口
- Web UI 服务：提供打包后的前端页面

当前输出模式是：

```text
output_mode = original_armature_visual
```

也就是说，烘焙结果会直接写回原始 source armature 上的普通 Blender Action，不改 rest pose，不创建 helper rig，不添加 constraint 或 driver。

### 当前端口行为

- API 端口不是固定死的
- add-on 会优先尝试 `127.0.0.1:37601`
- 如果该端口已经被别的 Blender 实例占用，就自动递增到下一个空闲端口
- Web UI 服务使用独立的动态端口
- `Open Web UI` 和 `Copy Web UI URL` 会生成带 `?apiBaseUrl=...` 的完整启动地址

这意味着你可以同时开启多个 Blender，每个实例都会有自己的 API URL 和 Web UI URL。

### 环境要求

- Blender 4.0+
- 使用 `mmd_tools` 导入 MMD/PMX/VMD 场景

### 给最终用户的安装方式

推荐方式：

1. 打开本仓库的 GitHub Releases 页面
2. 下载打包好的 add-on zip
3. 在 Blender 中安装该 zip

不要把源码仓库当前工作目录直接当成最终发布包。

### 给开发者的本地联调方式

如果你是开发者，源码 checkout 里默认可能没有 `web_dist/`。这是正常的。

本地联调流程：

1. 在 `mmd_ext_parent_baker_web` 中运行 `npm install`
2. 运行 `npm test`
3. 运行 `npm run build`
4. 把 `mmd_ext_parent_baker_web/dist/` 手工复制到 `mmd_ext_parent_baker/web_dist/`
5. 再启动 Blender add-on 做本地联调

注意：

- `web_dist/` 是发布构建产物，不再进入 add-on 仓库版本管理
- 如果源码 checkout 下缺少 `web_dist/`，API 服务仍可启动，但 Web UI 会显示 bundle 缺失

### 面板说明

面板会显示：

- `API Service`
- `Web UI`
- `API Port Search Starts At: 37601`

其中：

- `API Service` 显示当前实例真实绑定的 API 地址
- `Web UI` 显示当前实例完整的启动 URL
- `API Port Search Starts At: 37601` 只是起始探测端口，不是实际运行端口

可用按钮：

- `Start`
- `Stop`
- `Restart`
- `Open Web UI`
- `Copy Web UI URL`

### 多 Blender 实例

如果同时打开多个 Blender：

- 第一个实例通常会拿到 `37601`
- 第二个实例会自动拿到 `37602` 或之后的空闲端口
- 必须通过各自 Blender 面板里的 `Open Web UI` 打开页面

### HTTP API

```http
GET /scene
```

返回当前 Blender 场景中的模型、骨架、动作、骨骼和帧范围。

```http
POST /bake/external-parent
```

提交 external parent 烘焙请求。

请求中的帧号必须是 Blender 真实帧号。如果在 Web UI 中启用了 `MMD Frames` 模式，前端会在提交前自动转换成 Blender 帧号。

### Release 构建方式

发布流程由 add-on 仓库中的 GitHub Actions 完成：

1. 读取 `web_bundle.toml`
2. 按锁定的 commit/tag 拉取 `mmd_ext_parent_baker_web`
3. 运行 `npm ci`、`npm test`、`npm run build`
4. 把构建出的 `dist/` 放入 add-on staging 目录的 `web_dist/`
5. 打出 Blender 可安装 zip
6. 上传到 GitHub Release 资产

因此，release 中包含完整的 Web UI，而源码仓库默认不跟踪 `web_dist/`。

### 算法语义

当前 external parent 解析使用这条主路径：

1. 取 target 当前真实世界矩阵
2. 剥离 target 骨骼的 absolute rest rotation
3. 保留 target 当前 world location
4. 乘 source 骨骼的 absolute rest rotation-only
5. 再乘 source 当前 pose basis
6. 最后分解回 Blender 原骨架可直接播放的 local channels

核心形式是：

```text
external_parent_rotation = target_world_rotation * inverse(target_absolute_rest_rotation)
source_world = external_parent_pose @ source_absolute_rest_rotation_only @ source_basis
```

### Debug

可以在 Add-on Preferences 中启用：

- `Enable Bake Debug Logging`
- `Debug Source Bone Name (MMD)`
- `Debug Frame Start`
- `Debug Frame End`

用于输出矩阵、局部通道和 replay delta，定位烘焙问题。

## English

### Repository Role

This repository is now the **add-on source repository**, not the default end-user installation artifact.

The recommended install path for end users is:

- download the packaged add-on zip from GitHub Releases
- install that release asset in Blender

The source repository no longer promises that cloning it gives you a complete installable package. The release process builds the web frontend first and then bundles it into the release zip.

### Overview

The add-on runs two local HTTP services inside Blender:

- API service: scene queries and external-parent bake requests
- Web UI service: serves the bundled frontend

The bake output mode is:

```text
output_mode = original_armature_visual
```

The result is written directly back to the original source armature as a normal Blender Action. Rest pose is not modified, and no helper rigs, constraints, or drivers are created.

### Current Port Behavior

- The API port is not fixed
- The add-on tries `127.0.0.1:37601` first
- If that port is already owned by another Blender instance, it automatically advances to the next free port
- The Web UI service uses its own dynamic port
- `Open Web UI` and `Copy Web UI URL` generate a full launch URL with `?apiBaseUrl=...`

This allows multiple Blender instances to run at the same time without assuming a shared API port.

### Requirements

- Blender 4.0+
- `mmd_tools` workflow for MMD/PMX/VMD scenes

### End-User Installation

Recommended path:

1. Open this repository's GitHub Releases page
2. Download the packaged add-on zip
3. Install that zip in Blender

Do not treat the live source checkout as the final release package.

### Local Development Workflow

For local development, the source checkout may intentionally not include `web_dist/`. That is expected.

Local integration flow:

1. Run `npm install` in `mmd_ext_parent_baker_web`
2. Run `npm test`
3. Run `npm run build`
4. Copy `mmd_ext_parent_baker_web/dist/` into `mmd_ext_parent_baker/web_dist/`
5. Start the Blender add-on for local integration testing

Notes:

- `web_dist/` is a release build artifact and is no longer versioned in the add-on repo
- if a source checkout has no `web_dist/`, the API service still works, but the Web UI is correctly reported as missing

### Panel Behavior

The panel shows:

- `API Service`
- `Web UI`
- `API Port Search Starts At: 37601`

Meaning:

- `API Service` is the real API address for the current Blender instance
- `Web UI` is the full launch URL for the current Blender instance
- `API Port Search Starts At: 37601` is only the search starting point, not the actual bound port

Available buttons:

- `Start`
- `Stop`
- `Restart`
- `Open Web UI`
- `Copy Web UI URL`

### Multiple Blender Instances

If you open multiple Blender instances:

- the first one will usually get `37601`
- the second one will usually get `37602` or the next free port
- each UI must be opened from its own Blender panel

### HTTP API

```http
GET /scene
```

Returns models, armatures, actions, bones, and frame range from the current Blender scene.

```http
POST /bake/external-parent
```

Submits an external-parent bake request.

Frame numbers in the request must be real Blender frame numbers. If the Web UI is in `MMD Frames` mode, it converts them before sending the request.

### Release Build

Release packaging is handled by GitHub Actions in the add-on repository:

1. Read `web_bundle.toml`
2. Check out `mmd_ext_parent_baker_web` at the pinned commit/tag
3. Run `npm ci`, `npm test`, and `npm run build`
4. Copy the built `dist/` into the add-on staging directory as `web_dist/`
5. Generate a Blender-installable zip
6. Upload it to GitHub Release assets

So the release artifact includes the full bundled UI, while the source repo does not need to version `web_dist/`.

### Algorithm

The current external-parent path is:

1. Read the target's real current world matrix
2. Strip only the target bone's absolute rest rotation
3. Keep the target's current world location
4. Apply the source bone's absolute rest rotation-only
5. Apply the current source pose basis
6. Decompose the result back into Blender-playable local channels on the original rig

Core form:

```text
external_parent_rotation = target_world_rotation * inverse(target_absolute_rest_rotation)
source_world = external_parent_pose @ source_absolute_rest_rotation_only @ source_basis
```

### Debugging

You can enable:

- `Enable Bake Debug Logging`
- `Debug Source Bone Name (MMD)`
- `Debug Frame Start`
- `Debug Frame End`

in Add-on Preferences to inspect matrices, local channels, and replay deltas during baking.
