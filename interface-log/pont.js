/* Transport et WebAuthn uniquement : les vues et transitions appartiennent à Elm. */
(() => {
  'use strict';
  const app = Elm.Main.init({node: document.getElementById('application')});
  MrJamAnimations.relier(app.ports.mouvementReduit);
  let credential = null, consent = null, sequence = Promise.resolve(), verification = 0, delai = null;
  const query = Object.fromEntries(new URLSearchParams(location.search));
  const oauth = location.pathname === '/ui/oauth2' ? query : null;
  let retourReauth = null;
  addEventListener('pagehide', () => {credential = null; consent = null; verification++; clearTimeout(delai);});
  addEventListener('pageshow', event => {if (event.persisted) location.reload();});
  function notifier(action, status, document) { app.ports.recevoir.send({action, status, document}); }
  function urlSure(url) {
    const u = new URL(url);
    if (u.protocol !== 'https:' || u.username || u.password) throw new Error('Retour non autorisé');
    location.assign(u.href);
  }
  async function api(action, document = null, parametre = null) {
    const r = await fetch('/presentation/api', {method: 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: {'Content-Type': 'application/json'}, body: JSON.stringify({action, document, parametre})});
    const data = await r.json();
    return {status: r.status, data};
  }
  function binaire(value) { return Uint8Array.from(atob(value.replace(/-/g, '+').replace(/_/g, '/')), c => c.charCodeAt(0)); }
  function encode(value) {
    return btoa(String.fromCharCode(...new Uint8Array(value))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  }
  function assertion(c) {
    return {id: c.id, rawId: encode(c.rawId), type: c.type, response: {
      authenticatorData: encode(c.response.authenticatorData), clientDataJSON: encode(c.response.clientDataJSON),
      signature: encode(c.response.signature), userHandle: c.response.userHandle ? encode(c.response.userHandle) : null},
      extensions: c.getClientExtensionResults()};
  }
  async function obtenir(challenge) {
    const publicKey = structuredClone(challenge.publicKey);
    publicKey.challenge = binaire(publicKey.challenge);
    if (publicKey.allowCredentials) publicKey.allowCredentials.forEach(c => {c.id = binaire(c.id);});
    return assertion(await navigator.credentials.get({publicKey}));
  }
  async function creer(challenge) {
    const publicKey = structuredClone(challenge.publicKey);
    publicKey.challenge = binaire(publicKey.challenge); publicKey.user.id = binaire(publicKey.user.id);
    if (publicKey.excludeCredentials) publicKey.excludeCredentials.forEach(c => {c.id = binaire(c.id);});
    const c = await navigator.credentials.create({publicKey});
    return {id: c.id, rawId: encode(c.rawId), type: c.type, response: {
      attestationObject: encode(c.response.attestationObject), clientDataJSON: encode(c.response.clientDataJSON),
      transports: c.response.getTransports ? c.response.getTransports() : []}, extensions: c.getClientExtensionResults()};
  }
  function base32(bytes) {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567'; let bits = 0, valeur = 0, sortie = '';
    for (const octet of bytes) {valeur = (valeur << 8) | octet; bits += 8; while (bits >= 5) {bits -= 5; sortie += alphabet[(valeur >>> bits) & 31];}}
    if (bits) sortie += alphabet[(valeur << (5 - bits)) & 31]; return sortie;
  }
  function statutCredential(data) {
    if (data && data.mfaregstate && data.mfaregstate.TotpCheck) {
      const s = data.mfaregstate.TotpCheck; data.totp_secret = base32(s.secret);
      // Ne pas conserver le tableau de secret en double dans le modèle.
      delete data.mfaregstate.TotpCheck.secret;
    }
    return data;
  }
  async function apresConnexion() {
    if (retourReauth) {const action = retourReauth; retourReauth = null; return executer({action, verificationRecente: true});}
    if (oauth) {
      const r = await api('oauth', oauth);
      if (r.status === 401) {notifier('connexion', 200, null); return;}
      if (r.data && r.data.redirection) {urlSure(r.data.redirection); return;}
      if (r.data && r.data.ConsentRequested) {
        consent = r.data.ConsentRequested.consent_token;
        delete r.data.ConsentRequested.consent_token;
      }
      notifier('oauth', r.status, r.data); return;
    }
    const r = await api('profil');
    if (r.status === 401) notifier('connexion', 200, null);
    else {if (r.status === 200 && Number.isInteger(r.data.expiry)) r.data.expiration_log = new Date(r.data.expiry * 1000).toISOString(); notifier('profil', r.status, r.data);}
  }
  async function executer(req) {
    let action = req.action, document = req.document ?? null, parametre = null;
    if (action === 'initialiser') {
      if (query.token && location.pathname.startsWith('/ui/reset')) {
        document = query.token; delete query.token; history.replaceState(null, '', '/ui/reset'); action = 'recuperer';
      } else {const r = await api('profil'); if (r.status === 200) return apresConnexion(); notifier('connexion', 200, null); return;}
    }
    if (action === 'apres-connexion') return apresConnexion();
    if (action === 'ouvrir' && !req.verificationRecente) {
      retourReauth = 'ouvrir'; const r = await api('reauth', 'cookie');
      notifier('reauth', r.status, r.data); return;
    }
    if (action === 'auth-passkey') {
      const defis = document.state.continue, defi = defis.find(d => typeof d === 'object' && (d.passkey || d.securitykey));
      if (!defi) throw new Error('Défi absent');
      const type = defi.passkey ? 'passkey' : 'securitykey';
      document = {step: {cred: {[type]: await obtenir(defi[type])}}}; action = 'auth';
    }
    if (action === 'creer-passkey') {
      if (!credential) throw new Error('Session de modification absente');
      let r = await api('modifier', ['passkeyinit', credential]);
      if (r.status !== 200) {notifier(action, r.status, null); return;}
      r = await api('modifier', [{passkeyfinish: [req.nom, await creer(r.data.mfaregstate.Passkey)]}, credential]);
      notifier(action, r.status, statutCredential(r.data)); return;
    }
    if (['statut', 'enregistrer', 'annuler', 'modifier'].includes(action)) {
      if (!credential) throw new Error('Session de modification absente');
      document = action === 'modifier' ? [document, credential] : credential;
    }
    if (action === 'consentir' || action === 'refuser') {
      if (!consent) throw new Error('Consentement absent'); document = consent;
    }
    if (action.startsWith('revoquer:')) {parametre = action.slice('revoquer:'.length); action = 'revoquer';}
    if (action.startsWith('retirer-passkey:') || action.startsWith('retirer-totp:')) {
      if (!credential) throw new Error('Session de modification absente');
      const estPasskey = action.startsWith('retirer-passkey:');
      const valeur = action.slice(action.indexOf(':') + 1);
      document = [{[estPasskey ? 'passkeyremove' : 'totpremove']: valeur}, credential]; action = 'modifier';
    }
    const r = await api(action, document, parametre);
    if ((action === 'ouvrir' || action === 'recuperer') && r.status === 200) {
      credential = r.data[0]; notifier(action, r.status, statutCredential(r.data[1])); return;
    }
    if (r.data && r.data.redirection && r.status === 200) {consent = null; urlSure(r.data.redirection); return;}
    if (['enregistrer', 'annuler'].includes(action) && r.status === 200) credential = null;
    if (action === 'deconnexion' && r.status === 200) {notifier('connexion', 200, null); return;}
    if (action === 'revoquer' && r.status === 200) return executer({action: 'sessions'});
    if (action === 'profil' && r.status === 401) {notifier('connexion', 200, null); return;}
    if (action === 'profil' && r.status === 200) r.data.expiration_log = Number.isInteger(r.data.expiry) ? new Date(r.data.expiry * 1000).toISOString() : '';
    if (action === 'sessions' && r.status === 200) r.data.forEach(s => {
      s.debut = new Date(s.issued_at * 1000).toISOString();
      s.expiration = s.state && Number.isInteger(s.state.expiresat) ? new Date(s.state.expiresat * 1000).toISOString() : '';
    });
    notifier(action, r.status, action === 'modifier' ? statutCredential(r.data) : r.data);
  }
  app.ports.demander.subscribe(req => {
    if (req.action === 'force') {
      const n = ++verification; clearTimeout(delai);
      delai = setTimeout(() => {
        sequence = sequence.then(async () => {
          if (n !== verification || !credential) return;
          const r = await api('modifier', [{passwordqualitycheck: req.document}, credential]);
          if (n === verification) notifier('force', r.status, null);
        }).catch(() => {if (n === verification) notifier('force', 503, null);});
      }, 250);
      return;
    }
    sequence = sequence.then(() => executer(req)).catch(() => notifier(req.action, 503, null));
  });
  app.ports.focaliser.subscribe(id => {
    // Browser.element remplace le nœud d'amorçage ; ne pas conserver ce nœud.
    const racine = document.body;
    const chercher = () => document.getElementById(id) || racine.querySelector('input:not([type=hidden]),button');
    let observation = null, expiration = null;
    const trouver = () => {const e = chercher(); if (!e) return; e.focus({preventScroll: true});
      if (observation) observation.disconnect(); clearTimeout(expiration);};
    observation = new MutationObserver(trouver); observation.observe(racine, {childList: true, subtree: true});
    expiration = setTimeout(() => observation.disconnect(), 1000); queueMicrotask(trouver);
  });
})();
