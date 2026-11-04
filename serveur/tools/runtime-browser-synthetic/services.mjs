// Fixed local protocol fixtures, not substitutes for IdP/embedding qualification.
import http from 'node:http';
import https from 'node:https';
import fs from 'node:fs';
import path from 'node:path';
import { once } from 'node:events';

export const owner = 'synthetic.browser';
export const browserCookie = 'mrjam-synthetic-browser=owner';
export const csrf = 'synthetic-browser-csrf-only';
export const password = 'Entirely synthetic password 2026!';
const hosts = new Set(['vision.mrj.am', 'audition.mrj.am']);
const hasCookie = (request, value) => (request.headers.cookie || '').split(';').some(item => item.trim() === value);

async function body(request) {
  const parts = []; let size = 0;
  for await (const chunk of request) {
    size += chunk.length;
    if (size > 65536) throw new Error('FIXTURE_BODY_LIMIT');
    parts.push(chunk);
  }
  return size ? JSON.parse(Buffer.concat(parts)) : null;
}

function json(response, status, value, headers = {}) {
  response.writeHead(status, { 'content-type': 'application/json', 'cache-control': 'no-store', ...headers });
  response.end(status === 204 ? undefined : JSON.stringify(value));
}

function closed(handler, counters) {
  return (request, response) => {
    const key = `${request.method}:${request.url}`;
    counters[key] = (counters[key] || 0) + 1;
    Promise.resolve(handler(request, response)).catch(() => json(response, 400, { code: 'SYNTHETIC_REQUEST_REFUSED' }));
  };
}

async function listen(server) {
  server.requestTimeout = 10000;
  server.headersTimeout = 10000;
  server.maxHeadersCount = 32;
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  return server.address().port;
}

