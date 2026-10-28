"""Test sur le VRAI serveur (HTTP), avec instantané pris avant et comparaison par isomorphisme.

    cd backend
    python app.py                       # terminal 1   (et, pour passer par le proxy : cd frontend && npx ng serve)
    python modules/mesure/verifications/verif_live.py avant  [http://localhost:4200/api]
    # arrêter puis relancer python app.py (redémarrage réel)
    python modules/mesure/verifications/verif_live.py apres  [http://localhost:4200/api]

avant : copie data/smartgrid.owl dans data/verif_instantane.owl (instantané), puis crée
        un compteur, une mesure et un opérateur de test via HTTP.
apres : relit les individus via HTTP (après redémarrage), les supprime, puis compare
        data/smartgrid.owl à l'instantané par isomorphisme de graphes.
Seules les données de test créées par ce script sont supprimées.
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
COURANT, INSTANTANE = DATA / "smartgrid.owl", DATA / "verif_instantane.owl"

COMPTEUR = {"id": "Live_Compteur", "label": "Compteur test HTTP", "identifiant": "LIVE-1", "batiment": "Ecole_Ariana"}
MESURE = {"id": "Live_Mesure", "label": "Mesure test HTTP", "type": "consommation", "valeur": 42.5,
          "debut": "2025-04-01", "fin": "2025-04-30", "compteur": "Live_Compteur"}
OPERATEUR = {"id": "Live_Operateur", "label": "Opérateur test HTTP", "gere": ["Poste_Sfax"]}


def appel(base, methode, chemin, corps=None):
    data = json.dumps(corps).encode("utf-8") if corps is not None else None
    req = urllib.request.Request(base + chemin, data=data, method=methode, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def verif(condition, message, compteur):
    print(f"  [{'OK' if condition else 'ÉCHEC'}] {message}")
    compteur.append(bool(condition))


def avant(base):
    res = []
    if INSTANTANE.exists():
        sys.exit(f"{INSTANTANE} existe déjà : lancez d'abord « apres » (ou supprimez-le).")
    shutil.copyfile(COURANT, INSTANTANE)
    print(f"Instantané : {COURANT} → {INSTANTANE}")
    for chemin, corps in (("compteurs", COMPTEUR), ("mesures", MESURE), ("operateurs", OPERATEUR)):
        code, j = appel(base, "POST", f"/mesure/{chemin}", corps)
        verif(code == 201, f"POST {base}/mesure/{chemin} → {code} {j.get('id', j.get('error'))}", res)
    code, j = appel(base, "POST", "/mesure/nlp", {"question": "Quelle est la consommation totale de l'école d'Ariana en avril 2025 ?"})
    verif(code == 200 and j.get("lignes") == [{"type": "consommation", "totalKWh": 42.5, "nombre": 1}],
          f"NLP via HTTP : {j.get('interpretation')} → {j.get('lignes')}", res)
    print("Redémarrez maintenant le backend, puis lancez « apres ».")
    return 0 if all(res) else 1


def apres(base):
    res = []
    code, j = appel(base, "GET", "/health")
    print(f"Backend : {code} {j}")
    code, j = appel(base, "GET", "/mesure/compteurs/Live_Compteur")
    verif(code == 200 and j["item"]["batiments"] == ["Ecole_Ariana"], "après redémarrage : compteur relu", res)
    code, j = appel(base, "GET", "/mesure/mesures/Live_Mesure")
    verif(code == 200 and j["item"]["cibles"] == [{"id": "Ecole_Ariana", "via": "R5"}],
          "après redémarrage : mesure relue, R5 → Ecole_Ariana", res)
    code, j = appel(base, "GET", "/mesure/operateurs?q=Live_Operateur")
    verif(code == 200 and [o["gere"] for o in j["items"]] == [["Poste_Sfax"]], "après redémarrage : opérateur relu", res)
    for chemin in ("mesures/Live_Mesure", "compteurs/Live_Compteur", "operateurs/Live_Operateur?force=true"):
        code, _ = appel(base, "DELETE", f"/mesure/{chemin}")
        verif(code == 200, f"DELETE {chemin} → {code}", res)

    g_avant, g_apres = Graph(), Graph()
    g_avant.parse(INSTANTANE, format="xml")
    g_apres.parse(COURANT, format="xml")
    iso = isomorphic(g_avant, g_apres)
    verif(iso, f"data/smartgrid.owl isomorphe à l'instantané ({len(g_avant)} → {len(g_apres)} triplets)", res)
    if not iso:
        _, a, b = graph_diff(to_isomorphic(g_avant), to_isomorphic(g_apres))
        for t in sorted(a)[:20]:
            print("    - instantané", t)
        for t in sorted(b)[:20]:
            print("    + courant   ", t)
    else:
        INSTANTANE.unlink()
        print(f"Instantané supprimé ({INSTANTANE.name}).")
    return 0 if all(res) else 1


if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in ("avant", "apres"):
        sys.exit(__doc__)
    base = sys.argv[2] if len(sys.argv) > 2 else "http://localhost:5000/api"
    raise SystemExit(avant(base) if sys.argv[1] == "avant" else apres(base))
