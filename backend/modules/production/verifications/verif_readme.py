"""Exécute les exemples SPARQL du README du module sur une copie temporaire du graphe courant.

    cd backend
    python modules/production/verifications/verif_readme.py
"""
import re
from pathlib import Path

from _banc import Verif, banc, store


def main():
    banc()
    v = Verif()
    texte = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
    for q in re.findall(r"```sparql\n(.*?)```", texte, re.S):
        titre = q.strip().splitlines()[0][:70]
        if q.lstrip().startswith(("INSERT", "DELETE")):
            store.update(q)
            p = store.graph.value(store.iri("CentraleSolaire_Kairouan"), store.SG.puissanceInstallee)
            v(p is not None, f"{titre} … → puissance = {p}")
        else:
            lignes = store.select(q)
            print("    ", lignes)
            v(bool(lignes), f"{titre} … → {len(lignes)} ligne(s)")
    p = [o.toPython() for o in store.graph.objects(store.iri("CentraleSolaire_Kairouan"), store.SG.puissanceInstallee)]
    v(p == [2000.0], f"après DELETE/INSERT : une seule valeur de puissance {p}")
    return v.fin()


if __name__ == "__main__":
    raise SystemExit(main())
