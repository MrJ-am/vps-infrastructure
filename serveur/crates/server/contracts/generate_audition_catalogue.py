"""Literal port of the pinned Lisp catalogue generator; input is code only."""
import hashlib
import json
from pathlib import Path
import re
import sys


def pinned(path, expected):
    data = Path(path).read_bytes()
    actual = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
    if actual != expected:
        raise SystemExit("SOURCE_BLOB_MISMATCH")
    return data.decode()


def text(maximum):
    return {"type": "string", "maxLength": maximum}


def integer(minimum=0, maximum=None):
    result = {"type": "integer", "minimum": minimum}
    if maximum is not None:
        result["maximum"] = maximum
    return result


def array(items, maximum):
    return {"type": "array", "items": items, "maxItems": maximum}


def closed(props, required):
    return {"type": "object", "additionalProperties": False, "properties": props, "required": required}


def enum(values):
    return {"type": "string", "enum": values}


STATES = ["non_observe", "en_cours", "difficulte", "reussite_aidee", "reussite_autonome"]
OBSERVATION = closed({"critere": text(64), "etat": enum(STATES), "justification": text(4000), "points": {"type": "number", "minimum": 0}, "incertitude": text(2000)}, ["critere", "etat", "justification"])
AID = closed({"nature": enum(["indice", "explication", "correction", "solution"]), "contenu": text(8000), "activite_a": integer(0, 4102444800)}, ["nature", "contenu", "activite_a"])
EXPECTED = closed({"id": text(64), "texte": text(2000)}, ["id", "texte"])
CRITERION = closed({"id": text(64), "attendu": text(64), "texte": text(2000), "maximum": {"type": "number", "exclusiveMinimum": 0, "exclusiveMaximum": 1001}}, ["id", "attendu", "texte", "maximum"])
DOCUMENT = {"oneOf": [closed({"titre": text(200), "contenu": text(32000)}, ["titre", "contenu"]), closed({"titre": text(200), "consigne": text(16000), "attendus": array(EXPECTED, 32), "criteres": array(CRITERION, 64), "cours": text(64), "cours_version": integer(1), "corrige": text(16000), "publication_corrige": integer(0, 4102444800), "type": enum(["ouverte", "qcm"]), "propositions": integer(2, 100)}, ["titre", "consigne", "attendus", "criteres"])]}


def field(name):
    if name == "document":
        return DOCUMENT
    if name == "aides":
        return array(AID, 32)
    if name == "observations":
        return array(OBSERVATION, 64)
    if name == "role":
        return enum(["enseignant", "eleve", "retirer"])
    if name == "action":
        return enum(["reprendre", "interrompre", "terminer"])
    if name == "etat":
        return enum(STATES)
    if name in ["revision", "activite_version", "politique_version", "echeance", "activite_a", "offset", "limite"]:
        return {**integer(0 if name in ["offset", "echeance", "activite_a"] else 1), "description": "Secondes Unix UTC ; heure de l'activité distincte de la réception." if name in ["echeance", "activite_a"] else "Version serveur ou pagination, jamais à deviner."}
    if name == "observation":
        return text(64)
    if name == "eleves":
        return array(text(64), 500)
    if name == "points":
        return {"type": "number", "minimum": 0}
    return text(16000 if name in ["production", "consigne", "justification", "annotation"] else 200)


def output(name):
    obj = {"type": "object"}
    optional = {"oneOf": [obj, {"type": "null"}]}
    if name in ["contexte", "membres", "preparations", "travaux", "rapport"]:
        return {"type": "object", "required": ["elements", "total", "suivant"], "properties": {"elements": array(obj, 100), "total": integer(), "suivant": {"oneOf": [integer(), {"type": "null"}]}, "acteur": text(64), "administrateur": {"type": "boolean"}, "politique": obj, "indicateurs": obj, "methode": text(2000)}, "description": "Page bornée. Conserver les identifiants/versions et suivre suivant ; total ne compte pas des réussites."}
    if name in ["ouvrir_seance", "consulter_seance", "adopter_contexte", "consigner", "transition", "rectifier"]:
        return {"type": "object", "required": ["seance", "activite", "politique", "contexte_modifie"], "properties": {"seance": obj, "activite": obj, "cours": optional, "politique": obj, "activite_version": integer(), "version_actuelle": integer(), "contexte_modifie": {"type": "boolean"}, "nouvelle_activite": optional, "traces": obj, "actions_suivantes": array(text(80), 20)}, "description": "Séance contient id,revision,document. Lire politique.version et les versions effectives avant une écriture ; traces est une page."}
    if name in ["cours", "activite", "affecter"]:
        return {"type": "object", "required": ["id", "groupe", "nature", "revision", "document"], "properties": {"id": text(64), "groupe": text(64), "nature": text(64), "revision": integer(), "document": obj, "url": text(512)}, "description": "Version enregistrée. Les cours/activités proposés par MCP ont document.validee=false, sans prescription implicite."}
    return {"type": "object", "properties": {"id": text(64), "confirme": {"type": "boolean"}, "supprime": {"type": "boolean"}, "objet": optional, "url": text(512)}, "description": "Résultat métier. Une erreur MCP a isError=true et structuredContent {erreur,statut,details,reprise}."}


def main():
    if len(sys.argv) != 3:
        raise SystemExit("usage: generate_audition_catalogue.py pinned-mcp.lisp pinned-services.lisp")
    source = pinned(sys.argv[1], "ffc6830e122d279243ca7b90f979b16bca6062ac")
    services = pinned(sys.argv[2], "2ea12f2bb086f1fcb9dbe75809e4ff4b7e01711a")
    operations = re.findall(r'\("([a-z_]+)" :(lecture|admin|enseignant|eleve) (nil|\([^\n]*?\)) (nil|\([^\n]*?\))\)', services.split("(defun definition")[0])
    if len(operations) != 20:
        raise SystemExit("OPERATION_TABLE_MISMATCH")
    descriptions = dict(re.findall(r'\("([a-z_]+)" \. "([^"\n]*)"\)', source))
    catalogue = []
    for name, role, required, optional in operations:
        required = re.findall(r'"([a-z_]+)"', required)
        optional = re.findall(r'"([a-z_]+)"', optional)
        catalogue.append({"name": name, "description": descriptions.get(name, "Opération métier autorisée côté serveur, selon les rattachements. Consulter le guide canonique https://audition.mrj.am/#aide."), "inputSchema": closed({key: field(key) for key in required + optional}, required), "outputSchema": output(name), "annotations": {"readOnlyHint": "cle" not in required, "idempotentHint": True, "destructiveHint": name == "supprimer_groupe", "openWorldHint": False}, "_meta": {"droit": role}})
    root = Path(__file__).parent
    path = root / "audition-catalogue.json"
    path.write_text(json.dumps(catalogue, ensure_ascii=False, indent=2) + "\n")
    provenance = {"schema_version": 1, "source_repository": "MrJ-am/vps-infrastructure", "source_commit": "c6459ae215b0e4e8b1350b02222ad21af41db836", "source_blobs": {"lisp/audition/mcp.lisp": "ffc6830e122d279243ca7b90f979b16bca6062ac", "lisp/audition/services.lisp": "2ea12f2bb086f1fcb9dbe75809e4ff4b7e01711a"}, "method": "Literal translation of the catalogue generator and operation table; no production response used", "tools": 20, "catalogue_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (root / "audition-catalogue.provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
