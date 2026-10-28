"""Compare deux fichiers OWL/RDF par isomorphisme de graphes (nœuds anonymes compris).

    python modules/mesure/verifications/verif_isomorphisme.py ../SmartGrid-1.owl data/smartgrid.owl

Le nombre de triplets ne suffit pas : deux graphes de même taille peuvent différer.
rdflib.compare.isomorphic compare le contenu en renommant canoniquement les nœuds
anonymes (listes owl:AllDifferent, restrictions, atomes SWRL).
"""
import sys

from rdflib import Graph
from rdflib.compare import graph_diff, isomorphic, to_isomorphic


def charger(chemin):
    g = Graph()
    g.parse(chemin, format="xml")
    return g


def main(a, b):
    ga, gb = charger(a), charger(b)
    print(f"{a} : {len(ga)} triplets")
    print(f"{b} : {len(gb)} triplets")
    if isomorphic(ga, gb):
        print("ISOMORPHES : contenu RDF identique")
        return 0
    commun, seul_a, seul_b = graph_diff(to_isomorphic(ga), to_isomorphic(gb))
    print(f"DIFFÉRENTS : {len(seul_a)} triplet(s) seulement dans A, {len(seul_b)} seulement dans B")
    for t in sorted(seul_a)[:40]:
        print("  - A", t)
    for t in sorted(seul_b)[:40]:
        print("  + B", t)
    return 1


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1], sys.argv[2]))
