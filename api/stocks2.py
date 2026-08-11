import importlib.util
import pathlib

_target = pathlib.Path(__file__).with_name('radar.py')
_spec = importlib.util.spec_from_file_location('vmews_radar_production', _target)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler
