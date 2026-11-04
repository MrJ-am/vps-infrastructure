'use strict';
(() => {
  const form = document.getElementById('login');
  const accessForm = document.getElementById('access-continuation');
  const separate = document.getElementById('separate');
  const status = document.getElementById('status');
  const expiry = document.getElementById('expiry');
  const commit = document.getElementById('commit');
  const cancel = document.getElementById('cancel');
  let transaction = null;
  let deadline = 0;
  let busy = false;
  const from64 = value => Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), ch => ch.charCodeAt(0));
  const to64 = value => btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const expired = () => deadline > 0 && performance.now() >= deadline;
  async function call(action, value) {
    const response = await fetch('./api/' + action, {method: 'POST', credentials: 'omit', cache: 'no-store', redirect: 'error', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(value)});
    if (!response.ok) throw new Error(expired() ? 'EXPIRED' : 'REFUSED');
    const result = await response.json();
    if (Number.isInteger(result.expires_in) && result.expires_in >= 0 && result.expires_in <= 900) {
      deadline = performance.now() + result.expires_in * 1000;
    }
    return result;
  }
  function disabled(value) {
    busy = value;
    for (const container of [form, accessForm]) for (const item of container.elements) item.disabled = value;
    commit.disabled = value;
    cancel.disabled = value;
  }
  async function revoke() {
    if (transaction) {
      try { await call('cancel', {transaction}); } catch (_) { /* Fixed server expiry also revokes its dedicated session. */ }
      transaction = null;
    }
    deadline = 0;
    expiry.textContent = '';
  }
  function reset() {
    form.hidden = false;
    accessForm.hidden = true;
    commit.hidden = true;
    cancel.hidden = true;
  }
  function expiration() {
    commit.hidden = true;
    accessForm.hidden = true;
    status.textContent = 'L’autorisation a expiré. Reprenez l’authentification pour continuer. Si la page est fermée, le relais technique doit la rouvrir.';
    form.hidden = false;
    expiry.textContent = '';
  }
  async function authenticate(result) {
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
    return result;
  }
  async function display(result) {
    if (result.status === 'READY') {
      form.hidden = true;
      accessForm.hidden = true;
      commit.hidden = false;
      cancel.hidden = false;
      status.textContent = 'Authentification et droits vérifiés. Vous pouvez préparer les deux accès techniques.';
    } else if (result.status === 'ACCESS_REQUIRED') {
      form.hidden = true;
      accessForm.hidden = false;
      commit.hidden = true;
      cancel.hidden = false;
      status.textContent = 'Ce compte peut gérer les identités, mais pas les droits d’accès aux adresses courriel. Authentifiez un second compte qui possède ce droit ; la première authentification reste valable.';
    } else if (result.status === 'IDENTITY_RIGHTS_REQUIRED') {
      await revoke();reset();
      const missing = [];
      if (result.permissions?.identity_services !== true) missing.push('gestion des comptes techniques');
      if (result.permissions?.identity_admins !== true) missing.push('administration des identités');
      status.textContent = 'Connexion valide, mais droits manquants : ' + missing.join(' et ') + '. Choisissez un compte disposant de ces droits.';
    } else if (result.status === 'ACCESS_RIGHTS_REQUIRED') {
      await revoke();reset();
      status.textContent = 'Connexion valide, mais le compte choisi ne peut pas gérer les droits d’accès aux adresses courriel. Choisissez un compte disposant de ce droit.';
    } else if (result.status === 'EXPIRED') {
      await revoke();expiration();
    } else {
      throw new Error('REFUSED');
    }
  }
  async function authenticationFailure(error) {
    const ended = error.message === 'EXPIRED' || expired();
    await revoke();reset();
    if (ended) expiration();
    else status.textContent = 'L’authentification n’a pas abouti. Vérifiez le compte choisi et réessayez.';
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
      transaction = result.transaction || null;
      result = await authenticate(result);
      await display(result);
    } catch (error) { await authenticationFailure(error); }
    finally { disabled(false); }
  });
  accessForm.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy || !transaction) return;
    disabled(true);
    try {
      const result = await call('access', {transaction, access: document.getElementById('next-access').value.trim()});
      await display(await authenticate(result));
    } catch (error) { await authenticationFailure(error); }
    finally { disabled(false); }
  });
  cancel.addEventListener('click', async () => {
    if (busy) return;
    disabled(true);
    await revoke();reset();
    status.textContent = 'Opération annulée.';
    disabled(false);
  });
  commit.addEventListener('click', async () => {
    if (busy || !transaction) return;
    if (expired()) { await revoke();expiration();return; }
    disabled(true);
    status.textContent = 'Préparation des accès en cours…';
    let complete = false;
    try {
      const result = await call('commit', {transaction});
      if (result.status === 'COMPLETE') {
        complete = true;
        transaction = null;deadline = 0;expiry.textContent = '';
        status.textContent = 'Les accès techniques sont prêts. Vous pouvez fermer cette page.';
      } else {
        await display(result);
      }
    } catch (_) {
      await revoke();
      status.textContent = 'La préparation n’a pas abouti. Le relais technique dispose d’un diagnostic précis et doit vérifier le résultat avant une nouvelle tentative.';
    } finally {
      commit.hidden = true;
      cancel.hidden = true;
      disabled(false);
      if (complete) { form.hidden = true;accessForm.hidden = true; }
    }
  });
  setInterval(() => {
    if (!transaction || busy || !deadline) return;
    if (expired()) {
      expiration();
      void revoke();
    } else {
      expiry.textContent = 'Autorisation valable encore ' + Math.ceil((deadline - performance.now()) / 1000) + ' secondes.';
    }
  }, 1000);
})();
