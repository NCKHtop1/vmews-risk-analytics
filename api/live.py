import os
import pathlib
import importlib.util

# Vercel Functions expose a read-only deployment filesystem. Vnstock and some of
# its dependencies may try to create user config/cache files under Path.home().
# Bootstrap every writable location to /tmp BEFORE importing the Vnstock core.
os.environ["HOME"] = "/tmp"
os.environ["USERPROFILE"] = "/tmp"
os.environ["XDG_CACHE_HOME"] = "/tmp/.cache"
os.environ["XDG_CONFIG_HOME"] = "/tmp/.config"
os.environ["XDG_DATA_HOME"] = "/tmp/.local/share"
os.environ["MPLCONFIGDIR"] = "/tmp/matplotlib"
os.environ["PYTHONPYCACHEPREFIX"] = "/tmp/pycache"
os.environ["JOBLIB_TEMP_FOLDER"] = "/tmp/joblib"

for directory in (
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

# Some libraries use pathlib.Path.home() rather than $HOME.
pathlib.Path.home = classmethod(lambda cls: cls("/tmp"))

# Load the existing EWS implementation only after the writable runtime bootstrap
# is complete. Keeping the model core separate makes this fix easy to audit.
core_path = pathlib.Path(__file__).with_name("ews.py")
spec = importlib.util.spec_from_file_location("vmews_ews_core", core_path)
core = importlib.util.module_from_spec(spec)
spec.loader.exec_module(core)
handler = core.handler