export async function startServices(directory) {
  const calls = { identity: {}, embedding: {}, log_native: {} };
  const servers = [];
  let logStage = 'none';
  const identity = http.createServer(closed(async (request, response) => {
    const authenticated = hasCookie(request, browserCookie);
    const host = request.headers.host;
    if (request.url === '/auth/configuration' && request.method === 'GET' && hosts.has(host)) {
      return json(response, 200, { mode: 'local', synthetic: true });
    }
    if (request.url === '/auth/session' && request.method === 'GET' && hosts.has(host)) {
      return authenticated
        ? json(response, 200, { username: owner, csrf, administrateur: false, verificationRenforcee: false })
        : json(response, 401, { error: 'synthetic_session_required' });
    }
    if (request.url === '/auth/login' && request.method === 'POST' && host === 'vision.mrj.am') {
      const value = await body(request);
      if (request.headers.origin !== `https://${host}` || value?.username !== owner || value?.password !== password) return json(response, 401, {});
      return json(response, 200, { username: owner, csrf, administrateur: false, verificationRenforcee: false },
        { 'set-cookie': `${browserCookie}; Secure; HttpOnly; Path=/; SameSite=Strict` });
    }
    if (request.url === '/auth/logout' && request.method === 'POST' && hosts.has(host)) {
      if (!authenticated || request.headers.origin !== `https://${host}` || request.headers['x-csrf-token'] !== csrf) return json(response, 403, {});
      return json(response, 200, {}, { 'set-cookie': 'mrjam-synthetic-browser=; Secure; HttpOnly; Path=/; SameSite=Strict; Max-Age=0' });
    }
    if (request.method !== 'GET' || !['/verify', '/verify-mcp', '/verify-gestion'].includes(request.url)
        || host !== 'mrj-auth.internal' || !hosts.has(request.headers['x-forwarded-host'])
        || request.headers['x-forwarded-proto'] !== 'https') return json(response, 404, {});
    const forwardedHost = request.headers['x-forwarded-host'];
    if (request.url === '/verify-mcp') {
      const audience = forwardedHost === 'vision.mrj.am' ? 'vision' : 'audition';
      if (request.headers.authorization !== `Bearer synthetic-mcp-${audience}`) return json(response, 401, {});
    } else {
      if (!authenticated) return json(response, 401, {});
      if (request.url === '/verify-gestion'
          && (forwardedHost !== 'audition.mrj.am' || !hasCookie(request, 'mrjam-synthetic-mfa=recent'))) return json(response, 403, {});
      if (!['GET', 'HEAD'].includes(request.headers['x-original-method'])
          && (request.headers['x-csrf-token'] !== csrf || request.headers.origin !== `https://${forwardedHost}`)) return json(response, 403, {});
    }
    return json(response, 204, null, { 'x-mrj-user': owner });
  }, calls.identity));
  servers.push(identity);
  const embedding = http.createServer(closed(async (request, response) => {
    if (request.method !== 'POST' || request.url !== '/embedding' || request.headers.host !== 'mrjam-embeddings.internal') return json(response, 404, {});
    const value = await body(request);
    if (Object.keys(value || {}).join(',') !== 'contenu' || typeof value.contenu !== 'string' || !value.contenu || Buffer.byteLength(value.contenu) > 65536) return json(response, 400, {});
    return json(response, 200, { embedding: [0.5, 0.25, -0.75], modele: 'synthetic-browser-3' });
  }, calls.embedding));
  servers.push(embedding);
  const native = https.createServer({ key: fs.readFileSync(path.join(directory, 'tls.key')), cert: fs.readFileSync(path.join(directory, 'tls.pem')), minVersion: 'TLSv1.2' }, closed(async (request, response) => {
    if (request.headers.host !== 'log.mrj.am' || request.headers.origin !== 'https://log.mrj.am') return json(response, 400, {});
    const authenticated = hasCookie(request, 'bearer=synthetic-native-only');
    if (request.method === 'GET' && request.url === '/v1/self/_uat') {
      return authenticated ? json(response, 200, { displayname: 'Compte Log entièrement inventé', expiry: Math.floor(Date.now() / 1000) + 1800 }) : json(response, 401, {});
    }
    if (request.method === 'GET' && request.url === '/v1/logout') {
      logStage = 'none';
      return json(response, 200, null, { 'set-cookie': 'bearer=; Path=/; Secure; HttpOnly; SameSite=Strict; Max-Age=0' });
    }
    if (request.method !== 'POST' || request.url !== '/v1/auth') return json(response, 404, {});
    const value = await body(request);
    if (value?.step?.init2?.username === owner && value.step.init2.issue === 'cookie' && value.step.init2.privileged === false) {
      logStage = 'choose';
      return json(response, 200, { state: { choose: ['password'] } }, { 'set-cookie': 'auth-session-id=synthetic-native-step; Secure; HttpOnly; Path=/; SameSite=Strict' });
    }
    if (!hasCookie(request, 'auth-session-id=synthetic-native-step')) return json(response, 401, {});
    if (logStage === 'choose' && value?.step?.begin === 'password') {
      logStage = 'credential';
      return json(response, 200, { state: { continue: ['password'] } });
    }
    if (logStage === 'credential' && value?.step?.cred?.password === password) {
      logStage = 'connected';
      return json(response, 200, { state: { success: 'synthetic-token-must-be-erased-by-rust' } },
        { 'set-cookie': 'bearer=synthetic-native-only; Secure; HttpOnly; Path=/; SameSite=Strict' });
    }
    return json(response, 401, { state: { denied: 'synthetic fixture refusal' } });
  }, calls.log_native));
  servers.push(native);
  try {
    const ports = { identity: await listen(identity), embedding: await listen(embedding), log: await listen(native) };
    return { ports, calls, close: async () => {
      await Promise.all(servers.map(server => new Promise(resolve => { server.closeAllConnections(); server.close(resolve); })));
    } };
  } catch (error) {
    for (const server of servers) server.close();
    throw error;
  }
}
