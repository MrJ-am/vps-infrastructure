'use strict';
(() => {
  const form = document.getElementById('login');
  const separate = document.getElementById('separate');
  const status = document.getElementById('status');
  const commit = document.getElementById('commit');
  const cancel = document.getElementById('cancel');
  let transaction = null;
  let busy = false;
  const from64 = value => Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), ch => ch.charCodeAt(0));
  const to64 = value => btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  async function call(action, value) {
    const response = await fetch('./api/' + action, {method: 'POST', credentials: 'omit', cache: 'no-store', redirect: 'error', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
    if (!response.ok) throw new Error('REFUSED');
    return response.json();
  }
  function disabled(value) {
    busy = value;
    for (const item of form.elements) item.disabled = value;
    commit.disabled = value;
    cancel.disabled = value;
  }
  async function revoke() {
    if (transaction) {
      try { await call('cancel', {transaction}); } catch (_) { /* Server expiry also revokes the dedicated session. */ }
      transaction = null;
    }
  }
  separate.addEventListener('change', () => {
    document.getElementById('access-label').hidden = !separate.checked;
    document.getElementById('access').required = separate.checked;
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || location.origin !== 'https://log.mrj.am' || !window.isSecureContext) return;
    disabled(true);
    try {
      await revoke();
      let result = await call('begin', {identity: document.getElementById('identity').value.trim(), access: separate.checked ? document.getElementById('access').value.trim() : null});
      transaction = result.transaction;
      for (let count = 0; result.status === 'PASSKEY_REQUIRED' && count < 2; count++) {
        status.textContent = result.account === 2 ? 'Authentifiez le compte chargé des droits d’accès dans Proton Pass.' : 'Confirmez votre passkey dans Proton Pass.';
        const publicKey = result.challenge.publicKey;
        publicKey.challenge = from64(publicKey.challenge);
        publicKey.allowCredentials?.forEach(item => { item.id = from64(item.id); });
        const credential = await navigator.credentials.get({publicKey});
        const response = credential.response;
        const assertion = {id: credential.id, rawId: to64(credential.rawId), type: credential.type,
          response: {authenticatorData: to64(response.authenticatorData), clientDataJSON: to64(response.clientDataJSON), signature: to64(response.signature), userHandle: response.userHandle === null ? null : to64(response.userHandle)}};
        result = await call('assert', {transaction, assertion});
      }
      if (result.status !== 'READY') throw new Error('REFUSED');
      form.hidden = true;
      commit.hidden = false;
      cancel.hidden = false;
      status.textContent = 'Authentification réussie. Vous pouvez préparer les deux accès techniques.';
    } catch (_) {
      await revoke();
      status.textContent = 'L’authentification n’a pas abouti. Vérifiez le compte choisi et réessayez.';
    } finally { disabled(false); }
  });
  cancel.addEventListener('click', async () => {
    if (busy) return;
    disabled(true);
    await revoke();
    commit.hidden = true;
    cancel.hidden = true;
    form.hidden = false;
    status.textContent = 'Opération annulée.';
    disabled(false);
  });
  commit.addEventListener('click', async () => {
    if (busy || !transaction) return;
    disabled(true);
    status.textContent = 'Préparation des accès en cours…';
    try {
      const result = await call('commit', {transaction});
      if (result.status !== 'COMPLETE') throw new Error('REFUSED');
      transaction = null;
      status.textContent = 'Les accès techniques sont prêts. Vous pouvez fermer cette page.';
    } catch (_) {
      await revoke();
      status.textContent = 'La préparation n’a pas abouti. Le relais technique doit vérifier le résultat avant une nouvelle tentative.';
    } finally { commit.hidden = true; cancel.hidden = true; }
  });
})();
