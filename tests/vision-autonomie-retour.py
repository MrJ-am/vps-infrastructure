"""Essayer le retour SQL réel en PostgreSQL jetable, jamais en production."""
import importlib.util
import json
import subprocess
from pathlib import Path

source = Path('application')
spec = importlib.util.spec_from_file_location('deployer', 'scripts/vision-autonomie-deployer.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def sql(base, texte, compte='postgres'):
    return subprocess.check_output(['psql', '-XAtq', '-v', 'ON_ERROR_STOP=1', '--file=-'], input=texte.encode())

m.psql = sql
sql('test', 'CREATE EXTENSION vector;')
for p in sorted((source / 'migrations').glob('*.sql')):
    if int(p.name[:3]) <= 16:
        sql('test', p.read_text())
sql('test', "INSERT INTO vision_profils(utilisateur,intervalle_jours,budget,questions_typiques) VALUES('test-retour',120,4,12);")
ancien = m.fonctions('test')
assert sql('test', 'SELECT vision_revision_contrat()').strip() == b'6'
m.migration_sequentielle(source, 'test')
p = json.loads(sql('test', "SELECT vision_politique('test-retour')"))
assert (p['intervalle_jours'], p['budget'], p['questions_typiques'], p['duree_seance_courte_minutes']) == (120, 4, 12, 60)
# Une écriture postérieure à la publication doit survivre au retour.
sql('test', "UPDATE vision_profils SET duree_seance_courte_minutes=45,version=version+1 WHERE utilisateur='test-retour';")
avant = sql('test', "SELECT to_jsonb(p) FROM vision_profils p WHERE utilisateur='test-retour'")
sql('test', 'BEGIN;\n' + ancien + '\nCOMMIT;')
assert sql('test', 'SELECT vision_revision_contrat()').strip() == b'6'
assert sql('test', "SELECT to_jsonb(p) FROM vision_profils p WHERE utilisateur='test-retour'") == avant
m.migration_sequentielle(source, 'test')
assert sql('test', "SELECT to_jsonb(p) FROM vision_profils p WHERE utilisateur='test-retour'") == avant
print('Migration additive, réglages conservés, retour SQL réel et republication : OK.')
