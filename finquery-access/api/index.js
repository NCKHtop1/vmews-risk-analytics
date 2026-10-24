'use strict';
const crypto = require('node:crypto');
const { neon } = require('@neondatabase/serverless');

const COOKIE = 'finquery_session';
const SESSION_DAYS = 7;
const UPSTREAM = 'https://nckhtop1.github.io/vmews-risk-analytics/';
const GOOGLE_CERTS = 'https://www.googleapis.com/oauth2/v3/certs';
const OWNER = 'ngochailuong7274@gmail.com';
let jwksCache = { until: 0, keys: [] };
let cachedSql = null;

function db() {
  if (!process.env.DATABASE_URL || !process.env.FINQUERY_SESSION_PEPPER) {
    throw new Error('FinQuery auth server is not configured');
  }
  if (!cachedSql) cachedSql = neon(process.env.DATABASE_URL);
  return cachedSql;
}
function json(res, status, payload, extra) {
  const headers = Object.assign({
    'Content-Type': 'application/json; charset=utf-8',
    'Cache-Control': 'no-store, private',
    'X-Content-Type-Options': 'nosniff',
    'X-Frame-Options': 'DENY',
    'Referrer-Policy': 'no-referrer'
  }, extra || {});
  res.writeHead(status, headers);
  res.end(JSON.stringify(payload));
}
function cookieValue(req) {
  const match = String(req.headers.cookie || '').match(/(?:^|;\s*)finquery_session=([A-Za-z0-9_-]{40,100})(?:;|$)/);
  return match ? match[1] : null;
}
function tokenHash(token) {
  return crypto.createHmac('sha256', process.env.FINQUERY_SESSION_PEPPER).update(token).digest('hex');
}
function cookieHeader(token) {
  return COOKIE + '=' + token + '; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=' + (SESSION_DAYS * 86400);
}
function expireCookie() {
  return COOKIE + '=; Path=/; HttpOnly; Secure; SameSite=Lax; Max-Age=0';
}
function originAllowed(req) {
  const origin = String(req.headers.origin || '');
  const host = String(req.headers.host || '').toLowerCase();
  try {
    const o = new URL(origin);
    return o.protocol === 'https:' && o.host.toLowerCase() === host && !origin.includes('@');
  } catch (_) { return false; }
}
function parseBody(req) {
  const value = req.body;
  if (!value) return {};
  if (typeof value === 'object' && !Buffer.isBuffer(value)) return value;
  if (Buffer.byteLength(String(value)) > 16384) throw new Error('Request too large');
  return JSON.parse(String(value));
}
async function googleClaims(credential) {
  if (typeof credential !== 'string' || credential.length > 12000) throw new Error('Invalid Google credential');
  const parts = credential.split('.');
  if (parts.length !== 3) throw new Error('Malformed Google token');
  let header, claims;
  try {
    header = JSON.parse(Buffer.from(parts[0], 'base64url').toString('utf8'));
    claims = JSON.parse(Buffer.from(parts[1], 'base64url').toString('utf8'));
  } catch (_) { throw new Error('Invalid token encoding'); }
  if (header.alg !== 'RS256' || !/^[A-Za-z0-9_-]{1,120}$/.test(String(header.kid || ''))) {
    throw new Error('Unexpected Google signature');
  }
  const now = Math.floor(Date.now() / 1000);
  const email = String(claims.email || '').trim().toLowerCase();
  if (claims.iss !== 'https://accounts.google.com' && claims.iss !== 'accounts.google.com') throw new Error('Invalid token issuer');
  if (claims.aud !== process.env.FINQUERY_GOOGLE_CLIENT_ID) throw new Error('Invalid token audience');
  if (!Number.isFinite(claims.exp) || claims.exp <= now || !Number.isFinite(claims.iat) || claims.iat > now + 120) throw new Error('Expired Google token');
  if (claims.iat < now - 7200 || (claims.email_verified !== true && claims.email_verified !== 'true')) throw new Error('Google email not verified');
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254 || !/^[A-Za-z0-9_-]{3,150}$/.test(String(claims.sub || ''))) throw new Error('Invalid Google identity');
  if (Date.now() >= jwksCache.until || !jwksCache.keys.some(k => k.kid === header.kid)) {
    const response = await fetch(GOOGLE_CERTS, { signal: AbortSignal.timeout(8000), headers: { Accept: 'application/json' } });
    if (!response.ok) throw new Error('Google verification is unavailable');
    const body = await response.json();
    if (!Array.isArray(body.keys)) throw new Error('Google verification keys unavailable');
    jwksCache = { keys: body.keys, until: Date.now() + 10 * 60 * 1000 };
  }
  const jwk = jwksCache.keys.find(k => k.kid === header.kid && k.kty === 'RSA' && (!k.alg || k.alg === 'RS256'));
  if (!jwk || !crypto.verify('RSA-SHA256', Buffer.from(parts[0] + '.' + parts[1]), crypto.createPublicKey({ key: jwk, format: 'jwk' }), Buffer.from(parts[2], 'base64url'))) {
    throw new Error('Invalid Google signature');
  }
  let avatar = String(claims.picture || '');
  try { const u = new URL(avatar); if (u.protocol !== 'https:' || !/(^|\.)googleusercontent\.com$/.test(u.hostname) || avatar.length > 2000) avatar = ''; }
  catch (_) { avatar = ''; }
  return { sub: String(claims.sub), email, name: String(claims.name || email.split('@')[0]).trim().slice(0, 120), avatar };
}
async function session(req) {
  const token = cookieValue(req);
  if (!token) return null;
  const rows = await db()(
    'SELECT u.id,u.email,u.full_name,u.avatar_url,u.role,u.status,s.id AS session_id ' +
    'FROM public.finquery_sessions s INNER JOIN public.finquery_users u ON s.user_id=u.id ' +
    'WHERE s.token_hash=$1 AND s.revoked_at IS NULL AND s.expires_at>now() LIMIT 1',
    [tokenHash(token)]
  );
  return rows[0] || null;
}
function exposed(user) {
  return { email: user.email, name: user.full_name || user.email, avatar: user.avatar_url || '', role: user.role, status: user.status };
}
function adminAllowed(user) {
  return user && user.status === 'active' && ['owner', 'admin'].includes(user.role);
}
function redirect(res, location, status) {
  res.writeHead(status || 303, { Location: location, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  res.end();
}
function safeNext(value) {
  const v = String(value || '/financial-report/index.html');
  return v.startsWith('/') && !v.startsWith('//') && !v.includes('\\') && !/[\r\n]/.test(v) ? v : '/financial-report/index.html';
}
async function audit(actor, action, target, meta) {
  await db()('INSERT INTO public.finquery_audit(actor_email,action,target_email,meta) VALUES ($1,$2,$3,$4::jsonb)', [
    actor, action, target || null, JSON.stringify(meta || {})
  ]);
}
async function googleSignIn(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'Method not allowed' });
  if (!originAllowed(req)) return json(res, 403, { error: 'Invalid request origin' });
  let claims;
  try { claims = await googleClaims(parseBody(req).credential); }
  catch (err) { return json(res, 401, { error: 'Không xác minh được đăng nhập Google.', code: 'GOOGLE_INVALID' }); }
  const rows = await db()(
    'INSERT INTO public.finquery_users(email,google_sub,full_name,avatar_url,last_login_at) ' +
    'VALUES ($1,$2,$3,$4,now()) ON CONFLICT(email) DO UPDATE SET ' +
    'google_sub=COALESCE(finquery_users.google_sub,EXCLUDED.google_sub), ' +
    'full_name=EXCLUDED.full_name,avatar_url=EXCLUDED.avatar_url,last_login_at=now(),updated_at=now() ' +
    'WHERE finquery_users.google_sub IS NULL OR finquery_users.google_sub=EXCLUDED.google_sub ' +
    'RETURNING id,email,full_name,avatar_url,role,status',
    [claims.email, claims.sub, claims.name, claims.avatar]
  );
  const user = rows[0];
  if (!user) return json(res, 403, { error: 'Tài khoản Google không khớp với tài khoản đã đăng ký.' });
  if (user.status === 'blocked') {
    await audit(user.email, 'blocked_login', user.email);
    return json(res, 403, { error: 'Tài khoản đã bị khóa. Liên hệ quản trị viên.', code: 'BLOCKED' }, { 'Set-Cookie': expireCookie() });
  }
  const oldToken = cookieValue(req);
  if (oldToken) await db()('UPDATE public.finquery_sessions SET revoked_at=now() WHERE token_hash=$1 AND revoked_at IS NULL', [tokenHash(oldToken)]);
  const newToken = crypto.randomBytes(32).toString('base64url');
  await db()('INSERT INTO public.finquery_sessions(user_id,token_hash,expires_at) VALUES($1,$2,now()+interval \'7 days\')', [user.id,tokenHash(newToken)]);
  await audit(user.email,'google_login',user.email,{status:user.status});
  return json(res, 200, { authenticated: true, user: exposed(user) }, { 'Set-Cookie': cookieHeader(newToken) });
}
async function authSession(req, res) {
  if (req.method !== 'GET') return json(res, 405, { error: 'Method not allowed' });
  const user = await session(req);
  return json(res, 200, user ? { authenticated: true, user: exposed(user) } : { authenticated: false });
}
async function logout(req, res) {
  if (req.method !== 'POST') return json(res, 405, { error: 'Method not allowed' });
  if (!originAllowed(req)) return json(res, 403, { error: 'Invalid request origin' });
  const token = cookieValue(req);
  if (token) await db()('UPDATE public.finquery_sessions SET revoked_at=now() WHERE token_hash=$1 AND revoked_at IS NULL', [tokenHash(token)]);
  return json(res, 200, { ok: true }, { 'Set-Cookie': expireCookie() });
}
async function adminUsers(req, res, user) {
  if (!adminAllowed(user)) return json(res, 403, { error: 'Chỉ quản trị viên mới có quyền truy cập.' });
  const rows = await db()(
    'SELECT id,email,full_name,role,status,created_at,last_login_at,approved_at,approved_by FROM public.finquery_users ' +
    'ORDER BY CASE status WHEN \'pending\' THEN 0 WHEN \'active\' THEN 1 ELSE 2 END, created_at DESC LIMIT 300'
  );
  return json(res, 200, { users: rows, self: exposed(user) });
}
async function adminAudit(req, res, user) {
  if (!adminAllowed(user)) return json(res, 403, { error: 'Chỉ quản trị viên mới có quyền truy cập.' });
  const rows = await db()('SELECT id,actor_email,action,target_email,created_at FROM public.finquery_audit ORDER BY id DESC LIMIT 100');
  return json(res, 200, { events: rows });
}
async function adminUpdate(req, res, actor) {
  if (!adminAllowed(actor)) return json(res, 403, { error: 'Chỉ quản trị viên mới có quyền truy cập.' });
  if (req.method !== 'POST') return json(res, 405, { error: 'Method not allowed' });
  if (!originAllowed(req)) return json(res, 403, { error: 'Invalid request origin' });
  let data;
  try { data = parseBody(req); } catch (_) { return json(res, 400, { error: 'Dữ liệu không hợp lệ.' }); }
  const id = String(data.id || '');
  const action = String(data.action || '');
  if (!/^[0-9a-f-]{36}$/i.test(id) || !['approve','block','unblock','set_role','revoke_sessions'].includes(action)) {
    return json(res, 400, { error: 'Yêu cầu không hợp lệ.' });
  }
  const rows = await db()('SELECT id,email,role,status FROM public.finquery_users WHERE id=$1 LIMIT 1', [id]);
  const target = rows[0];
  if (!target) return json(res, 404, { error: 'Không tìm thấy tài khoản.' });
  if (target.role === 'owner' || target.email.toLowerCase() === OWNER || target.id === actor.id) {
    return json(res, 403, { error: 'Không thể thay đổi tài khoản chủ sở hữu hoặc tài khoản đang sử dụng.' });
  }
  if (actor.role !== 'owner' && target.role === 'admin') return json(res, 403, { error: 'Chỉ chủ sở hữu mới được quản lý tài khoản Admin.' });
  let change = null;
  if (action === 'approve' || action === 'unblock') {
    change = await db()('UPDATE public.finquery_users SET status=\'active\',approved_at=now(),approved_by=$2,updated_at=now() WHERE id=$1 RETURNING email,role,status', [id,actor.email]);
  } else if (action === 'block') {
    change = await db()('UPDATE public.finquery_users SET status=\'blocked\',updated_at=now() WHERE id=$1 RETURNING email,role,status', [id]);
    await db()('UPDATE public.finquery_sessions SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL', [id]);
  } else if (action === 'set_role') {
    const role = String(data.role || '');
    if (actor.role !== 'owner' || !['admin','user'].includes(role)) return json(res,403,{ error:'Chỉ chủ sở hữu được phân quyền Admin.' });
    change = await db()('UPDATE public.finquery_users SET role=$2,updated_at=now() WHERE id=$1 RETURNING email,role,status', [id,role]);
    await db()('UPDATE public.finquery_sessions SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL', [id]);
  } else if (action === 'revoke_sessions') {
    await db()('UPDATE public.finquery_sessions SET revoked_at=now() WHERE user_id=$1 AND revoked_at IS NULL', [id]);
  }
  await audit(actor.email, action, target.email, { role: data.role || null });
  return json(res, 200, { ok:true, user: change && change[0] ? change[0] : {email:target.email} });
}
function htmlToolbar() {
  return '<style id="finquery-auth-site-style">#site-unlock-form,.finquery-google-account{display:none!important}' +
    '.finquery-login-toolbar{display:flex;align-items:center;gap:10px;margin-left:auto;font:600 12px/1.4 system-ui,sans-serif;color:#274167}' +
    '.finquery-login-toolbar a{color:#335cba;text-decoration:none}.finquery-login-toolbar button{padding:7px 11px;border:1px solid #cbd8ea;border-radius:9px;background:#fff;cursor:pointer;font:inherit}' +
    '.finquery-login-toolbar .name{max-width:240px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}' +
    '@media(max-width:700px){.finquery-login-toolbar{width:100%;flex-wrap:wrap;margin:8px 0}}</style>' +
    '<script>try{sessionStorage.setItem("finquery-site-access","1")}catch(_){}</script>';
}
function toolbarCode() {
  return '<script>(function(){function start(){fetch("/api/auth/session",{credentials:"same-origin",cache:"no-store"})' +
  '.then(function(r){return r.json()}).then(function(s){if(!s.authenticated||s.user.status!=="active"){location.replace("/login");return}' +
  'var parent=document.querySelector(".intro");if(!parent)return;var bar=document.createElement("div");bar.className="finquery-login-toolbar";' +
  'var name=document.createElement("span");name.className="name";name.textContent=s.user.name||s.user.email;bar.append(name);' +
  'if(s.user.role==="owner"||s.user.role==="admin"){var admin=document.createElement("a");admin.href="/admin";admin.textContent="Quản trị";bar.append(admin)}' +
  'var out=document.createElement("button");out.type="button";out.textContent="Đăng xuất";out.onclick=function(){' +
  'fetch("/api/auth/logout",{method:"POST",credentials:"same-origin"}).finally(function(){location.href="/login"})};bar.append(out);parent.append(bar)' +
  '}).catch(function(){location.href="/login"})}if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",start);else start()})()</script>';
}
async function gateway(req, res, route, user) {
  if (req.method !== 'GET' && req.method !== 'HEAD') return json(res,405,{error:'Method not allowed'});
  if (!user || user.status !== 'active') {
    const url = new URL(req.url, 'https://' + String(req.headers.host || 'finquery.info.vn'));
    if (req.method === 'GET' && (/\.html?$/i.test(route) || route === '' || route === 'financial-report')) {
      return redirect(res,'/login?next=' + encodeURIComponent(safeNext(url.pathname + url.search)),307);
    }
    return json(res,401,{error:'Đăng nhập và được phê duyệt để sử dụng FinQuery.',code:user ? user.status.toUpperCase() : 'LOGIN_REQUIRED'});
  }
  const clean = route.replace(/^\/+/, '');
  if (!clean || clean.includes('\\') || clean.includes('\0') || clean.split('/').some(s => s === '..' || s === '.')) {
    return json(res,400,{error:'Invalid path'});
  }
  if (clean.startsWith('api/') || clean.startsWith('_vercel/')) return json(res,404,{error:'Not found'});
  const upstream = new URL(clean, UPSTREAM);
  if (!upstream.href.startsWith(UPSTREAM)) return json(res,400,{error:'Invalid upstream path'});
  const incoming = new URL(req.url, 'https://' + String(req.headers.host || 'finquery.info.vn'));
  for (const [k,v] of incoming.searchParams) if (k !== 'route') upstream.searchParams.append(k,v);
  const upstreamResponse = await fetch(upstream.href, {
    method: req.method,
    redirect:'follow',
    signal:AbortSignal.timeout(25000),
    headers: { Accept: String(req.headers.accept || '*/*') }
  });
  if (!upstreamResponse.url.startsWith(UPSTREAM)) return json(res,502,{error:'Unexpected upstream redirect'});
  if (!upstreamResponse.ok) return json(res,upstreamResponse.status,{error:'Không tải được tài nguyên FinQuery.'});
  const type = upstreamResponse.headers.get('content-type') || 'application/octet-stream';
  const headers = {
    'Content-Type':type,
    'Cache-Control':'no-store, private',
    'X-Content-Type-Options':'nosniff',
    'X-Frame-Options':'SAMEORIGIN',
    'Referrer-Policy':'strict-origin-when-cross-origin'
  };
  if (req.method === 'HEAD') { res.writeHead(200,headers);return res.end(); }
  if (type.includes('text/html')) {
    let html = await upstreamResponse.text();
    html = html.replace(/(<meta name="finquery-google-client-id" content=")[^"]*/i, '$1');
    html = html.replace(/<\/head>/i,htmlToolbar()+'</head>');
    html = html.replace(/<\/body>/i,toolbarCode()+'</body>');
    res.writeHead(200,Object.assign(headers,{'Content-Type':'text/html; charset=utf-8'}));
    return res.end(html);
  }
  const buf = Buffer.from(await upstreamResponse.arrayBuffer());
  res.writeHead(200,headers);
  res.end(buf);
}
module.exports = async function handler(req,res) {
  const requestUrl = new URL(req.url,'https://'+String(req.headers.host || 'finquery.info.vn'));
  const route = String((req.query && req.query.route) || requestUrl.searchParams.get('route') || requestUrl.pathname.replace(/^\/+/,''));
  try {
    if (route === 'healthz') return json(res,200,{ok:true,service:'finquery-auth'});
    if (route === 'login' || route === 'login.html') return redirect(res,'/login.html',307);
    if (route === 'api/auth/google') return googleSignIn(req,res);
    if (route === 'api/auth/session') return authSession(req,res);
    if (route === 'api/auth/logout') return logout(req,res);
    const user = await session(req);
    if (route === 'admin') {
      if (!adminAllowed(user)) return redirect(res,'/login?next=%2Fadmin',307);
      return redirect(res,'/admin.html',307);
    }
    if (route === 'api/admin/users') return adminUsers(req,res,user);
    if (route === 'api/admin/audit') return adminAudit(req,res,user);
    if (route === 'api/admin/user') return adminUpdate(req,res,user);
    if (route.startsWith('api/')) return json(res,404,{error:'Not found'});
    return gateway(req,res,route,user);
  } catch (err) {
    console.error('[finquery-auth]',err && err.message ? err.message : 'unexpected error');
    return json(res,503,{error:'Hệ thống xác thực tạm thời chưa sẵn sàng. Vui lòng thử lại.'});
  }
};
