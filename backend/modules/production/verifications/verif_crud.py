"""CRUD, validations, R1, dépendances et absence de cascade — sur une copie temporaire du graphe courant.

    cd backend
    python modules/production/verifications/verif_crud.py

Écrit aussi deux graphes pour verif_hermit.py : « avec_source_test.owl » (source de test injectant
dans Ligne_Ariana) et « controle_step.owl » (ParcEolien forcé en SourceNonRenouvelable).
"""
from rdflib import Graph, URIRef
from rdflib.compare import isomorphic
from rdflib.namespace import RDF

from _banc import Verif, appel, banc, montrer, store

S = "Verif_Source_Solaire"
BASE = {"label": "Source de vérification", "type": "Solaire", "puissance": 120.5, "date": "2021-06-15",
        "lignes": ["Ligne_MT_Lac"], "batiments": ["Villa_Hammamet"]}


def copie():
    g = Graph()
    for t in store.graph:
        g.add(t)
    return g


def alimentation(client, source):
    _, j = appel(client, "GET", f"/api/production/sources/{source}")
    return {a["batiment"]: sorted(c["via"] for c in a["chemins"]) for a in j["item"]["alimentation"]}


def main():
    app, client, dossier = banc()
    v = Verif()
    initial = copie()

    print("=== 1. validations (le graphe doit rester inchangé)")
    cas = [
        ({**BASE, "id": "Bad> } DROP"}, "id"),
        ({**BASE, "id": "ParcEolien_SidiDaoud"}, "id"),
        ({**BASE, "id": S, "type": "Nucleaire"}, "type"),
        ({**BASE, "id": S, "puissance": -5}, "puissance"),
        ({**BASE, "id": S, "puissance": "nan"}, "puissance"),
        ({**BASE, "id": S, "puissance": "1e400"}, "puissance"),
        ({**BASE, "id": S, "puissance": "abc"}, "puissance"),
        ({**BASE, "id": S, "date": "2099-01-01"}, "date"),
        ({**BASE, "id": S, "date": "15/06/2021"}, "date"),
        ({**BASE, "id": S, "lignes": ["Poste_Rades"]}, "lignes"),
        ({**BASE, "id": S, "batiments": ["Ligne_Ariana"]}, "batiments"),
        ({**BASE, "id": S, "type": "Eolien", "lignes": []}, "lignes"),
        ({**BASE, "id": S, "label": "Parc éolien de Sidi Daoud"}, "label"),
    ]
    for corps, champ in cas:
        code, j = appel(client, "POST", "/api/production/sources", corps)
        v(code == 422 and champ in j.get("champs", {}), f"refus {champ!r} → {code} : {j.get('champs', {}).get(champ)}")
    v(isomorphic(initial, store.graph), "aucune écriture après les 13 refus")

    print("\n=== 2. création + sous-classes")
    code, j = appel(client, "POST", "/api/production/sources", {**BASE, "id": S})
    v(code == 201, f"POST → {code}")
    _, liste = appel(client, "GET", "/api/production/sources?categorie=renouvelable")
    v(S in [x["id"] for x in liste["items"]], "la source Solaire apparaît parmi les renouvelables (parent non asserté)")
    v((store.iri(S), RDF.type, store.SG.SourceRenouvelable) not in store.graph,
      "aucun type parent matérialisé : l'inclusion vient de rdfs:subClassOf*")
    _, d = appel(client, "GET", f"/api/production/sources/{S}")
    v(d["item"]["puissance"] == 120.5 and d["item"]["date"] == "2021-06-15T00:00:00", "puissance et date relues")

    print("\n=== 3. R1 avant / après modification de l'injection")
    avant = alimentation(client, S)
    print("    avant (Ligne_MT_Lac) :", avant)
    v(avant == {"Immeuble_Lac": ["R1"], "Centre_Commercial_Lac": ["R7"], "Villa_Hammamet": ["produitEnergiePour"]},
      "R1 → Immeuble_Lac, R7 → Centre_Commercial_Lac, lien direct → Villa_Hammamet")
    code, _ = appel(client, "PUT", f"/api/production/sources/{S}", {**BASE, "lignes": ["Ligne_Ariana"]})
    apres = alimentation(client, S)
    print("    après (Ligne_Ariana) :", apres)
    v(code == 200 and "Immeuble_Lac" not in apres and "Centre_Commercial_Lac" not in apres,
      "plus aucun résultat obsolète du Lac après le changement de ligne")
    v(apres.get("Hopital_CharlesNicolle") == ["R1", "R7"], "Hopital_CharlesNicolle une seule fois, deux justifications (R1 et R7)")
    v(apres.get("Ecole_Ariana") == ["R7"], "Ecole_Ariana via R7 (estRaccordeA)")
    store.graph.serialize(destination=dossier / "avec_source_test.owl", format="xml")

    print("\n=== 4. modification d'une source existante : liens des autres modules préservés")
    p = store.iri("ParcEolien_SidiDaoud")
    externes = {t for t in store.graph.triples((None, None, p))}
    _, d = appel(client, "GET", "/api/production/sources/ParcEolien_SidiDaoud")
    it = d["item"]
    corps = {"label": it["label"], "type": "Eolien", "puissance": 55000, "date": it["date"][:10],
             "lignes": it["lignes"], "batiments": it["batimentsDirects"]}
    code, _ = appel(client, "PUT", "/api/production/sources/ParcEolien_SidiDaoud", corps)
    v(code == 200 and store.graph.value(p, store.SG.puissanceInstallee).toPython() == 55000.0, "puissance modifiée (55 000 kW)")
    v({t for t in store.graph.triples((None, None, p))} == externes,
      "triplets entrants intacts (estAlimentePar de Mairie_Nabeul, stockeEnergieDe des stockages…)")
    code, j = appel(client, "PUT", "/api/production/sources/ParcEolien_SidiDaoud", {**corps, "type": "SourceNonRenouvelable"})
    print("   ", code, j.get("champs", {}).get("type"))
    v(code == 422, "type non renouvelable refusé : STEP_Sejnane impose stockeEnergieDe only SourceRenouvelable")
    code, j = appel(client, "PUT", "/api/production/sources/ParcEolien_SidiDaoud", {**corps, "lignes": []})
    v(code == 422 and "lignes" in j["champs"], "éolienne sans ligne refusée (Eolien ⊑ injecteDans some LigneElectrique)")
    corps["puissance"] = 54000
    appel(client, "PUT", "/api/production/sources/ParcEolien_SidiDaoud", corps)

    print("\n=== 5. suppressions")
    avant_suppr = copie()
    code, j = appel(client, "DELETE", "/api/production/sources/CentraleGaz_Rades")
    print("   ", code, montrer(j.get("dependances")))
    v(code == 409 and {d["relation"] for d in j["dependances"]} >= {"estAlimentePar", "stockeEnergieDe"},
      "CentraleGaz_Rades : 409, dépendances estAlimentePar (Bâtiments) et stockeEnergieDe (Stockage)")
    v(isomorphic(avant_suppr, store.graph), "rien n'est supprimé en cascade")

    code, _ = appel(client, "POST", "/api/mesure/mesures", {
        "id": "Verif_Mesure_Prod", "label": "Mesure de vérification production", "type": "production",
        "valeur": 10, "debut": "2025-02-01", "fin": "2025-02-28", "cible": S})
    v(code == 201, "mesure de production créée via l'API Mesure (concerne la source de test)")
    code, j = appel(client, "DELETE", f"/api/production/sources/{S}")
    v(code == 409 and j["dependances"] == [{"id": "Verif_Mesure_Prod", "relation": "concerne", "sens": "entrante"}],
      "suppression bloquée par la mesure (concerne)")
    appel(client, "DELETE", "/api/mesure/mesures/Verif_Mesure_Prod")
    _, deps = appel(client, "GET", f"/api/production/sources/{S}/dependances")
    v(deps["bloquantes"] == [], "plus de dépendance bloquante après suppression de la mesure")
    code, j = appel(client, "DELETE", f"/api/production/sources/{S}")
    v(code == 200 and {x["relation"] for x in j["supprimees"]} == {"injecteDans", "produitEnergiePour"},
      "source supprimée avec ses seuls triplets (injecteDans, produitEnergiePour)")
    v((URIRef(store.SG.Villa_Hammamet), RDF.type, None) in store.graph or
      any(store.graph.triples((store.iri("Villa_Hammamet"), RDF.type, None))), "Villa_Hammamet toujours présente")
    v(isomorphic(initial, store.graph), "graphe final isomorphe au graphe de départ")

    print("\n=== 6. contrôle négatif pour HermiT (sur une copie, jamais via l'API)")
    g = copie()
    g.remove((p, RDF.type, store.SG.Eolien))
    g.add((p, RDF.type, store.SG.SourceNonRenouvelable))
    g.serialize(destination=dossier / "controle_step.owl", format="xml")
    print(f"\nGraphes écrits dans {dossier}")
    print(f'  python modules/production/verifications/verif_hermit.py "{dossier / "avec_source_test.owl"}" '
          f"Hopital_CharlesNicolle.estAlimentePar={S} Ecole_Ariana.estAlimentePar={S} "
          f"Usine_Sfax.estAlimentePar=CentraleSolaire_Tozeur")
    print(f'  python modules/production/verifications/verif_hermit.py "{dossier / "controle_step.owl"}" --incoherent')
    return v.fin()


if __name__ == "__main__":
    raise SystemExit(main())
