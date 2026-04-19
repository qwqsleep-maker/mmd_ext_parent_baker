bl_info = {
    "name": "MMD External Parent Baker",
    "author": "OpenAI Codex",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "View3D > Sidebar > MMD Ext Parent",
    "description": "Offline external-parent baker for mmd_tools scenes",
    "category": "Animation",
}


def register() -> None:
    from .addon import register as addon_register

    addon_register()


def unregister() -> None:
    from .addon import unregister as addon_unregister

    addon_unregister()

