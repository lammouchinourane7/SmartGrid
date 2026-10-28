"""Test sur le VRAI serveur (HTTP, de préférence via le proxy Angular), avec instantané et isomorphisme.

    cd backend
    python app.py                       # et, pour le proxy : cd frontend && npx ng serve
    python modules/production/verifications/verif_live.py avant  [http://localhost:4200/api]
    # arrêter puis relancer python app.py (redémarrage réel)
    python modules/production/verifications/verif_live.py apres  [http://localhost:4200/api]

avant : copie data/smartgrid.owl → data/verif_instantane_production.owl, crée une source de test
        (URI Live_Production_Test), vérifie R1 et le NLP via HTTP.
apres : relit la source après redémarrage, la supprime (seule donnée créée), puis compare
        data/smartgrid.owl à l'instantané par isomorphisme. Jamais de réinitialisation depuis SmartGrid-1.owl.
"""
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

from rdflib import Graph
from rdflib.compare import graph_diff, isomorphic, to_isomorphic

DATA = Path(__file__).resolve().parents[3] / "data"
COURANT, INSTANTANE = DATA / "smartgrid.owl", DATA / "verif_instantane_production.owl"
ID = "Live_Production_Test"
SOURCE = {"id": ID, "label": "Source test HTTP", "type": "Solaire", "puissance": 75, "date": "2022-09-01",
          "lignes": ["Ligne_Ariana"], "batiments": ["Villa_Hammamet"]}


def appel(base, methode, chemin, corps=None):
    data = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(base + chemin, data=data, method=methode, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def verif(ok, message, res):
    print(f"  [{'OK' if ok else 'ÉCHEC'}] {message}")
    res.append(bool(ok))


def avant(base):
    res = []
    if INSTANTANE.exists():
        sys.exit(f"{INSTANTANE} existe déjà : lancez d'abord « apres ».")
    shutil.copyfile(COURANT, INSTANTANE)
    print(f"Instantané : {INSTANTANE}")
    code, j = appel(base, "POST", "/production/sources", SOURCE)
    verif(code == 201, f"POST {base}/production/sources → {code} {j.get('id', j.get('error'))}", res)
    code, j = appel(base, "GET", f"/production/sources/{ID}")
    alim = {a["batiment"]: sorted(c["via"] for c in a["chemins"]) for a in j["item"]["alimentation"]}
    verif(alim == {"Hopital_CharlesNicolle": ["R1", "R7"], "Ecole_Ariana": ["R7"], "Villa_Hammamet": ["produitEnergiePour"]},
          f"alimentation via HTTP : {alim}", res)
    code, j = appel(base, "POST", "/production/nlp", {"question": "Quels bâtiments sont alimentés par Live_Production_Test ?"})
    verif(code == 200 and {r["batiment"] for r in j.get("lignes", [])} == set(alim), "NLP via HTTP : mêmes bâtiments", res)
    print("Redémarrez maintenant le backend, puis lancez « apres ».")
    return 0 if all(res) else 1


def apres(base):
    res = []
    code, j = appel(base, "GET", f"/production/sources/{ID}")
    verif(code == 200 and j["item"]["puissance"] == 75.0, "après redémarrage : source relue (75 kW)", res)
    code, j = appel(base, "DELETE", f"/production/sources/{ID}")
    verif(code == 200, f"DELETE → {code}", res)
    for m in ("mesure/stats", "reseau/stats", "stockage/stats", "batiments/stats"):
        code, _ = appel(base, "GET", f"/{m}")
        verif(code == 200, f"GET /{m} → {code}", res)
    g1, g2 = Graph(), Graph()
    g1.parse(INSTANTANE, format="xml")
    g2.parse(COURANT, format="xml")
    iso = isomorphic(g1, g2)
    verif(iso, f"data/smartgrid.owl isomorphe à l'instantané ({len(g1)} → {len(g2)} triplets)", res)
    if iso:
        INSTANTANE.unlink()
    else:
        _, a, b = graph_diff(to_isomorphic(g1), to_isomorphic(g2))
        for t in sorted(a)[:20]:
            print("    - instantané", t)
        for t in sorted(b)[:20]:
            print("    + courant   ", t)
    return 0 if all(res) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("avant", "apres"):
        sys.exit(__doc__)
    base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:5000/api"
    raise SystemExit(avant(base) if sys.argv[1] == "avant" else apres(base))
