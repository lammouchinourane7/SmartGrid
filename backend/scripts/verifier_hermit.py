"""Vérifie SmartGrid-1.owl avec le raisonneur HermiT (via owlready2, Java requis).

    pip install owlready2
    python backend/scripts/verifier_hermit.py

Affiche la cohérence, les classes insatisfiables et les individus déduits
pour chaque classe définie (≡) — y compris les effets des règles SWRL.
"""
from pathlib import Path

from owlready2 import OwlReadyInconsistentOntologyError, default_world, get_ontology, sync_reasoner

OWL_FILE = Path(__file__).resolve().parents[2] / "SmartGrid-1.owl"

CLASSES_DEFINIES = [
    "BatimentAutonome", "LigneHauteTension", "LigneMoyenneTension", "LigneBasseTension",
    "StockageVert", "StockageCritique", "StockageGrandeCapacite", "StockageSecours",
]


def main():
    onto = get_ontology(OWL_FILE.as_uri()).load()
    try:
        with onto:
            sync_reasoner(infer_property_values=True, debug=0)
    except OwlReadyInconsistentOntologyError:
        print("✗ Ontologie INCOHÉRENTE")
        return
    insat = list(default_world.inconsistent_classes())
    print("✓ Ontologie cohérente")
    print(f"  classes insatisfiables : {len(insat)} {[c.name for c in insat]}")
    for nom in CLASSES_DEFINIES:
        c = onto[nom]
        if c is not None:
            print(f"  {nom:24} ← {', '.join(sorted(i.name for i in c.instances())) or '—'}")


if __name__ == "__main__":
    main()
