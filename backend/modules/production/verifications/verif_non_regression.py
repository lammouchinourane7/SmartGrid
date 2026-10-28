"""Non-régression des autres modules (Mesure, Réseau, Stockage, Bâtiments) — copie du graphe courant.

    cd backend
    python modules/production/verifications/verif_non_regression.py

1. Capture toutes les routes GET sans paramètre des autres modules et les réponses de leurs
   questions NLP d'exemple (Mesure compris).
2. Cycle CRUD Production : création d'une source qui alimente un bâtiment et injecte dans une
   ligne ; on vérifie que Bâtiments et Réseau la voient ; modification ; suppression.
3. Recapture : réponses identiques (contenu ; l'ordre des listes n'est pas comparé) et graphe
   isomorphe à la copie de départ.
"""
import json

from rdflib import Graph
from rdflib.compare import isomorphic

from _banc import Verif, appel, banc, store

MODULES_NLP = ("mesure", "reseau", "stockage", "batiments")


def canonique(x):
    if isinstance(x, dict):
        return {k: canonique(v) for k, v in sorted(x.items())}
    if isinstance(x, list):
        return sorted((canonique(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    return x


def capture(app, client):
    out = {}
    for regle in app.url_map.iter_rules():
        r = regle.rule
        if "GET" in regle.methods and r.startswith("/api/") and "<" not in r and not r.startswith("/api/production"):
            out[r] = appel(client, "GET", r)
    for m in MODULES_NLP:
        for q in appel(client, "GET", f"/api/{m}/nlp/exemples")[1]:
            out[f"NLP {m} : {q}"] = appel(client, "POST", f"/api/{m}/nlp", {"question": q})
    return {k: (code, canonique(j)) for k, (code, j) in out.items()}


def main():
    app, client, _ = banc()
    v = Verif()
    depart = Graph()
    for t in store.graph:
        depart.add(t)

    print("--- 1. capture initiale")
    avant = capture(app, client)
    v(all(code < 500 for code, _ in avant.values()), f"{len(avant)} réponses capturées, aucune erreur 500")

    print("--- 2. cycle CRUD Production")
    s = {"id": "NR_Source", "label": "Source non-régression", "type": "SourceNonRenouvelable", "puissance": 800,
         "date": "2010-01-01", "lignes": ["Ligne_MT_Nabeul"], "batiments": ["Cimenterie_Gabes"]}
    code, _ = appel(client, "POST", "/api/production/sources", s)
    v(code == 201, f"POST source → {code}")
    _, b = appel(client, "GET", "/api/batiments/batiments/Cimenterie_Gabes")
    v("NR_Source" in json.dumps(b), "Bâtiments voit NR_Source parmi les sources de Cimenterie_Gabes (produitEnergiePour⁻¹)")
    _, l = appel(client, "GET", "/api/reseau/lignes/Ligne_MT_Nabeul")
    v("NR_Source" in l["item"].get("sources", []), "Réseau voit NR_Source parmi les sources de Ligne_MT_Nabeul")
    code, _ = appel(client, "PUT", "/api/production/sources/NR_Source", {**s, "puissance": 900})
    v(code == 200, f"PUT source → {code}")
    code, _ = appel(client, "DELETE", "/api/production/sources/NR_Source")
    v(code == 200, f"DELETE source → {code}")

    print("--- 3. recapture")
    apres = capture(app, client)
    differentes = [k for k in avant if avant[k] != apres.get(k)]
    v(not differentes, f"réponses des autres modules identiques avant/après ({len(avant)} comparées)")
    for k in differentes:
        print("     différente :", k)
    v(isomorphic(depart, store.graph), "graphe isomorphe à la copie de départ")
    return v.fin()


if __name__ == "__main__":
    raise SystemExit(main())
