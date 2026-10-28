"""Non-régression des autres modules, sur une copie temporaire de SmartGrid-1.owl.

    cd backend
    python modules/mesure/verifications/verif_non_regression.py

1. Capture les réponses de toutes les routes GET sans paramètre des autres modules
   (production, stockage, bâtiments, réseau, console SPARQL) et des questions d'exemple
   de leurs traducteurs NLP.
2. Exécute un cycle CRUD complet du module Mesure (création, modification, changement de
   bâtiment, suppressions), en vérifiant au passage que Réseau et Bâtiments voient les ajouts.
3. Recapture : les réponses doivent être identiques à l'étape 1 (même contenu, l'ordre des
   éléments d'une liste n'est pas comparé) et le graphe isomorphe à SmartGrid-1.owl.
"""
import json

from rdflib import Graph
from rdflib.compare import isomorphic

from _banc import SOURCE_OWL, Verif, appel, banc, store

MODULES_NLP = ("reseau", "stockage", "batiments")


def canonique(x):
    """Forme comparable indépendante de l'ordre des listes et des clés."""
    if isinstance(x, dict):
        return {k: canonique(v) for k, v in sorted(x.items())}
    if isinstance(x, list):
        return sorted((canonique(v) for v in x), key=lambda v: json.dumps(v, sort_keys=True, ensure_ascii=False))
    return x


def capture(app, client):
    out = {}
    for regle in app.url_map.iter_rules():
        r = regle.rule
        if "GET" in regle.methods and r.startswith("/api/") and "<" not in r and not r.startswith("/api/mesure"):
            out[r] = appel(client, "GET", r)
    for m in MODULES_NLP:
        for q in appel(client, "GET", f"/api/{m}/nlp/exemples")[1]:
            out[f"NLP {m} : {q}"] = appel(client, "POST", f"/api/{m}/nlp", {"question": q})
    out["SPARQL console"] = appel(client, "POST", "/api/sparql", {"query": "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }"})
    return {k: (code, canonique(j)) for k, (code, j) in out.items()}


def main():
    app, client, _ = banc()
    v = Verif()
    print("--- 1. capture initiale")
    avant = capture(app, client)
    v(all(code < 500 for code, _ in avant.values()), f"{len(avant)} réponses capturées, aucune erreur 500")
    for k, (code, _) in avant.items():
        print(f"     {code} {k}")

    print("--- 2. cycle CRUD du module Mesure")
    etapes = [
        ("POST", "/api/mesure/compteurs", {"id": "NR_Compteur", "label": "Compteur NR", "identifiant": "NR-1", "batiment": "Villa_Hammamet"}, 201),
        ("POST", "/api/mesure/mesures", {"id": "NR_Mesure", "label": "Mesure NR", "type": "consommation", "valeur": 5,
                                         "debut": "2025-06-01", "fin": "2025-06-30", "compteur": "NR_Compteur"}, 201),
        ("POST", "/api/mesure/operateurs", {"id": "NR_Operateur", "label": "Opérateur NR", "gere": ["Poste_Sfax"]}, 201),
        ("PUT", "/api/mesure/compteurs/NR_Compteur?politique=reaffecter",
         {"label": "Compteur NR", "identifiant": "NR-1", "batiment": "Mairie_Nabeul"}, 200),
    ]
    for methode, chemin, corps, attendu in etapes:
        code, j = appel(client, methode, chemin, corps)
        v(code == attendu, f"{methode} {chemin} → {code}")
    _, postes = appel(client, "GET", "/api/reseau/postes")
    v(["NR_Operateur"] in [p["gestionnaires"] for p in postes["items"] if p["id"] == "Poste_Sfax"],
      "Réseau voit NR_Operateur comme gestionnaire de Poste_Sfax")
    _, bats = appel(client, "GET", "/api/batiments/batiments?definie=intelligent")
    v("Mairie_Nabeul" in [b["id"] for b in bats["items"]], "Bâtiments déduit BatimentIntelligent pour Mairie_Nabeul")
    for chemin in ("mesures/NR_Mesure", "compteurs/NR_Compteur", "operateurs/NR_Operateur?force=true"):
        code, _ = appel(client, "DELETE", f"/api/mesure/{chemin}")
        v(code == 200, f"DELETE /api/mesure/{chemin} → {code}")

    print("--- 3. recapture")
    apres = capture(app, client)
    differentes = [k for k in avant if avant[k] != apres.get(k)]
    v(not differentes, f"réponses des autres modules identiques avant/après ({len(avant)} comparées)")
    for k in differentes:
        print("     différente :", k)
    origine = Graph()
    origine.parse(SOURCE_OWL, format="xml")
    v(isomorphic(origine, store.graph), "graphe isomorphe à SmartGrid-1.owl après le cycle")
    return v.fin()


if __name__ == "__main__":
    raise SystemExit(main())
