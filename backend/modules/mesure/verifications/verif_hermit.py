"""Raisonnement HermiT (owlready2, Java requis) sur un fichier OWL, avec les règles SWRL du fichier.

    pip install owlready2
    python modules/mesure/verifications/verif_hermit.py FICHIER.owl [Mesure=Bat[,Bat2] ...] [--incoherent]

Configuration : owlready2 charge le fichier (RDF/XML) dans un World isolé ; les règles
swrl:Imp qu'il contient sont lues comme objets Imp (listées ci-dessous) et transmises à
HermiT par sync_reasoner(infer_property_values=True), qui ajoute au monde les valeurs de
propriétés déduites (dont concerne déduit par R5).

Vérifie : cohérence (ou incohérence attendue avec --incoherent), classes insatisfiables,
et pour chaque « Mesure=Bat » que l'ensemble des concerne (assertés + déduits) est exactement {Bat}.
"""
import sys
from pathlib import Path

from owlready2 import OwlReadyInconsistentOntologyError, World, sync_reasoner


def main(args):
    fichier = Path(args[0]).resolve()
    attendus = dict(a.split("=", 1) for a in args[1:] if "=" in a)
    incoherent_attendu = "--incoherent" in args

    monde = World()
    onto = monde.get_ontology(str(fichier)).load()
    regles = list(onto.rules())
    print(f"Fichier : {fichier}")
    print(f"Règles SWRL chargées : {len(regles)}")
    for r in regles:
        print(f"  {r.label.first() or '?'} : {r}")
    print(f"Raisonneur : HermiT (owlready2 sync_reasoner, infer_property_values=True)")

    echecs = 0
    try:
        with onto:
            sync_reasoner(monde, infer_property_values=True, debug=0)
    except OwlReadyInconsistentOntologyError:
        print("Résultat : ontologie INCOHÉRENTE")
        print("[OK] incohérence attendue" if incoherent_attendu else "[ÉCHEC] incohérence inattendue")
        return 0 if incoherent_attendu else 1

    insat = list(monde.inconsistent_classes())
    print(f"Résultat : ontologie cohérente ; classes insatisfiables : {[c.name for c in insat]}")
    if incoherent_attendu:
        print("[ÉCHEC] une incohérence était attendue")
        return 1
    if insat:
        echecs += 1
    for mesure, batiments in attendus.items():
        obtenu = sorted(x.name for x in onto[mesure].concerne)
        attendu = sorted(batiments.split(","))
        ok = obtenu == attendu
        echecs += not ok
        print(f"[{'OK' if ok else 'ÉCHEC'}] {mesure} concerne {obtenu} (attendu {attendu})")
    return 1 if echecs else 0


if __name__ == "__main__":
    if not sys.argv[1:]:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
