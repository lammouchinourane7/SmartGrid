"""Persistance après redémarrage du backend (deux processus Python distincts).

    cd backend
    python modules/mesure/verifications/verif_persistance.py

Processus 1 : charge une copie temporaire de SmartGrid-1.owl, crée un compteur, une mesure
et un opérateur via l'API (écrits dans le fichier par store.update), puis se termine.
Processus 2 : nouvel interpréteur, recharge le fichier, relit les trois individus et R5,
les supprime via l'API et compare le graphe final à SmartGrid-1.owl par isomorphisme.
"""
import subprocess
import sys
import tempfile
from pathlib import Path

ICI = Path(__file__).resolve().parent

COMPTEUR = {"id": "Verif_Compteur", "label": "Compteur de vérification", "identifiant": "VERIF-1", "batiment": "Ecole_Ariana"}
MESURE = {"id": "Verif_Mesure", "label": "Mesure de vérification", "type": "consommation", "valeur": 12.5,
          "debut": "2025-05-01", "fin": "2025-05-31", "compteur": "Verif_Compteur"}
OPERATEUR = {"id": "Verif_Operateur", "label": "Opérateur de vérification", "gere": ["Poste_Sfax"]}


def ecrire(dossier):
    from _banc import Verif, appel, banc
    _, client, _ = banc(dossier)
    v = Verif()
    print("--- processus 1 (écriture)")
    for chemin, corps in (("compteurs", COMPTEUR), ("mesures", MESURE), ("operateurs", OPERATEUR)):
        code, j = appel(client, "POST", f"/api/mesure/{chemin}", corps)
        v(code == 201, f"POST /api/mesure/{chemin} → {code} {j.get('id', j.get('error'))}")
    return v.fin()


def relire(dossier):
    from rdflib import Graph
    from rdflib.compare import isomorphic

    from _banc import SOURCE_OWL, Verif, appel, banc, store
    _, client, _ = banc(dossier)
    v = Verif()
    print("--- processus 2 (après redémarrage : graphe relu depuis le fichier)")
    code, j = appel(client, "GET", "/api/mesure/compteurs/Verif_Compteur")
    v(code == 200 and j["item"]["batiments"] == ["Ecole_Ariana"], "compteur relu, installé dans Ecole_Ariana")
    code, j = appel(client, "GET", "/api/mesure/mesures/Verif_Mesure")
    v(code == 200 and j["item"]["valeur"] == 12.5 and j["item"]["fin"] == "2025-05-31T23:59:59",
      "mesure relue : 12.5 kWh, fin 2025-05-31T23:59:59")
    v(code == 200 and j["item"]["cibles"] == [{"id": "Ecole_Ariana", "via": "R5"}], "R5 recalculée : concerne Ecole_Ariana")
    code, j = appel(client, "GET", "/api/mesure/operateurs?q=Verif_Operateur")  # recherche sensible aux accents
    v(code == 200 and [o["gere"] for o in j["items"]] == [["Poste_Sfax"]], "opérateur relu, gere Poste_Sfax")

    for chemin in ("mesures/Verif_Mesure", "compteurs/Verif_Compteur", "operateurs/Verif_Operateur?force=true"):
        code, _ = appel(client, "DELETE", f"/api/mesure/{chemin}")
        v(code == 200, f"DELETE /api/mesure/{chemin} → {code}")
    origine = Graph()
    origine.parse(SOURCE_OWL, format="xml")
    final = Graph()
    final.parse(store.DATA_OWL, format="xml")
    v(isomorphic(origine, final), f"fichier final isomorphe à SmartGrid-1.owl ({len(final)} triplets)")
    return v.fin()


def main():
    dossier = tempfile.mkdtemp(prefix="verif_persistance_")
    print(f"Copie temporaire : {dossier}\\smartgrid.owl")
    codes = [subprocess.run([sys.executable, "-X", "utf8", __file__, etape, dossier], cwd=ICI).returncode
             for etape in ("--ecrire", "--relire")]
    return max(codes)


if __name__ == "__main__":
    sys.path.insert(0, str(ICI))
    if len(sys.argv) == 3:
        raise SystemExit(ecrire(sys.argv[2]) if sys.argv[1] == "--ecrire" else relire(sys.argv[2]))
    raise SystemExit(main())
