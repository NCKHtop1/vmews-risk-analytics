/* Session freshness is evaluated at read time; saved PASS flags are not clocks. */
((root)=>{
  const holidays = new Set(['2026-01-01','2026-01-02','2026-02-16','2026-02-17','2026-02-18','2026-02-19','2026-02-20','2026-04-27','2026-04-30','2026-05-01','2026-08-31','2026-09-01','2026-09-02']);
  function expectedSession(now = new Date()) {
    const local = new Date(now.getTime() + 7 * 3600000);
    if(local.getUTCFullYear() !== 2026) return null;
    const minutes = local.getUTCHours() * 60 + local.getUTCMinutes();
    if(minutes < 15 * 60 + 5) local.setUTCDate(local.getUTCDate() - 1);
    for(let i=0;i<20;i++){
      const day = local.toISOString().slice(0,10), weekday = local.getUTCDay();
      if(local.getUTCFullYear() !== 2026) return null;
      if(weekday !== 0 && weekday !== 6 && !holidays.has(day)) return day;
      local.setUTCDate(local.getUTCDate() - 1);
    }
    return null;
  }
  function inspect(snapshot, now = new Date()){
    const expected = expectedSession(now), actual = String(snapshot?.date || '').slice(0,10);
    return {expected, actual, stale: !expected || actual !== expected};
  }
  root.__VMEWS_FRESHNESS__ = {expectedSession, inspect};
  if(typeof module !== 'undefined') module.exports = root.__VMEWS_FRESHNESS__;
})(typeof window !== 'undefined' ? window : globalThis);
