import importlib.util
import pathlib
import time

ROOT=pathlib.Path(__file__).resolve().parents[1]
PATH=ROOT/'scripts'/'update_hose_detail_cache.py'
spec=importlib.util.spec_from_file_location('vmews_hose_cache_impl',PATH)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_original=mod.vnstock_once
_last_call=[0.0]

def throttled_vnstock(symbol):
    # Unified Market may use several internal requests. Keep a conservative
    # per-symbol cadence under the anonymous 20-request/minute ceiling.
    last=None
    for attempt in range(4):
        wait=max(0.0,20.0-(time.monotonic()-_last_call[0]))
        if wait:
            time.sleep(wait)
        _last_call[0]=time.monotonic()
        try:
            return _original(symbol)
        except BaseException as e:
            last=e
            # Vnstock can raise SystemExit when the guest quota is exceeded.
            # Cool down before retrying instead of terminating the refresh job.
            time.sleep(35.0+attempt*10.0)
    raise RuntimeError(f'{symbol}: Vnstock fallback failed after cooldown retries: {last}')

mod.vnstock_once=throttled_vnstock
mod.main()
