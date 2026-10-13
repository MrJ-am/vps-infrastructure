/* Transport seulement : cookies HttpOnly, CSRF privé au pont, dates UTC,
   idempotence et focus natif. Aucune présentation, animation ou collecte. */
(() => {
  "use strict";
  const app = Elm.Main.init({ node: document.getElementById("application"), flags: {
    route: location.hash, largeur: window.innerWidth,
    reduit: window.matchMedia("(prefers-reduced-motion: reduce)").matches
  } });
  window.MrJamAnimations.relier(app.ports.mouvementReduit, { initiale: false });
  let csrf = null;
  let derniereEcriture = null;
  const lectures = new Set(["contexte", "retrouver", "preparations", "membres", "diagnostic", "travaux", "consulter_seance", "rapport"]);
  const operations = new Set([...lectures, "creer_groupe", "habiliter", "supprimer_groupe", "cours", "activite", "affecter", "ouvrir_seance", "adopter_contexte", "consigner", "transition", "rectifier", "remediation"]);

  function envoyer(operation, statut, document, erreur = "", groupe = "") {
    app.ports.recevoir.send({ operation, statut, document, erreur, groupe });
  }

  function dateUTC(value) {
    if (Number.isInteger(value)) return value;
    const m = typeof value === "string" && /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})$/.exec(value);
    if (!m) throw new Error("date_invalide");
    const n = m.slice(1).map(Number), t = new Date(Date.UTC(n[0], n[1] - 1, n[2], n[3], n[4]));
    if (t.getUTCFullYear() !== n[0] || t.getUTCMonth() !== n[1] - 1 || t.getUTCDate() !== n[2] || t.getUTCHours() !== n[3] || t.getUTCMinutes() !== n[4]) throw new Error("date_invalide");
    return t.getTime() / 1000;
  }

  async function session() {
    const r = await fetch("/auth/session", { credentials: "same-origin", cache: "no-store" });
    if (r.status === 401) { csrf = null; return false; }
    if (!r.ok) throw new Error("reseau");
    const d = await r.json();
    csrf = d.csrf; // Jamais transmis dans les ports, ni dans le modèle Elm.
    return typeof csrf === "string";
  }

  async function appel(operation, document, reprise = false) {
    if (!operations.has(operation)) throw new Error("operation_inconnue");
    const p = JSON.parse(JSON.stringify(document || {}));
    if (p.echeance !== undefined) p.echeance = dateUTC(p.echeance);
    if (p.document && p.document.publication_corrige !== undefined) p.document.publication_corrige = dateUTC(p.document.publication_corrige);
    if (!lectures.has(operation) && !p.cle) p.cle = crypto.randomUUID();
    if (!lectures.has(operation)) derniereEcriture = { operation, document: p };
    if (!csrf || reprise) {
      if (!await session()) { envoyer(operation, 401, {}, "session_expiree"); return; }
    }
    const abort = new AbortController();
    const timeout = setTimeout(() => abort.abort(), 8000); // Délai de transport, pas une horloge de présentation.
    try {
      const r = await fetch("/api/audition/" + operation, { method: "POST", credentials: "same-origin", cache: "no-store",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(p), signal: abort.signal });
      const d = await r.json();
      if (r.ok && !lectures.has(operation)) derniereEcriture = null;
      if (r.status === 401) csrf = null;
      envoyer(operation, r.status, d, r.ok ? "" : d.erreur || "reseau", p.groupe || "");
    } catch (_) {
      envoyer(operation, 503, {}, "reseau", p.groupe || "");
    } finally { clearTimeout(timeout); }
  }

  app.ports.demander.subscribe(async ({ operation, document }) => {
    try {
      if (operation === "initialiser") {
        if (!await session()) { envoyer(operation, 200, {}); return; }
        await appel("contexte", {});
      } else if (operation === "reessayer") {
        if (derniereEcriture) await appel(derniereEcriture.operation, derniereEcriture.document, true);
        else await appel("contexte", {}, true);
      } else if (operation === "deconnexion") {
        const r = await fetch("/auth/logout", { method: "POST", credentials: "same-origin", headers: { "X-CSRF-Token": csrf } });
        if (r.ok) { csrf = null; derniereEcriture = null; location.assign("/"); }
        else envoyer(operation, r.status, {}, "session_expiree");
      } else if (operation === "oauth_demande") {
        const r = await fetch("/auth/oauth-demande?id=" + encodeURIComponent(document.id), { credentials: "same-origin", cache: "no-store" });
        envoyer(operation, r.status, await r.json());
      } else if (operation === "oauth_consentement") {
        const r = await fetch("/auth/oauth-consentement", { method: "POST", credentials: "same-origin", cache: "no-store", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf }, body: JSON.stringify(document) });
        const d = await r.json();
        if (r.ok) location.assign(d.redirection);
        else envoyer(operation, r.status, {}, "session_expiree");
      } else { await appel(operation, document); }
    } catch (e) { envoyer(operation, 400, {}, e.message === "date_invalide" ? "date_invalide" : "reseau"); }
  });
  app.ports.naviguer.subscribe(route => {
    const cible = route.startsWith("#") ? route : "#" + route;
    if (location.hash === cible || (cible === "#" && !location.hash)) app.ports.routeChangee.send(cible);
    else location.hash = cible;
  });
  window.addEventListener("hashchange", () => app.ports.routeChangee.send(location.hash));
  document.addEventListener("visibilitychange", () => app.ports.visible.send(!document.hidden));
})();
