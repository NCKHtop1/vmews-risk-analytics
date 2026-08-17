import pathlib
import runpy
import v12_source_capture as capture
from v12_reference_resilience import install as install_resilience
from v12_source_capture_methodfix import install as install_continuity

audit=install_resilience(capture,max_attempts=3,backoff_seconds=(1.0,2.0))
install_continuity()
print({'v12ReferenceResilience':audit,'v12ContinuityPolicy':'STRICT_POST_LAST_UNRESOLVED_GT_GUARD_SUFFIX_MIN_ROWS_UNCHANGED'},flush=True)
runpy.run_path(str(pathlib.Path(__file__).with_name('freeze_v12_source_snapshot.py')),run_name='__main__')
