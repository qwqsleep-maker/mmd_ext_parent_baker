from __future__ import annotations

import bpy

from .service import DEFAULT_PREFERRED_API_PORT, get_service_status, start_service, stop_service


DEFAULT_HOST = "127.0.0.1"


class MMD_EXT_PARENT_BAKER_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    host: bpy.props.StringProperty(
        name="Host",
        default=DEFAULT_HOST,
    )
    auto_start: bpy.props.BoolProperty(
        name="Auto Start Server",
        default=True,
    )
    debug_bake_logging: bpy.props.BoolProperty(
        name="Enable Bake Debug Logging",
        default=False,
    )
    debug_source_bone_name_j: bpy.props.StringProperty(
        name="Debug Source Bone Name (MMD)",
        default="",
    )
    debug_frame_start: bpy.props.IntProperty(
        name="Debug Frame Start",
        default=1,
    )
    debug_frame_end: bpy.props.IntProperty(
        name="Debug Frame End",
        default=1,
    )

    def draw(self, context: bpy.types.Context) -> None:
        _ = context
        layout = self.layout
        layout.prop(self, "host")
        layout.prop(self, "auto_start")
        layout.label(text=f"API Port Search Starts At: {DEFAULT_PREFERRED_API_PORT}")
        debug_box = layout.box()
        debug_box.label(text="Bake Debug Logging")
        debug_box.prop(self, "debug_bake_logging")
        debug_box.prop(self, "debug_source_bone_name_j")
        debug_row = debug_box.row(align=True)
        debug_row.prop(self, "debug_frame_start")
        debug_row.prop(self, "debug_frame_end")


class MMD_EXT_PARENT_BAKER_OT_start_service(bpy.types.Operator):
    bl_idname = "mmd_ext_parent_baker.start_service"
    bl_label = "Start HTTP Service"
    bl_description = "Start the local HTTP service for external-parent baking"

    def execute(self, context: bpy.types.Context) -> set[str]:
        host, _auto_start = _get_preference_values(context)
        try:
            start_service(host)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f'Service started at {get_service_status().get("api_base_url")}')
        return {"FINISHED"}


class MMD_EXT_PARENT_BAKER_OT_stop_service(bpy.types.Operator):
    bl_idname = "mmd_ext_parent_baker.stop_service"
    bl_label = "Stop HTTP Service"
    bl_description = "Stop the local HTTP service for external-parent baking"

    def execute(self, context: bpy.types.Context) -> set[str]:
        _ = context
        stop_service()
        self.report({"INFO"}, "Service stopped")
        return {"FINISHED"}


class MMD_EXT_PARENT_BAKER_OT_open_web_ui(bpy.types.Operator):
    bl_idname = "mmd_ext_parent_baker.open_web_ui"
    bl_label = "Open Web UI"
    bl_description = "Open the bundled web editor in your browser"

    def execute(self, context: bpy.types.Context) -> set[str]:
        _ = context
        status = get_service_status()
        ui_launch_url = status.get("ui_launch_url")
        if not status.get("ui_running") or not isinstance(ui_launch_url, str):
            self.report({"ERROR"}, status.get("ui_error") or "Web UI service is not running")
            return {"CANCELLED"}
        bpy.ops.wm.url_open(url=ui_launch_url)
        return {"FINISHED"}


class MMD_EXT_PARENT_BAKER_OT_copy_web_ui_url(bpy.types.Operator):
    bl_idname = "mmd_ext_parent_baker.copy_web_ui_url"
    bl_label = "Copy Web UI URL"
    bl_description = "Copy the bundled web editor URL"

    def execute(self, context: bpy.types.Context) -> set[str]:
        status = get_service_status()
        ui_launch_url = status.get("ui_launch_url")
        if not status.get("ui_running") or not isinstance(ui_launch_url, str):
            self.report({"ERROR"}, status.get("ui_error") or "Web UI service is not running")
            return {"CANCELLED"}
        context.window_manager.clipboard = ui_launch_url
        self.report({"INFO"}, "Web UI URL copied")
        return {"FINISHED"}


