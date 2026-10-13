'use strict';
// Navigateur réel, API pédagogique/Log doublées et explicitement isolées.
// Les garanties de persistance/droits sont qualifiées séparément sur PostgreSQL.
const { chromium, expect } = require('../../M-moire/docs/node_modules/@playwright/test');
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const site = path.join(root, 'interface-audition/dist');
const construction = JSON.parse(fs.readFileSync(path.join(root, 'state/audition-construction.json')));
function sha(p) {return crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');}
function contenus(d) {
  const result={};
  function parcourir(dir) {
    for(const n of fs.readdirSync(dir).sort()) {
      const p=path.join(dir,n), s=fs.lstatSync(p);
      assert.ok(!s.isSymbolicLink(),'Lien dans le candidat');
      if(s.isDirectory()) parcourir(p);
      else if(s.isFile()) result[path.relative(d,p)]=sha(p);
    }
  }
  parcourir(d);return result;
}
assert.deepEqual(contenus(site),construction.fichiers,'Artefact changé après construction');
const app=path.join(root,'interface-audition');
assert.deepEqual(contenus(path.join(app,'src')),construction.sources.application,'Sources applicatives différentes');
assert.deepEqual(contenus(path.join(app,'tests')),construction.sources.tests,'Tests Elm différents');
for(const [n,k] of [['index.html','bootstrap'],['pont.js','interop'],['elm.json','elm_json']])
  assert.equal(sha(path.join(app,n)),construction.sources[k],'Entrée différente : '+n);
const verrou=JSON.parse(fs.readFileSync(path.join(root,'assemblage/manifest.json'))).frontends_infrastructure.audition;
assert.equal(verrou.revision_style,construction.sources.style);
assert.equal(verrou.revision_signature,construction.sources.signature);
let assertions = 0;
function oui(v) { assert.ok(v); assertions++; }
const activite = { id: 'a1', groupe: 'g1', revision: 1, nature: 'activite', document: {
  titre: 'Le carré d’un réel', consigne: 'Justifier $x^2 \\geq 0$ sans négliger zéro.',
  attendus: [{id:'attendu-1',texte:'Justifier le signe'}],
  criteres: [{id:'critere-1',attendu:'attendu-1',texte:'Traiter zéro et les deux signes',maximum:2}]
}};
const affectation = { id:'f1',revision:1,groupe:'g1',document:{activite:'a1',eleves:['alice'],echeance:1792000000}};
function seance() { return {seance:{id:'s1',revision:1,groupe:'g1',document:{eleve:'alice',activite:'a1',activite_version:1,etat:'en_cours',tentatives:[],rectifications:[]}},
  activite,activite_version:1,version_actuelle:1,contexte_modifie:false,traces:{elements:[],total:0,suivant:null}}; }

(async () => {
  const server = http.createServer((req,res) => {
    const file = path.join(site, decodeURIComponent(new URL(req.url,'http://localhost').pathname));
    const cible = file.endsWith('/') ? file + 'index.html' : file;
    if (!cible.startsWith(site + path.sep) || !fs.existsSync(cible)) {res.writeHead(404);res.end();return;}
    const types = {'.html':'text/html','.js':'text/javascript','.css':'text/css','.svg':'image/svg+xml','.ttf':'font/ttf','.woff2':'font/woff2'};
    res.setHeader('Content-Type', types[path.extname(cible)] || 'application/octet-stream');
    fs.createReadStream(cible).pipe(res);
  });
  await new Promise(resolve => server.listen(0,'127.0.0.1',resolve));
  const origin = 'http://127.0.0.1:' + server.address().port;
  const browser = await chromium.launch({executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE || '/usr/bin/chromium', headless:true, args:['--no-sandbox']});
  try {
    for (const width of [320,768,1440]) {
      const p = await browser.newPage({viewport:{width,height:900},reducedMotion:'reduce'});
      const erreurs=[];p.on('pageerror',e=>erreurs.push(e.message));
      await p.route('**/auth/session',r=>r.fulfill({status:401,contentType:'application/json',body:'{}'}));
      await p.goto(origin);
      await expect(p.getByText('Comprendre ce que chacun sait faire',{exact:true})).toBeVisible();
      await expect(p.getByRole('img',{name:'Logo Audition'})).toBeVisible();
      oui(await p.evaluate(()=>document.fonts.check('28px MrJamEcriture')));
      oui(await p.evaluate(()=>document.documentElement.scrollWidth <= innerWidth));
      await expect(p.getByText('Erreur :', {exact:true})).toHaveCount(0);
      await p.getByRole('button',{name:'Aide',exact:true}).focus();
      await p.keyboard.press('Enter');
      await expect(p.getByText('Connecter votre LLM',{exact:true})).toBeVisible();
      await p.getByRole('button',{name:'Accueil',exact:true}).click();
      const detail = p.locator('[aria-controls="details-suivi"]');
      for (let n=0;n<12;n++) await detail.evaluate(e=>e.click());
      await expect(detail).toHaveAttribute('aria-expanded','false');
      await detail.click();await expect(detail).toHaveAttribute('aria-expanded','true');
      oui(erreurs.length===0);
      if (width===320) await p.screenshot({path:path.join(root,'state/audition-public-mobile.png'),fullPage:true});
      await p.close();
    }
    for (const acteur of ['enseignant','eleve','admin']) {
      const p=await browser.newPage({viewport:{width:390,height:844}});
      const ecritures=[];let conflit=true;let revision=1;
      const context={acteur:acteur==='eleve'?'alice':acteur,administrateur:acteur==='admin',
        elements:[{id:'g1',nom:'Classe isolée',role:acteur}],total:1,suivant:null};
      await p.route('**/auth/session',r=>r.fulfill({json:{username:context.acteur,csrf:'CSRF_FIXTURE_NE_DOIT_PAS_ENTRER_DANS_ELM'}}));
      await p.route('**/auth/oauth-demande?*',r=>r.fulfill({json:{id:'demande',client:'Tuteur de test',redirect_uri:origin+'/retour',scope:'audition:mcp'}}));
      await p.route('**/auth/oauth-consentement',r=>r.fulfill({json:{redirection:origin+'/retour'}}));
      await p.route('**/api/audition/*',async route=>{
        const op=route.request().url().split('/').pop();const q=route.request().postDataJSON();
        if (q.cle) ecritures.push({op,q});
        let d={confirme:true};let status=200;
        if(op==='contexte')d=context;
        if(op==='preparations')d={elements:[{...activite,revision}],total:1,suivant:null,cours:[],eleves:[{acteur:'alice',role:'eleve'}]};
        if(op==='travaux')d={elements:[{activite,affectation,seance:null}],total:1,suivant:null};
        if(op==='retrouver')d={id:'s1',nature:'seance',groupe:'g1'};
        if(op==='ouvrir_seance'||op==='consulter_seance')d=seance();
        if(op==='rapport')d={elements:[{eleve:'alice',activite:'a1',activite_version:1,titre:activite.document.titre,attendus:activite.document.attendus,criteres:activite.document.criteres,observations:[],seance:{id:'s1'}}],total:1,suivant:null,difficultes:[],indicateurs:{elements:[]},methode:'Non observé reste distinct de l’échec.'};
        if(op==='membres')d={elements:[{acteur:'alice',role:'eleve'}],total:1,suivant:null};
        if(op==='activite'){
          if(conflit){status=409;d={erreur:'conflit_revision'};conflit=false;}
          else {revision++;d={...activite,revision,document:q.document};}
        }
        await route.fulfill({status,json:d});
      });
      await p.goto(origin+'/#'+(acteur==='enseignant'?'preparer':acteur==='eleve'?'eleve':'administration'));
      if(acteur==='enseignant'){
        const titre=p.getByLabel("Titre de l'activité",{exact:true});
        await titre.fill('Une saisie conservée');
        await expect(titre).toHaveValue('Une saisie conservée');
        await p.getByLabel('Consigne — texte et $TeX$',{exact:true}).fill('Établir $x^2 \\geq 0$. <script>n’est que du texte</script>');
        await p.getByLabel("Attendus — un par ligne",{exact:true}).fill('Raisonner');
        await p.getByLabel('Critère 1',{exact:true}).fill('Justifier les deux signes');
        await expect(titre).toHaveValue('Une saisie conservée');
        await p.getByRole('button',{name:"Enregistrer l'activité",exact:true}).click();
        await expect(p.getByText('Une modification a été enregistrée entre-temps.',{exact:false})).toBeVisible();
        await expect(titre).toHaveValue('Une saisie conservée').catch(async e=>{await p.screenshot({path:path.join(root,'state/audition-conflit.png'),fullPage:true});throw new Error('Conflit conserve la saisie : requête '+JSON.stringify(ecritures)+' '+e.message);});
        await p.getByRole('button',{name:'Réessayer après vérification',exact:true}).click();
        await expect(p.getByText('Enregistré par le serveur.',{exact:true})).toBeVisible();
        oui(ecritures.length===2 && ecritures[0].q.cle===ecritures[1].q.cle);
        oui(JSON.stringify(ecritures[0].q)===JSON.stringify(ecritures[1].q));
        await p.getByRole('button',{name:'Aide',exact:true}).click();
        await p.getByRole('button',{name:'Préparer',exact:true}).click();
        await expect(titre).toHaveValue('Une saisie conservée');
        await p.getByRole('button',{name:'Suivre la classe',exact:true}).click();
        await expect(p.getByText('Non observé',{exact:true})).toBeVisible();
        await p.getByRole('button',{name:'alice — Le carré d’un réel',exact:true}).click();
        await expect(p.getByText('La séance et son cadre',{exact:true})).toBeVisible();
        await p.getByLabel("Justification de l'annotation ou rectification",{exact:true}).fill('Saisie en cours de suivi');
        await p.clock.install();await p.clock.fastForward(22000);
        await expect(p.getByLabel("Justification de l'annotation ou rectification",{exact:true})).toHaveValue('Saisie en cours de suivi');
        oui(await p.evaluate(()=>document.querySelectorAll('script script').length===0));
      } else if(acteur==='eleve'){
        await p.getByRole('button',{name:'Commencer',exact:true}).click();
        await expect(p.getByText('La séance et son cadre',{exact:true})).toBeVisible();
        await expect(p.getByText('Aucune production enregistrée.',{exact:false})).toBeVisible();
        await expect(p.getByRole('button',{name:'Administration',exact:true})).toHaveCount(0);
        await p.goto(origin+'/#autorisation-mcp=demande');
        await expect(p.getByText('Autoriser votre tuteur',{exact:true})).toBeVisible();
        await expect(p.getByText('Tuteur de test',{exact:false})).toBeVisible();
      } else {
        await expect(p.getByText('Groupes et habilitations',{exact:true})).toBeVisible();
        await expect(p.getByRole('button',{name:'Suivre la classe',exact:true})).toHaveCount(0);
        await expect(p.getByRole('button',{name:'Préparer',exact:true})).toHaveCount(0);
      }
      const largeur = await p.evaluate(()=>({vue:document.documentElement.scrollWidth,ecran:innerWidth,
        debordements:Array.from(document.querySelectorAll('body *')).filter(e=>e.getBoundingClientRect().right>innerWidth+1).slice(-5).map(e=>({tag:e.tagName,texte:e.textContent.slice(0,90),largeur:e.getBoundingClientRect().width}))}));
      if(largeur.vue>largeur.ecran){await p.screenshot({path:path.join(root,'state/audition-debordement-'+acteur+'.png'),fullPage:true});throw new Error('Débordement '+acteur+' '+JSON.stringify(largeur));}
      oui(largeur.vue<=largeur.ecran);
      await p.close();
    }
    const rapport={format:1,chromium:browser.version(),assertions,parcours:['public 320/768/1440','clavier','réduction','interruptions/inversions','enseignant brouillon/conflit/rejeu/retour','élève reprise/consentement','administration limitée'],
      api:'doubles isolés, aucune preuve de connexion réelle à Log ou à un fournisseur LLM',ensemble_sha256:construction.ensemble_sha256,publication:false};
    fs.writeFileSync(path.join(root,'state/audition-navigateur.json'),JSON.stringify(rapport,null,2)+'\n');
    process.stdout.write(JSON.stringify(rapport)+'\n');
  } finally {await browser.close();await new Promise(resolve=>server.close(resolve));}
})().catch(e=>{process.stderr.write(e.stack+'\n');process.exitCode=1;});
