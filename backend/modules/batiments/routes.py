"""API REST du module Bâtiments (Membre 3 · Abir Mosrati) : /api/batiments/..."""
from flask import Blueprint, jsonify, request

import store
from . import nlp
from . import queries as Q
from .validation import valider

bp = Blueprint("batiments", __name__, url_prefix="/api/batiments")

HEURES_PAR_AN = 8760
VIA_LABELS = {
    "direct": "assertion directe",
    "inverse": "produitEnergiePour⁻¹ (owl:inverseOf)",
    "R1": "règle R1 (ligne qui transporte vers le bâtiment)",
    "R6": "règle R6 (via un stockage)",
    "R7": "règle R7 (ligne de raccordement)",
    "R2": "règle R2 (alimente → possedeStockage)",
    "R3": "règle R3 (estRaccordeA ∘ relie)",
}


def _err(message, status=400, **extra):
    return jsonify({"error": message, **extra}), status


def _invalide(erreurs):
    """422 avec une erreur par champ, pour l'affichage sous chaque champ du formulaire."""
    return _err(next(iter(erreurs.values())), 422, champs=erreurs)


def _float_arg(name):
    raw = request.args.get(name)
    try:
        return float(raw) if raw not in (None, "") else None
    except ValueError:
        return None


def _r(x, n=2):
    return round(x, n) if isinstance(x, (int, float)) else None


# ---------------------------------------------------------------- bâtiments --

def _relations(batiment_id=None):
    """{bâtiment: {ligne|source|stockage|poste|compteur: [{id, via, (renouvelable)}]}}"""
    out = {}
    for r in store.select(Q.relations(batiment_id)):
        rel = out.setdefault(r["b"], {k: [] for k in ("ligne", "source", "stockage", "poste", "compteur")})
        liste = rel[r["rel"]]
        if any(x["id"] == r["cible"] and x["via"] == r["via"] for x in liste):
            continue
        item = {"id": r["cible"], "via": r["via"]}
        if r["rel"] == "source":
            item["renouvelable"] = bool(r["renouvelable"])
        liste.append(item)
    return out


def _batiment(row, rel):
    rel = rel or {k: [] for k in ("ligne", "source", "stockage", "poste", "compteur")}
    definies = [Q.DEFINIES[k] for k in ("autonome", "vert", "gros", "intelligent", "ht") if row[k]]
    return {
        "id": row["b"],
        "label": row["label"] or row["b"],
        "classe": row["classe"],
        "adresse": row["adresse"],
        "consommation": row["conso"],
        "surface": row["surface"],
        "occupants": row["occupants"],
        "annee": row["annee"],
        "dpe": row["dpe"],
        "puissance": row["puissance"],
        "intensite": _r(row["intensite"], 1),
        "dpeCalcule": row["dpeCalcule"],
        "consoHoraire": _r((row["conso"] or 0) / HEURES_PAR_AN, 1) if row["conso"] is not None else None,
        "lignes": rel["ligne"],
        "sources": rel["source"],
        "stockages": rel["stockage"],
        "postes": rel["poste"],
        "compteurs": rel["compteur"],
        "classesDeduites": definies,
    }


def _lister(**filtres):
    sparql = Q.lister(**filtres)
    rows = store.select(sparql)
    rel = _relations() if rows else {}
    return [_batiment(r, rel.get(r["b"])) for r in rows], sparql


@bp.get("/")
def statut():
    return jsonify({"module": "batiments", "membre": "Abir Mosrati", "statut": "complet",
                    "classesDefinies": list(Q.DEFINIES.values())})


@bp.get("/batiments")
def lister():
    items, sparql = _lister(
        q=request.args.get("q", "").strip() or None,
        type_=request.args.get("type") or None,
        definie=request.args.get("definie") or None,
        conso_min=_float_arg("consoMin"),
        conso_max=_float_arg("consoMax"),
        ligne=request.args.get("ligne") or None,
        poste=request.args.get("poste") or None,
        source=request.args.get("source") or None,
        dpe=(request.args.get("dpe") or "").upper() or None,
    )
    return jsonify({"items": items, "sparql": sparql.strip()})


@bp.get("/batiments/<bid>")
def detail(bid):
    rows = store.select(Q.lister(ids=[bid]))
    if not rows:
        return _err("Bâtiment introuvable", 404)
    item = _batiment(rows[0], _relations(bid).get(bid))
    sparql = Q.detail(bid)
    return jsonify({"item": item, "triplets": store.select(sparql), "sparql": sparql.strip()})


