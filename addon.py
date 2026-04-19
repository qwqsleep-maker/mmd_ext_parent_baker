from __future__ import annotations

import bpy

from .service import get_service_status, start_service, stop_service


DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 37601


class MMD_EXT_PARENT_BAKER_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__

    host: bpy.props.StringProperty(
        name="Host",
        default=DEFAULT_HOST,
    )
    port: bpy.props.IntProperty(
        name="Port",
        default=DEFAULT_PORT,
        min=1,
        max=65535,
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
        layout.prop(self, "port")
        layout.prop(self, "auto_start")
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
        host, port, _auto_start = _get_preference_values(context)
        try:
            start_service(host, int(port))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Service started at http://{host}:{port}")
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


class MMD_EXT_PARENT_BAKER_OT_restart_service(bpy.types.Operator):
    bl_idname = "mmd_ext_parent_baker.restart_service"
    bl_label = "Restart HTTP Service"
    bl_description = "Restart the local HTTP service for external-parent baking"

    def execute(self, context: bpy.types.Context) -> set[str]:
        host, port, _auto_start = _get_preference_values(context)
        try:
            stop_service()
            start_service(host, int(port))
        except Exception as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}
        self.report({"INFO"}, f"Service restarted at http://{host}:{port}")
        return {"FINISHED"}


class MMD_EXT_PARENT_BAKER_PT_panel(bpy.types.Panel):
    bl_label = "MMD Ext Parent"
    bl_idname = "MMD_EXT_PARENT_BAKER_PT_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "MMD Ext Parent"

    def draw(self, context: bpy.types.Context) -> None:
        preferences = _get_preferences(context)
        host, port, _auto_start = _get_preference_values(context)
        status = get_service_status()

        layout = self.layout
        layout.label(text="HTTP Service")
        if status["running"]:
            layout.label(text=f'Running at {status["base_url"]}')
        else:
            layout.label(text="Stopped")

        if preferences is not None:
            layout.prop(preferences, "host")
            layout.prop(preferences, "port")
        else:
            layout.label(text=f"Host: {host}")
            layout.label(text=f"Port: {port}")
        row = layout.row(align=True)
        row.operator(MMD_EXT_PARENT_BAKER_OT_start_service.bl_idname, text="Start")
        row.operator(MMD_EXT_PARENT_BAKER_OT_stop_service.bl_idname, text="Stop")
        layout.operator(MMD_EXT_PARENT_BAKER_OT_restart_service.bl_idname, text="Restart")


CLASSES = (
    MMD_EXT_PARENT_BAKER_Preferences,
    MMD_EXT_PARENT_BAKER_OT_start_service,
    MMD_EXT_PARENT_BAKER_OT_stop_service,
    MMD_EXT_PARENT_BAKER_OT_restart_service,
    MMD_EXT_PARENT_BAKER_PT_panel,
)


def register() -> None:
    for cls in CLASSES:
        bpy.utils.register_class(cls)

    host, port, auto_start = _get_preference_values(bpy.context)
    if auto_start:
        try:
            start_service(host, int(port))
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


def _get_preference_values(context: bpy.types.Context) -> tuple[str, int, bool]:
    preferences = _get_preferences(context)
    if preferences is None:
        return DEFAULT_HOST, DEFAULT_PORT, True
    return str(preferences.host), int(preferences.port), bool(preferences.auto_start)
