"use strict";
const element = id => document.getElementById(id);
let csrf = "";
async function requete(chemin, action) {
    const options = { credentials: "same-origin", cache: "no-store" };
    if (action) Object.assign(options, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ action })
    });
    const reponse = await fetch(chemin, options);
    if (!reponse.ok) throw new Error(reponse.status === 401
        ? "Connectez-vous dans Vision, puis revenez sur cette page."
        : "L’opération a échoué. Rechargez la page avant de réessayer.");
    return reponse.json();
}
function afficher(valeur) {
    const actif = Boolean(valeur.active || valeur.token);
    element("etat").textContent = actif
        ? "Token actif jusqu’au " + new Date(valeur.expiresAt * 1000).toLocaleDateString("fr-FR") + "."
        : "Aucun token actif.";
    element("creer").textContent = actif ? "Remplacer le token" : "Créer le token";
    element("revoquer").hidden = !actif;
    element("token").value = valeur.token || "";
    element("secret").hidden = !valeur.token;
}
async function modifier(action) {
    if (action === "creer" && !element("revoquer").hidden &&
        !confirm("Remplacer le token désactivera immédiatement celui utilisé dans Mistral. Continuer ?")) return;
    element("creer").disabled = element("revoquer").disabled = true;
    element("token").value = "";
    element("secret").hidden = true;
    try { afficher(await requete("/auth/mcp-token", action)); }
    catch (erreur) { element("etat").textContent = erreur.message; }
    finally { element("creer").disabled = element("revoquer").disabled = false; }
}
element("creer").onclick = () => modifier("creer");
element("revoquer").onclick = () => modifier("revoquer");
element("copier").onclick = async () => {
    try { await navigator.clipboard.writeText(element("token").value); element("etat").textContent = "Token copié."; }
    catch (_) { element("token").focus(); element("token").select(); element("etat").textContent = "Sélectionnez puis copiez le token."; }
};
window.addEventListener("pagehide", () => { element("token").value = ""; element("secret").hidden = true; });
(async () => {
    try {
        const session = await requete("/auth/session"); csrf = session.csrf;
        afficher(await requete("/auth/mcp-token")); element("gestion").hidden = false;
    } catch (erreur) { element("etat").textContent = erreur.message; }
})();
