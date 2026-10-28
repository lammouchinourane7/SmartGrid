"""Banc d'essai : backend Flask sur une COPIE TEMPORAIRE d'un graphe (jamais backend/data/smartgrid.owl).

Par défaut la copie est faite depuis backend/data/smartgrid.owl (état courant, avec les éventuelles
données ajoutées par l'équipe), ou depuis le fichier passé en argument.
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
COURANT = BACKEND / "data" / "smartgrid.owl"
sys.path.insert(0, str(BACKEND))

import store  # noqa: E402


def banc(source=None, dossier=None):
    """Copie `source` (ou le graphe courant) dans un dossier temporaire et charge l'application dessus."""
    dossier = Path(dossier or tempfile.mkdtemp(prefix="verif_production_"))
    cible = dossier / "smartgrid.owl"
    if not cible.exists():
        shutil.copyfile(source or (COURANT if COURANT.exists() else BACKEND.parent / "SmartGrid-1.owl"), cible)
    store.DATA_OWL = cible
    import app  # noqa: E402  (app.py appelle store.load() sur la copie)
    return app.app, app.app.test_client(), dossier


class Verif:
    def __init__(self):
        self.ok = self.ko = 0

    def __call__(self, condition, message):
        print(f"  [{'OK' if condition else 'ÉCHEC'}] {message}")
        if condition:
            self.ok += 1
        else:
            self.ko += 1
        return condition

    def fin(self):
        print(f"\n{self.ok} vérification(s) réussie(s), {self.ko} échec(s)")
        return 1 if self.ko else 0


def appel(client, methode, chemin, corps=None):
    r = getattr(client, methode.lower())(chemin, json=corps)
    return r.status_code, r.get_json()


def montrer(obj, n=300):
    return json.dumps(obj, ensure_ascii=False)[:n]
