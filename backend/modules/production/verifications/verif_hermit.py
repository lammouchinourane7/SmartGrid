"""Raisonnement HermiT (owlready2, Java requis) sur une COPIE de graphe, règles SWRL du fichier comprises.

    pip install owlready2
    python modules/production/verifications/verif_hermit.py FICHIER.owl [Sujet.propriete=Objet ...]
                                                            [--incoherent] [--comparer-sparql]

owlready2 charge le fichier dans un World isolé ; les règles swrl:Imp du fichier (R1…R7) sont
listées puis transmises à HermiT par sync_reasoner(infer_property_values=True), qui ajoute les
valeurs de propriétés déduites. Chaque « Sujet.propriete=Objet » vérifie que Objet figure parmi
les valeurs (assertées + déduites) de Sujet.propriete.

Rappel : OWL n'applique pas l'hypothèse des noms uniques ; une incohérence vient ici d'une
disjonction de classes (SourceRenouvelable ⊓ SourceNonRenouvelable ⊑ ⊥), pas d'un comptage.
"""
import sys
from pathlib import Path

from owlready2 import OwlReadyInconsistentOntologyError, World, sync_reasoner


def comparer(onto, fichier):
    """Paires (bâtiment, source) : HermiT (estAlimentePar asserté + déduit) = réécriture SPARQL du module."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
    import store
    from modules.production import queries as Q
    store.DATA_OWL = fichier
    store.load()
    hermit = {(b.name, s.name) for b in onto.search(type=onto.Batiment) for s in b.estAlimentePar}
    sparql = {(r["b"], r["s"]) for r in store.select(Q.alimentation())}
    ok = hermit == sparql
    print(f"[{'OK' if ok else 'ÉCHEC'}] estAlimentePar : HermiT {len(hermit)} paires = SPARQL {len(sparql)} paires")
    for p in sorted(hermit - sparql):
        print("    seulement HermiT :", p)
    for p in sorted(sparql - hermit):
        print("    seulement SPARQL :", p)
    return 0 if ok else 1


def main(args):
    fichier = Path(args[0]).resolve()
    attendus = [a for a in args[1:] if "=" in a]
    incoherent_attendu = "--incoherent" in args
    monde = World()
    onto = monde.get_ontology(str(fichier)).load()
    regles = list(onto.rules())
    print(f"Fichier : {fichier}")
    print(f"Règles SWRL chargées : {len(regles)}")
    for r in regles:
        print(f"  {r.label.first() or '?'} : {r}")
    try:
        with onto:
            sync_reasoner(monde, infer_property_values=True, debug=0)
    except OwlReadyInconsistentOntologyError:
        print("Résultat : ontologie INCOHÉRENTE")
        print("[OK] incohérence attendue" if incoherent_attendu else "[ÉCHEC] incohérence inattendue")
        return 0 if incoherent_attendu else 1
    insat = [c.name for c in monde.inconsistent_classes()]
    print(f"Résultat : ontologie cohérente ; classes insatisfiables : {insat}")
    if incoherent_attendu:
        print("[ÉCHEC] une incohérence était attendue")
        return 1
    echecs = len(insat)
    if "--comparer-sparql" in args:
        echecs += comparer(onto, fichier)
    for a in attendus:
        gauche, objet = a.split("=", 1)
        sujet, prop = gauche.split(".", 1)
        valeurs = sorted(x.name for x in getattr(onto[sujet], prop))
        ok = objet in valeurs
        echecs += not ok
        print(f"[{'OK' if ok else 'ÉCHEC'}] {sujet}.{prop} contient {objet} (valeurs : {valeurs})")
    return 1 if echecs else 0


if __name__ == "__main__":
    if not sys.argv[1:]:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
