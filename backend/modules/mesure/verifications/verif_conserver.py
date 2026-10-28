"""Scénario « changer le bâtiment d'un compteur → Conserver les anciennes mesures ».

    cd backend
    python modules/mesure/verifications/verif_conserver.py

Sur une copie temporaire de SmartGrid-1.owl :
  1. triplets avant : Compteur_M1 installeDans Maison1, enregistre Mesure_Maison1_Janvier (sans concerne) ;
  2. PUT sans politique → 409, rien n'est écrit ;
  3. PUT ?politique=conserver vers Villa_Hammamet → triplets après, cible de la mesure (assertion + R5) ;
  4. ré-attacher la mesure au compteur sans confirmation → 409 ; avec confirmation → réaffectée par R5 ;
  5. contrôle négatif : garder enregistre ET concerne Maison1 → deux bâtiments (violation de max 1).
Les graphes « après conserver » et « violation » sont écrits pour verif_hermit.py.
"""
from rdflib import Graph, URIRef

from _banc import Verif, appel, banc, montrer, store

C, M, P = "Compteur_M1", "Mesure_Maison1_Janvier", "Mesure_Prod_Panneau_Janvier"
ANCIEN, NOUVEAU = "Maison1", "Villa_Hammamet"


def _court(x):
    """IRI → nom local (sg:Maison1 → Maison1), littéral → texte."""
    return str(x).rsplit("#", 1)[-1] if isinstance(x, URIRef) else str(x)


def triplets(*ids):
    """Triplets dont le sujet ou l'objet est l'un des individus (hors listes RDF anonymes : owl:AllDifferent)."""
    out = set()
    for i in ids:
        u = store.iri(i)
        out |= set(store.graph.triples((u, None, None)))
        out |= {t for t in store.graph.triples((None, None, u)) if isinstance(t[0], URIRef)}
    return sorted(" ".join(_court(x) for x in t) for t in out)


def cibles(client, mesure):
    _, j = appel(client, "GET", f"/api/mesure/mesures/{mesure}")
    return j["item"]["cibles"], j["item"].get("historique", [])


def main():
    app, client, dossier = banc()
    v = Verif()
    corps = {"label": "Compteur de Maison1", "identifiant": "CPT-0001"}

    print("=== 1. AVANT")
    avant = triplets(C, M)
    for t in avant:
        print("   ", t)
    cib, _ = cibles(client, M)
    print("   R5 / cible de", M, ":", cib)
    v(cib == [{"id": ANCIEN, "via": "R5"}], f"{M} concerne {ANCIEN} uniquement, déduit par R5 (aucun concerne asserté)")

    print("\n=== 2. PUT sans politique")
    code, j = appel(client, "PUT", f"/api/mesure/compteurs/{C}", {**corps, "batiment": NOUVEAU})
    print("   ", code, j["error"])
    for a in j["apercu"]["conserver"]:
        print("    aperçu conserver :", a)
    v(code == 409, "changement refusé tant qu'aucune politique n'est choisie")
    v(triplets(C, M) == avant, "aucun triplet modifié par le refus")

    print("\n=== 3. PUT ?politique=conserver")
    code, j = appel(client, "PUT", f"/api/mesure/compteurs/{C}?politique=conserver", {**corps, "batiment": NOUVEAU})
    print("   ", code)
    print("    SPARQL exécuté :\n      " + j["sparql"].replace("\n", "\n      "))
    apres = triplets(C, M)
    print("    triplets retirés :", sorted(set(avant) - set(apres)))
    print("    triplets ajoutés :", sorted(set(apres) - set(avant)))
    cib, hist = cibles(client, M)
    print("    cible de", M, ":", cib, "| historique :", hist)
    v(code == 200, "politique conserver appliquée")
    v(cib == [{"id": ANCIEN, "via": "assertion"}], f"{M} concerne {ANCIEN} seul (assertion), jamais {NOUVEAU}")
    v(f"Compteur_M1 enregistre {M}" not in apres, "lien enregistre retiré : R5 ne peut plus déduire le nouveau bâtiment")
    v(any("Compteur_M1" in h for h in hist), "historique conservé : rdfs:comment cite le compteur d'origine")
    v(f"Compteur_M1 installeDans {NOUVEAU}" in apres and f"Compteur_M1 installeDans {ANCIEN}" not in apres,
      "le compteur est installé dans le nouveau bâtiment uniquement")
    _, jp = appel(client, "GET", f"/api/mesure/mesures/{P}")
    v(jp["item"]["compteurs"] == [C], f"la mesure de production {P} reste enregistrée par {C} (R5 ne la concerne pas)")
    _, jc = appel(client, "GET", "/api/mesure/coherence")
    v(jc["anomalies"] == [], "aucune anomalie (exactly 1, max 1, only) après conserver")
    store.graph.serialize(destination=dossier / "apres_conserver.owl", format="xml")

    print("\n=== 4. ré-attacher la mesure au compteur (déplacé)")
    mesure = {"label": "Consommation de Maison1 en janvier 2025", "type": "consommation", "valeur": 350,
              "debut": "2025-01-01T00:00:00", "fin": "2025-01-31T23:59:59", "compteur": C}
    code, j = appel(client, "PUT", f"/api/mesure/mesures/{M}", mesure)
    print("    sans confirmation :", code, j.get("error"))
    v(code == 409 and cibles(client, M)[0] == [{"id": ANCIEN, "via": "assertion"}],
      "réaffectation silencieuse refusée (409), données inchangées")
    copie = Graph()  # état « après conserver », pour le contrôle négatif
    for t in store.graph:
        copie.add(t)

    code, j = appel(client, "PUT", f"/api/mesure/mesures/{M}", {**mesure, "confirmerReaffectation": True})
    cib, _ = cibles(client, M)
    print("    avec confirmation :", code, cib)
    v(code == 200 and cib == [{"id": NOUVEAU, "via": "R5"}], f"réaffectation confirmée : {NOUVEAU} seul, par R5")

    print("\n=== 5. contrôle négatif : enregistre conservé + concerne ancien bâtiment")
    store.graph.remove((None, None, None))
    for t in copie:
        store.graph.add(t)
    store.graph.add((store.iri(C), store.SG.enregistre, store.iri(M)))
    cib, _ = cibles(client, M)
    _, jc = appel(client, "GET", "/api/mesure/coherence")
    print("    cibles :", cib, "| anomalies :", montrer(jc["anomalies"]))
    v({c["id"] for c in cib} == {ANCIEN, NOUVEAU}, "sans retrait de enregistre, R5 donnerait deux bâtiments")
    v(any("max 1" in a["probleme"] for a in jc["anomalies"]), "le contrôle de cohérence signale la violation de max 1")
    store.graph.serialize(destination=dossier / "controle_violation.owl", format="xml")

    print(f"\nGraphes écrits dans {dossier} :")
    print(f"  python modules/mesure/verifications/verif_hermit.py \"{dossier / 'apres_conserver.owl'}\" "
          f"{M}={ANCIEN} Mesure_Usine_Q1=Usine_Sfax")
    print(f"  python modules/mesure/verifications/verif_hermit.py \"{dossier / 'controle_violation.owl'}\" --incoherent")
    return v.fin()


if __name__ == "__main__":
    raise SystemExit(main())
