import os
import pathlib
import importlib.util

# Official Vnstock source prioritizes VNSTOCK_DATA_DIR over Path.home()/.vnstock.
# Vercel Functions can write to /tmp, while the deployment/home filesystem is
# read-only. Set the Vnstock data directory before importing any Vnstock module.
os.environ["VNSTOCK_DATA_DIR"] = "/tmp/.vnstock"
os.environ["HOME"] = "/tmp"
os.environ["USERPROFILE"] = "/tmp"
os.environ["XDG_CACHE_HOME"] = "/tmp/.cache"
os.environ["XDG_CONFIG_HOME"] = "/tmp/.config"
os.environ["XDG_DATA_HOME"] = "/tmp/.local/share"
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
os.environ["PYTHONPYCACHEPREFIX"] = "/tmp/pycache"
os.environ["JOBLIB_TEMP_FOLDER"] = "/tmp/joblib"

for directory in (
    "/tmp/.vnstock",
    "/tmp/.vnstock/id",
    "/tmp/.cache",
    "/tmp/.config",
    "/tmp/.local/share",
    "/tmp/matplotlib",
    "/tmp/pycache",
    "/tmp/joblib",
):
    try:
        os.makedirs(directory, exist_ok=True)
    except Exception:
        pass

# Defensive compatibility for dependencies that still call Path.home().
pathlib.Path.home = classmethod(lambda cls: cls("/tmp"))

# Import the resilient provider wrapper only after Vnstock's writable directory
# has been configured. That wrapper provides Vnstock/KBS primary data and a
# secondary live provider if the primary source is temporarily unavailable.
wrapped_path = pathlib.Path(__file__).with_name("live.py")
spec = importlib.util.spec_from_file_location("vmews_live_runtime", wrapped_path)
wrapped = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wrapped)
handler = wrapped.handler
