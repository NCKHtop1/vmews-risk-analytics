import importlib.util
import pathlib

_target = pathlib.Path(__file__).with_name('validate2.py')
_spec = importlib.util.spec_from_file_location('vmews_validate_production', _target)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler
