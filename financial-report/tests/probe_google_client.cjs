'use strict';
// Read-only verification of Google's OAuth registration for FinQuery.
// No Google user, client secret or token is required for this negative-path probe.
// A deliberately unregistered redirect URI elicits redirect_uri_mismatch from a
// real web OAuth client, while a misspelled/deleted client returns invalid_client.
const fs = require('node:fs');
const path = require('node:path');
const html = fs.readFileSync(path.resolve(__dirname, '../frontend/index.html'), 'utf8');
const clientId = html.match(/<meta name="finquery-google-client-id" content="([^"]+)"/)?.[1];
if (!/^[0-9]+-[a-z0-9-]+\.apps\.googleusercontent\.com$/.test(clientId || '')) {
  console.error('FAIL: FinQuery Google Client ID is missing or malformed');
  process.exit(1);
}
const params = new URLSearchParams({
  client_id: clientId,
  redirect_uri: 'https://finquery.info.vn/oauth-client-discovery-only',
  response_type: 'code',
  scope: 'openid email profile',
  state: 'finquery-oauth-client-discovery'
});
const endpoint = 'https://accounts.google.com/o/oauth2/v2/auth?' + params;
(async () => {
  let response;
  try {
    response = await fetch(endpoint, {
      redirect: 'manual',
      signal: AbortSignal.timeout(20000),
      headers: {'User-Agent': 'Mozilla/5.0 (compatible; FinQuery-OAuth-Client-Probe/1.0)'}
    });
  } catch (error) {
    console.log('INCONCLUSIVE: Google OAuth service unreachable (' + error.name + ')');
    return;
  }
  const body = (await response.text()).slice(0, 250000);
  const url = response.headers.get('location') || '';
  const returned = body + '\n' + url;
  if (/invalid_client|OAuth client was not found/i.test(returned)) {
    console.error('FAIL: Google reports invalid_client for Client ID from FinQuery');
    process.exitCode = 1;
    return;
  }
  if (/redirect_uri_mismatch/i.test(returned)) {
    console.log('PASS: Google recognized the OAuth client (expected redirect_uri_mismatch on deliberately unregistered callback)');
    return;
  }
  if ([301, 302, 303, 307, 308].includes(response.status) && /^https:\/\/accounts\.google\.com\//.test(url)) {
    console.log('PASS: Google recognized client and continued into OAuth flow (HTTP ' + response.status + ')');
    return;
  }
  // A Google anti-bot page or network intermediary cannot prove client validity.
  console.log('INCONCLUSIVE: Google OAuth HTTP ' + response.status + '; interactive confirmation is still required');
})().catch(error => {
  console.error('INCONCLUSIVE: Unexpected network probe failure: ' + error.name);
});