class MMD_EXT_PARENT_BAKER_OT_restart_service(bpy.types.Operator):
    bl_idname = "mmd_ext_parent_baker.restart_service"
    bl_label = "Restart HTTP Service"
    bl_description = "Restart the local HTTP service for external-parent baking"

    def execute(self, context: bpy.types.Context) -> set[str]:
        host, _auto_start = _get_preference_values(context)
        try:
            stop_service()
            start_service(host)
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f'Service restarted at {get_service_status().get("api_base_url")}')
        return {"FINISHED"}


class MMD_EXT_PARENT_BAKER_PT_panel(bpy.types.Panel):
    bl_label = "MMD Ext Parent"
    bl_idname = "MMD_EXT_PARENT_BAKER_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD Ext Parent"

    def draw(self, context: bpy.types.Context) -> None:
        preferences = _get_preferences(context)
        host, _auto_start = _get_preference_values(context)
        status = get_service_status()

        layout = self.layout
        layout.label(text="API Service")
        if status["api_running"]:
            layout.label(text=f'Running at {status["api_base_url"]}')
        else:
            layout.label(text="Stopped")

        layout.separator()
        layout.label(text="Web UI")
        if status["ui_running"]:
            layout.label(text=f'Launch URL: {status["ui_launch_url"]}')
        elif status["ui_error"]:
            layout.label(text=str(status["ui_error"]))
        else:
            layout.label(text="Stopped")

        if preferences is not None:
            layout.prop(preferences, "host")
            layout.prop(preferences, "auto_start")
        else:
            layout.label(text=f"Host: {host}")
        layout.label(text=f"API Port Search Starts At: {DEFAULT_PREFERRED_API_PORT}")
        row = layout.row(align=True)
        row.operator(MMD_EXT_PARENT_BAKER_OT_start_service.bl_idname, text="Start")
        row.operator(MMD_EXT_PARENT_BAKER_OT_stop_service.bl_idname, text="Stop")
        layout.operator(MMD_EXT_PARENT_BAKER_OT_restart_service.bl_idname, text="Restart")
        web_row = layout.row(align=True)
        web_row.enabled = bool(status["ui_running"])
        web_row.operator(MMD_EXT_PARENT_BAKER_OT_open_web_ui.bl_idname, text="Open Web UI")
        web_row.operator(MMD_EXT_PARENT_BAKER_OT_copy_web_ui_url.bl_idname, text="Copy Web UI URL")


CLASSES = (
    MMD_EXT_PARENT_BAKER_Preferences,
    MMD_EXT_PARENT_BAKER_OT_start_service,
    MMD_EXT_PARENT_BAKER_OT_stop_service,
    MMD_EXT_PARENT_BAKER_OT_open_web_ui,
    MMD_EXT_PARENT_BAKER_OT_copy_web_ui_url,
    MMD_EXT_PARENT_BAKER_OT_restart_service,
    MMD_EXT_PARENT_BAKER_PT_panel,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    host, auto_start = _get_preference_values(bpy.context)
    if auto_start:
        try:
            start_service(host)
        except Exception:
            pass


def unregister() -> None:
    stop_service()
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)


def _get_preferences(context: bpy.types.Context) -> MMD_EXT_PARENT_BAKER_Preferences | None:
    preferences = getattr(context, "preferences", None)
    addons = getattr(preferences, "addons", None)
    if addons is None:
        return None
    addon = addons.get(__package__)
    if addon is None:
        return None
    return getattr(addon, "preferences", None)


def _get_preference_values(context: bpy.types.Context) -> tuple[str, bool]:
    preferences = _get_preferences(context)
    if preferences is None:
        return DEFAULT_HOST, True
    return str(preferences.host), bool(preferences.auto_start)
