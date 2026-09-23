"use strict";
const element = id => document.getElementById(id);
let csrf = "";
async function requete(action, donnees) {
    const options = { credentials: "same-origin", cache: "no-store" };
    if (action) Object.assign(options, {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
        body: JSON.stringify({ action, ...donnees })
    });
    const reponse = await fetch("/auth/access-tokens", options);
    if (!reponse.ok) throw new Error(reponse.status === 401
        ? "Connectez-vous dans Vision, puis revenez sur cette page."
        : "L’opération a échoué. Rechargez la page avant de réessayer.");
    return reponse.json();
}
const date = valeur => new Date(valeur * 1000).toLocaleString("fr-FR");
function afficher(liste) {
    const conteneur = element("tokens");
    conteneur.replaceChildren();
    if (!liste.length) {
        const p = document.createElement("p"); p.textContent = "Aucun token créé."; conteneur.append(p); return;
    }
    for (const t of liste) {
        const ligne=document.createElement("div"); ligne.className="ligne";
        const info=document.createElement("div");
        const nom=document.createElement("strong"); nom.textContent=t.name;
        const meta=document.createElement("div"); meta.className="meta";
        meta.textContent = "Créé le " + date(t.createdAt) + " · " +
            (t.active ? "actif jusqu’au " + date(t.expiresAt)
             : t.revokedAt ? "révoqué le " + date(t.revokedAt) : "expiré le " + date(t.expiresAt));
        info.append(nom,meta); ligne.append(info);
        if (t.active) {
            const bouton=document.createElement("button"); bouton.type="button"; bouton.className="danger";
            bouton.textContent="Révoquer"; bouton.onclick=()=>revoquer(t.id,t.name); ligne.append(bouton);
        }
        conteneur.append(ligne);
    }
}
async function charger() { const r=await requete(); afficher(r.tokens || []); }
async function creer() {
    const nom=element("nom").value.trim();
    if (!nom) { element("etat").textContent="Donnez un nom à ce token."; element("nom").focus(); return; }
    element("creer").disabled=true; element("secret").hidden=true; element("token").value="";
    try {
        const r=await requete("creer",{name:nom});
        element("token").value=r.token; element("secret").hidden=false;
        element("etat").textContent="Token « "+r.name+" » créé. Copiez-le maintenant.";
        element("nom").value=""; await charger();
    } catch(e) { element("etat").textContent=e.message; }
    finally { element("creer").disabled=false; }
}
async function revoquer(id,nom) {
    if (!confirm("Révoquer le token « "+nom+" » ? Le client qui l’utilise perdra immédiatement l’accès.")) return;
    try { const r=await requete("revoquer",{id}); afficher(r.tokens||[]); element("etat").textContent="Token « "+nom+" » révoqué."; }
    catch(e) { element("etat").textContent=e.message; }
}
element("creer").onclick=creer;
element("copier").onclick=async()=>{
    try { await navigator.clipboard.writeText(element("token").value); element("etat").textContent="Token copié."; }
    catch(_){ element("token").focus(); element("token").select(); element("etat").textContent="Sélectionnez puis copiez le token."; }
};
window.addEventListener("pagehide",()=>{ element("token").value=""; element("secret").hidden=true; });
(async()=>{
    try {
        const session=await fetch("/auth/session",{credentials:"same-origin",cache:"no-store"});
        if(!session.ok) throw new Error("Connectez-vous dans Vision, puis revenez sur cette page.");
        csrf=(await session.json()).csrf; await charger();
        element("gestion").hidden=false; element("historique").hidden=false; element("etat").textContent="Gestion des tokens d’accès.";
    } catch(e){ element("etat").textContent=e.message; }
})();