@bp.post("/batiments")
def creer():
    d = request.get_json(silent=True) or {}
    if erreurs := valider(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/batiments/<bid>")
def modifier(bid):
    if not store.ask(Q.ask_type(bid, "Batiment")):
        return _err("Bâtiment introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": bid}
    if erreurs := valider(d, creation=False):
        return _invalide(erreurs)
    sparql = Q.modifier(d)
    store.update(sparql)
    return jsonify({"id": bid, "sparql": sparql.strip()})


@bp.patch("/batiments/<bid>/consommation")
def changer_consommation(bid):
    """Met à jour la seule valeur consommationAnnuelle (fonctionnelle) : DELETE/INSERT."""
    if not store.ask(Q.ask_type(bid, "Batiment")):
        return _err("Bâtiment introuvable", 404)
    d = request.get_json(silent=True) or {}
    try:
        conso = float(d.get("consommation"))
    except (TypeError, ValueError):
        return _invalide({"consommation": "Doit être un nombre"})
    if not 0 <= conso <= 1_000_000_000:
        return _invalide({"consommation": "Entre 0 et 1 000 000 000 kWh (consommationAnnuelle only float[≥ 0])"})
    sparql = Q.changer_consommation(bid, conso)
    store.update(sparql)
    return jsonify({"id": bid, "consommation": conso, "gros": conso >= Q.SEUIL_GROS, "sparql": sparql.strip()})


@bp.delete("/batiments/<bid>")
def supprimer(bid):
    if not store.ask(Q.ask_type(bid, "Batiment")):
        return _err("Bâtiment introuvable", 404)
    deps = store.select(Q.dependances(bid))
    if deps and request.args.get("force") != "true":
        return _err("Des individus d'autres modules pointent vers ce bâtiment", 409,
                    dependances=[{"id": r["s"], "relation": r["relation"]} for r in deps])
    store.forget_distinct(store.iri(bid))
    sparql = Q.supprimer(bid)
    store.update(sparql)
    return jsonify({"id": bid, "sparql": sparql.strip()})


# ------------------------------------------------------ vue d'ensemble ----

@bp.get("/stats")
def statistiques():
    s = store.select(Q.STATISTIQUES)[0]
    types = {r["classe"]: {"nb": int(r["nb"] or 0), "consommation": float(r["conso"] or 0)}
             for r in store.select(Q.PAR_TYPE)}
    conso = float(s["consoTotale"] or 0)
    return jsonify({
        "nb": int(s["nb"] or 0),
        "consoTotale": conso,
        "consoVerte": float(s["consoVerte"] or 0),
        "partVerte": _r(float(s["consoVerte"] or 0) / conso * 100, 1) if conso else 0,
        "intensiteMoyenne": _r(float(s["intensiteMoyenne"] or 0), 1),
        "occupants": int(s["occupantsTotal"] or 0),
        "parClasseDefinie": {
            "BatimentAutonome": int(s["nbAutonomes"] or 0),
            "BatimentVert": int(s["nbVerts"] or 0),
            "GrosConsommateur": int(s["nbGros"] or 0),
            "BatimentIntelligent": int(s["nbIntelligents"] or 0),
            "BatimentRaccordeHT": int(s["nbHT"] or 0),
        },
        "parType": types,
        "sparql": Q.STATISTIQUES.strip(),
    })


@bp.get("/options")
def options():
    """Listes de choix pour les formulaires (lignes, sources, stockages, postes)."""
    out = {"lignes": {}, "sources": {}, "stockages": {}, "postes": {}}
    for r in store.select(Q.OPTIONS):
        groupe = out[r["groupe"]]
        item = groupe.setdefault(r["id"], {"id": r["id"], "label": r["label"] or r["id"]})
        if r["groupe"] == "lignes":
            item["tension"] = r["tension"]
            item.setdefault("sources", [])
        elif r["groupe"] == "stockages":
            item.setdefault("sources", [])
        elif r["groupe"] == "sources":
            item["renouvelable"] = bool(r["renouvelable"])
        if r["lie"] and r["lie"] not in item.get("sources", [r["lie"]]):
            item["sources"].append(r["lie"])
    return jsonify({k: list(v.values()) for k, v in out.items()})


# ------------------------------------------- déclaré vs déduit (HermiT) ----

def _grouper(items):
    """[{id, via}] → {id: [via, …]} en gardant l'ordre."""
    out = {}
    for x in items:
        out.setdefault(x["id"], [])
        if x["via"] not in out[x["id"]]:
            out[x["id"]].append(x["via"])
    return out


def _justifier(b):
    """Pour chaque classe définie déduite : la raison, à la manière de l'explication HermiT."""
    renouv = [s for s in b["sources"] if s["renouvelable"]]
    lignes_ht = b.get("_lignesHT", [])
    out = []
    for c in b["classesDeduites"]:
        if c == "BatimentVert":
            raison = ", ".join(f"{sid} ({' · '.join(vias)})" for sid, vias in _grouper(renouv).items())
        elif c == "BatimentAutonome":
            raison = (f"source renouvelable ({', '.join(sorted({s['via'] for s in renouv}))}) "
                      f"+ stockage {', '.join(x['id'] for x in b['stockages'])} (R2)")
        elif c == "GrosConsommateur":
            raison = f"consommationAnnuelle = {b['consommation']:,.0f} kWh ≥ 1 000 000".replace(",", " ")
        elif c == "BatimentIntelligent":
            raison = f"equipeDe {', '.join(x['id'] for x in b['compteurs'])} (inverse de installeDans)"
        else:
            raison = f"estRaccordeA {', '.join(lignes_ht)} (LigneHauteTension : tension ≥ 63 kV)"
        out.append({"classe": c, "raison": raison})
    return out


@bp.get("/inferences")
def inferences():
    """Tableau « déclaré / déduit / grâce à » : classes définies, R3, R7, R6, R1, inverses."""
    items, sparql = _lister()
    tensions = {r["id"]: r["tension"] for r in store.select(Q.OPTIONS) if r["groupe"] == "lignes"}
    lignes = []
    for b in items:
        b["_lignesHT"] = [l["id"] for l in b["lignes"]
                          if l["via"] == "estRaccordeA" and (tensions.get(l["id"]) or 0) >= Q.SEUIL_HT]
        relations = []
        directes = {s["id"] for s in b["sources"] if s["via"] == "direct"}
        for sid, vias in _grouper([s for s in b["sources"] if s["via"] != "direct"]).items():
            if sid not in directes:
                relations.append({"propriete": "estAlimentePar", "valeur": sid, "via": " · ".join(vias),
                                  "explication": " ; ".join(VIA_LABELS[v] for v in vias)})
        for p in b["postes"]:
            if p["via"] == "R3":
                relations.append({"propriete": "estDesserviPar", "valeur": p["id"], "via": "R3",
                                  "explication": VIA_LABELS["R3"]})
        for x in b["stockages"]:
            if x["via"] == "R2":
                relations.append({"propriete": "possedeStockage", "valeur": x["id"], "via": "R2",
                                  "explication": VIA_LABELS["R2"]})
        for c in b["compteurs"]:
            if c["via"] != "equipeDe":
                relations.append({"propriete": "equipeDe", "valeur": c["id"], "via": "inverse",
                                  "explication": "equipeDe ≡ installeDans⁻¹ (owl:inverseOf)"})
        lignes.append({"id": b["id"], "label": b["label"], "declare": b["classe"],
                       "classes": _justifier(b), "relations": relations})
    return jsonify({"items": lignes, "sparql": sparql.strip(), "relationsSparql": Q.relations().strip()})


# --------------------------------------------- diagnostic énergétique ----

def _diagnostic():
    items, sparql = _lister()
    out = []
    for b in items:
        if b["intensite"] is None:
            statut = "incomplet"
        elif not b["dpe"]:
            statut = "absent"
        elif b["dpe"] == b["dpeCalcule"]:
            statut = "conforme"
        else:
            statut = "ecart"
        out.append({"id": b["id"], "label": b["label"], "classe": b["classe"],
                    "consommation": b["consommation"], "surface": b["surface"],
                    "intensite": b["intensite"], "dpe": b["dpe"], "dpeCalcule": b["dpeCalcule"],
                    "statut": statut})
    out.sort(key=lambda x: -(x["intensite"] or 0))
    return out, sparql


@bp.get("/diagnostic")
def diagnostic():
    """Intensité énergétique (kWh/m²/an) et classe DPE recalculée en SPARQL vs classe déclarée."""
    items, sparql = _diagnostic()
    resume = {k: sum(1 for x in items if x["statut"] == k) for k in ("conforme", "ecart", "absent", "incomplet")}
    return jsonify({"items": items, "resume": resume,
                    "seuils": [{"classe": c, "max": m} for c, m in Q.SEUILS_DPE] + [{"classe": "G", "max": None}],
                    "sparql": sparql.strip()})


@bp.post("/diagnostic/appliquer")
def appliquer_diagnostic():
    """Remplace classeEnergetique (fonctionnelle) par la classe recalculée : SPARQL DELETE/INSERT."""
    d = request.get_json(silent=True) or {}
    ids = d.get("ids")
    if ids is not None and (not isinstance(ids, list) or not all(isinstance(x, str) for x in ids)):
        return _invalide({"ids": "Liste d'identifiants attendue"})
    requetes, changements = [], []
    for b in _diagnostic()[0]:
        if b["statut"] not in ("ecart", "absent") or (ids is not None and b["id"] not in ids):
            continue
        sparql = Q.changer_dpe(b["id"], b["dpeCalcule"])
        store.update(sparql)
        requetes.append(sparql.strip())
        changements.append({"id": b["id"], "avant": b["dpe"], "apres": b["dpeCalcule"]})
    return jsonify({"changements": changements, "sparql": "\n\n".join(requetes)})


# ------------------------------------------------------------ NLP → SPARQL --

@bp.post("/nlp")
def question_nlp():
    """Question en français → analyse spaCy → requête SPARQL → résultats."""
    question = str((request.get_json(silent=True) or {}).get("question", "")).strip()
    if len(question) < 3:
        return _err("Posez une question d'au moins 3 caractères", 422)
    if len(question) > 300:
        return _err("Question trop longue (300 caractères au maximum)", 422)
    return jsonify(nlp.repondre(question))


@bp.get("/nlp/exemples")
def exemples_nlp():
    return jsonify(nlp.EXEMPLES)
