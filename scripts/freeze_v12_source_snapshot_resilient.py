import pathlib
import runpy
import v12_source_capture as capture
from v12_reference_resilience import install

audit=install(capture,max_attempts=3,backoff_seconds=(1.0,2.0))
print({'v12ReferenceResilience':audit},flush=True)
runpy.run_path(str(pathlib.Path(__file__).with_name('freeze_v12_source_snapshot.py')),run_name='__main__')
