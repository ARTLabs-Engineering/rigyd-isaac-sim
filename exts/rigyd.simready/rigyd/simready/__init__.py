# Kit imports this package and looks for the omni.ext.IExt subclass here. Outside
# Isaac Sim (e.g. scripts/smoke_test.py), carb/omni aren't available — guard the
# import so the pure-stdlib modules (api_client, loader) stay usable standalone.
try:
    from .extension import RigydSimReadyExtension
except ModuleNotFoundError:  # no carb/omni — running outside Kit
    RigydSimReadyExtension = None

__all__ = ["RigydSimReadyExtension"]
