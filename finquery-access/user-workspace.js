/* FinQuery signed-in account workspace. Local fallback remains usable offline.
 * No credentials or Gemini keys are sent or persisted here.
 */
(function () {
  'use strict';
  const API = '/api/user/workspace';
  const KEYS = {
    watchlist: 'finquery-watchlist',
    strategies: 'finquery-strategies-v2',
    newsMode: 'finquery-news-mode'
  };
  const state = {ready:false, busy:false, revision:0, last:'', userId:null};
  function read(key, fallback) {
    try { return JSON.parse(localStorage.getItem(key) || 'null') ?? fallback; }
    catch (_) { return fallback; }
  }
  function snapshot() {
    const watchlist = read(KEYS.watchlist, []);
    const strategies = read(KEYS.strategies, []);
    const newsMode = localStorage.getItem(KEYS.newsMode) || 'company';
    return {
      watchlist: Array.isArray(watchlist) ? [...new Set(watchlist
        .map(s => String(s || '').trim().toUpperCase())
        .filter(s => /^[A-Z]{3,5}$/.test(s)))].slice(0,100) : [],
      strategies: Array.isArray(strategies) ? strategies.slice(0,30) : [],
      settings: {newsMode: ['company','watchlist','new','vietnam','sbv','global'].includes(newsMode) ? newsMode : 'company'}
    };
  }
  function normalized(x) {
    return JSON.stringify({
      watchlist: x.watchlist || [], strategies: x.strategies || [],
      settings: x.settings || {newsMode:'company'}
    });
  }
  function writeLocal(workspace) {
    const data = normalized(workspace);
    if (normalized(snapshot()) === data) return false;
    try {
      localStorage.setItem(KEYS.watchlist, JSON.stringify(workspace.watchlist || []));
      localStorage.setItem(KEYS.strategies, JSON.stringify(workspace.strategies || []));
      if (workspace.settings && workspace.settings.newsMode) {
        localStorage.setItem(KEYS.newsMode, workspace.settings.newsMode);
      }
      return true;
    } catch (_) { return false; }
  }
  async function request(method, data) {
    const response = await fetch(API,{
      method, credentials:'same-origin',cache:'no-store',
      headers:{'Content-Type':'application/json'},
      ...(data ? {body:JSON.stringify(data)} : {}),
      signal:AbortSignal.timeout(12000)
    });
    const result = await response.json();
    return {status:response.status, result};
  }
  async function sync(force) {
    if (!state.ready || state.busy) return;
    const values = snapshot(), signature = normalized(values);
    if (!force && signature === state.last) return;
    state.busy = true;
    try {
      let response = await request('PUT',{...values, revision:state.revision});
      if (response.status === 409 && response.result.workspace) {
        // Two tabs/devices updated at once: retry a single time against latest
        // revision, preserving the user's current local edits.
        response = await request('PUT',{...values,revision:response.result.workspace.revision});
      }
      if (response.status === 200 && response.result.workspace) {
        state.revision = response.result.workspace.revision;
        state.last = normalized(response.result.workspace);
      } else {
        console.warn('[FinQuery workspace] Changes remain on this device; sync will retry.');
      }
    } catch (_) {
      console.warn('[FinQuery workspace] Offline; local changes have been retained.');
    } finally {
      state.busy = false;
    }
  }
  async function init() {
    try {
      const sessionResponse = await fetch('/api/auth/session',{
        credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(9000)
      });
      if (!sessionResponse.ok) return;
      const session = await sessionResponse.json();
      if (!session.authenticated || session.user?.status !== 'active') return;
      state.userId = session.user.id;
      const response = await request('GET');
      if (response.status !== 200 || !response.result.workspace) return;
      const remote = response.result.workspace, local = snapshot();
      state.revision = remote.revision;
      if (remote.revision > 0) {
        const changed = writeLocal(remote);
        state.last = normalized(remote);
        state.ready = true;
        if (changed) {
          const marker = 'finquery-workspace-hydrated:' + state.userId + ':' + remote.revision;
          if (sessionStorage.getItem(marker) !== '1') {
            sessionStorage.setItem(marker, '1');
            location.reload();
            return;
          }
        }
      } else {
        state.last = normalized(local);
        state.ready = true;
        if (local.watchlist.length || local.strategies.length ||
            local.settings.newsMode !== 'company') {
          state.last = '';
          await sync();
        }
      }
      setInterval(() => { sync(false); }, 6000);
      document.addEventListener('click', () => {
        setTimeout(() => { sync(false); }, 1200);
      }, {passive:true});
      window.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') sync(false);
      });
    } catch (_) {
      console.warn('[FinQuery workspace] Local mode; personal sync will retry on next page load.');
    }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded',init,{once:true});
  else init();
})();
