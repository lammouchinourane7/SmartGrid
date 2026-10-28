"""Persistance dans un nouveau processus (redémarrage du backend), sur une copie du graphe courant.

    cd backend
    python modules/production/verifications/verif_persistance.py

Processus 1 : crée une source via l'API (écrite dans le fichier par store.update), puis se termine.
Processus 2 : nouvel interpréteur, relit la source, R1 recalculée, la supprime, et compare le
fichier final à la copie de départ par isomorphisme.
"""
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent
SOURCE = {"id": "Verif_Persistance_Eolien", "label": "Éolienne de vérification", "type": "Eolien",
          "puissance": "2.5e3", "date": "2018-03-01", "lignes": ["Ligne_MT_Lac"], "batiments": []}


def ecrire(dossier):
    from _banc import Verif, appel, banc
    _, client, _ = banc(dossier=dossier)
    v = Verif()
    print("--- processus 1 (écriture)")
    code, j = appel(client, "POST", "/api/production/sources", SOURCE)
    v(code == 201, f"POST /api/production/sources → {code} {j.get('id', j.get('error'))}")
    return v.fin()


def relire(dossier):
    from rdflib import Graph
    from rdflib.compare import isomorphic

    from _banc import Verif, appel, banc, store
    _, client, _ = banc(dossier=dossier)
    v = Verif()
    print("--- processus 2 (nouveau processus : graphe relu depuis le fichier)")
    code, j = appel(client, "GET", f"/api/production/sources/{SOURCE['id']}")
    it = j.get("item", {})
    v(code == 200 and it["type"] == "Eolien" and it["puissance"] == 2500.0 and it["date"] == "2018-03-01T00:00:00",
      "source relue : Eolien, 2 500 kW, 2018-03-01")
    v({a["batiment"] for a in it.get("alimentation", [])} == {"Immeuble_Lac", "Centre_Commercial_Lac"},
      "R1/R7 recalculées : Immeuble_Lac (R1) et Centre_Commercial_Lac (R7)")
    code, _ = appel(client, "DELETE", f"/api/production/sources/{SOURCE['id']}")
    v(code == 200, f"DELETE → {code}")
    depart, final = Graph(), Graph()
    depart.parse(Path(dossier) / "depart.owl", format="xml")
    final.parse(store.DATA_OWL, format="xml")
    v(isomorphic(depart, final), f"fichier final isomorphe à la copie de départ ({len(final)} triplets)")
    return v.fin()


def main():
    from _banc import COURANT
    dossier = Path(tempfile.mkdtemp(prefix="verif_production_persistance_"))
    shutil.copyfile(COURANT, dossier / "smartgrid.owl")
    shutil.copyfile(COURANT, dossier / "depart.owl")
    print(f"Copie : {dossier}")
    codes = [subprocess.run([sys.executable, "-X", "utf8", __file__, etape, str(dossier)], cwd=ICI).returncode
             for etape in ("--ecrire", "--relire")]
    return max(codes)


if __name__ == "__main__":
    sys.path.insert(0, str(ICI))
    if len(sys.argv) == 3:
        raise SystemExit(ecrire(sys.argv[2]) if sys.argv[1] == "--ecrire" else relire(sys.argv[2]))
    raise SystemExit(main())
