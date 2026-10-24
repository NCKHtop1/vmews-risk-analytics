(function () {
  'use strict';
  const CLIENT_ID = '216957728290-6h80djpq7ouk2cmd5jgjr08j6233voes.apps.googleusercontent.com';
  const status = document.getElementById('status');
  const switchAccount = document.getElementById('switch-account');
  const nextParam = new URLSearchParams(window.location.search).get('next');
  function nextPath() {
    if (!nextParam || !nextParam.startsWith('/') || nextParam.startsWith('//') ||
        nextParam.includes('\\') || /[\r\n]/.test(nextParam)) return '/financial-report/index.html';
    try {
      const u = new URL(nextParam, window.location.origin);
      return u.origin === window.location.origin ? u.pathname + u.search + u.hash : '/financial-report/index.html';
    } catch (_) { return '/financial-report/index.html'; }
  }
  function report(text) {
    if (status) status.textContent = text;
  }
  function visit() { window.location.replace(nextPath()); }
  async function signOut() {
    try {
      await fetch('/api/auth/logout', { method: 'POST', credentials: 'same-origin' });
    } catch (_) {}
    window.location.replace('/login.html');
  }
  switchAccount?.addEventListener('click', signOut);

  async function existingSession() {
    try {
      const response = await fetch('/api/auth/session', { cache: 'no-store', credentials: 'same-origin' });
      if (!response.ok) throw new Error('SESSION_UNAVAILABLE');
      const result = await response.json();
      if (result.authenticated && result.user?.status === 'active') {
        report('Đã nhận diện tài khoản ' + result.user.email + '. Đang mở FinQuery…');
        visit();
        return;
      }
      if (result.authenticated && result.user?.status === 'pending') {
        report('Tài khoản ' + result.user.email + ' đang chờ được cấp quyền.');
        switchAccount.style.display = 'inline-block';
      } else if (result.authenticated && result.user?.status === 'blocked') {
        report('Tài khoản đã bị khóa. Vui lòng liên hệ quản trị viên.');
        switchAccount.style.display = 'inline-block';
      } else {
        report('Vui lòng chọn tài khoản Google để đăng nhập.');
      }
    } catch (_) {
      report('Chưa kiểm tra được phiên đăng nhập. Vui lòng thử lại.');
    }
  }
  async function credential(response) {
    report('Đang xác minh tài khoản Google…');
    try {
      const r = await fetch('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ credential: response.credential })
      });
      const result = await r.json();
      if (!r.ok) {
        report(result.error || 'Không thể xác minh Google. Vui lòng thử lại.');
        return;
      }
      if (result.user?.status === 'active') {
        report('Xin chào, ' + result.user.name + '. Đang mở FinQuery…');
        visit();
      } else {
        report('Đã ghi nhận tài khoản. Vui lòng liên hệ quản trị viên.');
        switchAccount.style.display = 'inline-block';
      }
    } catch (_) {
      report('Không thể kết nối máy chủ xác thực. Vui lòng thử lại.');
    }
  }
  async function ready() {
    try {
      const health = await fetch('/healthz', { cache: 'no-store', credentials: 'same-origin' });
      if (!health.ok) {
        report('Hệ thống đăng nhập đang được cấu hình. Vui lòng quay lại sau.');
        return;
      }
      if (!window.google?.accounts?.id) throw new Error('GOOGLE_UNAVAILABLE');
      google.accounts.id.initialize({ client_id: CLIENT_ID, callback: credential, auto_select: false });
      google.accounts.id.renderButton(document.getElementById('signin'), {
        type: 'standard', theme: 'outline', size: 'large',
        shape: 'pill', text: 'signin_with', locale: 'vi', width: 280
      });
      existingSession();
    } catch (_) { report('Không kết nối được hệ thống đăng nhập. Vui lòng làm mới trang.'); }
  }
  const script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client?hl=vi';
  script.async = true;
  script.onload = ready;
  script.onerror = function () { report('Google Sign-In tạm thời không sẵn sàng.'); };
  document.head.appendChild(script);
})();
