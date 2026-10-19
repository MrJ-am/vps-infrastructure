"""Le tutoriel utilise l'environnement Nix réellement livré au serveur commun."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ConfigurationMcp(unittest.TestCase):
    def test_tutoriel_apres_authentification_avec_configuration_deployee(self):
        expression = '''let e=import <nixpkgs/nixos/lib/eval-config.nix> {
          modules=[ %s ];
        }; in e.config.systemd.services.mrjam-metier.environment'''
        resultat = subprocess.run(['nix-instantiate', '--eval', '--strict', '--json',
            '--expr', expression % (ROOT/'tests/log-evaluation-base.nix')],
            capture_output=True, text=True, check=True)
        environnement = json.loads(resultat.stdout)
        self.verifier_tutoriel(environnement)

    def verifier_tutoriel(self, environnement):
        # Aucun DSN/secret de la configuration n'est transmis au processus.
        env = {k:v for k,v in os.environ.items() if not k.startswith('VISION_')}
        env.update({k:v for k,v in environnement.items() if k in (
            'VISION_PUBLIC_MCP_URL', 'VISION_PUBLIC_WEB_URL', 'VISION_MCP_PATH', 'VISION_WEB_PATH')})
        source = Path(os.environ.get('MRJAM_SOURCE_VISION', ROOT.parent/'vision')).resolve()
        programme = '''
(require :asdf)
(require :sb-bsd-sockets)
(asdf:load-asd #p%s)
(asdf:load-system "vision/http")
(let ((vision::*utilisateur* "fixture-locale")
      (vision::*database-executor* (lambda (&rest args)
        (declare (ignore args)) (error "Le tutoriel ne doit pas accéder à une base."))))
  (multiple-value-bind (status reason body)
      (vision::handle-mcp-message "{\\"jsonrpc\\":\\"2.0\\",\\"id\\":41,\\"method\\":\\"tools/call\\",\\"params\\":{\\"name\\":\\"tutoriel\\",\\"arguments\\":{}}}")
    (declare (ignore reason))
    (let* ((reponse (vision::parse-json body))
           (resultat (vision::json-object-get reponse "result"))
           (contenu (vision::json-object-get resultat "structuredContent"))
           (connexion (vision::json-object-get contenu "connexion")))
      (assert (= status 200))
      (assert (eql (vision::json-object-get reponse "id") 41))
      (assert (null (vision::json-object-get reponse "error")))
      (assert (not (eq (vision::json-object-get resultat "isError") :true)))
      (assert (equal (vision::json-object-get connexion "url_mcp") "https://vision.mrj.am/mcp"))
      (assert (equal (vision::json-object-get connexion "gestion_acces") "https://vision.mrj.am/auth/mcp")))))
(format t "MCP_CONFIGURATION_OK~%%")
''' % json.dumps(str(source/'vision.asd'))
        with tempfile.TemporaryDirectory(prefix='vision-mcp-configuration-') as tmp:
            fichier = Path(tmp)/'verifier.lisp'
            fichier.write_text(programme)
            p = subprocess.run([os.environ.get('SBCL', 'sbcl'), '--noinform', '--non-interactive',
                '--load', str(fichier)], env=env, capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr[-2500:])
        self.assertIn('MCP_CONFIGURATION_OK', p.stdout)


if __name__ == '__main__':
    unittest.main()
