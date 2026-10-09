/* EOD model freshness and intraday quote freshness are different clocks. */
((root)=>{
  const holidays = new Set(['2026-01-01','2026-01-02','2026-02-16','2026-02-17','2026-02-18','2026-02-19','2026-02-20','2026-04-27','2026-04-30','2026-05-01','2026-08-31','2026-09-01','2026-09-02']);
  const VN_OFFSET = 7 * 3600000;
  function vnLocal(now = new Date()){ return new Date(now.getTime() + VN_OFFSET); }
  function dayKey(local){ return local.toISOString().slice(0,10); }
  function isTradingDay(local){
    const day = dayKey(local), weekday = local.getUTCDay();
    return local.getUTCFullYear() === 2026 && weekday !== 0 && weekday !== 6 && !holidays.has(day);
  }
  function previousTradingDay(local){
    for(let i=0;i<20;i++){
      if(local.getUTCFullYear() !== 2026) return null;
      if(isTradingDay(local)) return dayKey(local);
      local.setUTCDate(local.getUTCDate() - 1);
    }
    return null;
  }
  /*
   * Latest COMPLETED EOD model session.
   * Keep this clock unchanged for forecast validation: before 15:05 the current
   * trading day is not yet a completed model row.
   */
  function expectedSession(now = new Date()) {
    const local = vnLocal(now);
    if(local.getUTCFullYear() !== 2026) return null;
    const minutes = local.getUTCHours() * 60 + local.getUTCMinutes();
    if(minutes < 15 * 60 + 5) local.setUTCDate(local.getUTCDate() - 1);
    return previousTradingDay(local);
  }
  /*
   * Expected quote date.
   * From 09:00 onward on a trading day, an intraday quote must belong to TODAY.
   * Before 09:00 (or on weekends/holidays), the latest completed trading day is
   * still the correct quote date.
   */
  function expectedQuoteSession(now = new Date()) {
    const local = vnLocal(now);
    if(local.getUTCFullYear() !== 2026) return null;
    const minutes = local.getUTCHours() * 60 + local.getUTCMinutes();
    if(isTradingDay(local) && minutes >= 9 * 60) return dayKey(local);
    local.setUTCDate(local.getUTCDate() - 1);
    return previousTradingDay(local);
  }
  function quoteMode(now = new Date()) {
    const local = vnLocal(now);
    if(local.getUTCFullYear() !== 2026 || !isTradingDay(local)) return 'CLOSED';
    const minutes = local.getUTCHours() * 60 + local.getUTCMinutes();
    if(minutes < 9 * 60) return 'PRE_OPEN';
    if(minutes <= 11 * 60 + 30) return 'LIVE';
    if(minutes < 13 * 60) return 'LUNCH';
    // Continuous trading and the closing auction end at 14:45; EOD model
    // readiness at 15:05 is a DIFFERENT clock, not a quote freshness SLA.
    if(minutes <= 14 * 60 + 45) return 'LIVE';
    return 'POST_CLOSE';
  }
  function inspect(snapshot, now = new Date()){
    const expected = expectedSession(now), actual = String(snapshot?.date || '').slice(0,10);
    return {expected, actual, stale: !expected || actual !== expected};
  }
  root.__VMEWS_FRESHNESS__ = {expectedSession, expectedQuoteSession, quoteMode, inspect};
  if(typeof module !== 'undefined') module.exports = root.__VMEWS_FRESHNESS__;
})(typeof window !== 'undefined' ? window : globalThis);
