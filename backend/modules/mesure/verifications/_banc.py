"""Banc d'essai commun : backend Flask sur une copie TEMPORAIRE de SmartGrid-1.owl.

La copie de travail de l'équipe (backend/data/smartgrid.owl) n'est jamais ouverte :
store.DATA_OWL est redirigé avant le chargement de l'application.
"""
import json
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[3]
SOURCE_OWL = BACKEND.parent / "SmartGrid-1.owl"
sys.path.insert(0, str(BACKEND))

import store  # noqa: E402


def banc(dossier=None):
    """Charge une copie de SmartGrid-1.owl dans un dossier temporaire et renvoie (app, client, dossier)."""
    dossier = Path(dossier or tempfile.mkdtemp(prefix="verif_mesure_"))
    store.DATA_OWL = dossier / "smartgrid.owl"
    store.load(reset=not store.DATA_OWL.exists())
    import app  # noqa: E402  (app.py appelle store.load() sur la copie temporaire)
    return app.app, app.app.test_client(), dossier


class Verif:
    """Compte les vérifications réussies / échouées et affiche chaque résultat."""

    def __init__(self):
        self.ok = self.ko = 0

    def __call__(self, condition, message):
        if condition:
            self.ok += 1
            print(f"  [OK] {message}")
        else:
            self.ko += 1
            print(f"  [ÉCHEC] {message}")
        return condition

    def fin(self):
        print(f"\n{self.ok} vérification(s) réussie(s), {self.ko} échec(s)")
        return 1 if self.ko else 0


def appel(client, methode, chemin, corps=None):
    r = getattr(client, methode.lower())(chemin, json=corps)
    return r.status_code, r.get_json()


def montrer(obj, n=400):
    return json.dumps(obj, ensure_ascii=False)[:n]
