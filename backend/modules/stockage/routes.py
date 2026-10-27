"""API REST du module Stockage (Membre 2 · Takoua Naceur) : /api/stockage/..."""
from flask import Blueprint, jsonify, request

import store
from . import nlp
from . import queries as Q
from .validation import valider

bp = Blueprint("stockage", __name__, url_prefix="/api/stockage")

HEURES_PAR_AN = 8760


def _split(value):
    return [v for v in (value or "").split("|") if v]


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


# ---------------------------------------------------------------- systèmes --

def _systeme(row):
    definies = [Q.DEFINIES[k] for k in ("vert", "critique", "grande", "secours") if row[k]]
    return {
        "id": row["x"],
        "label": row["label"] or row["x"],
        "classe": row["classe"],
        "famille": row["famille"] or row["classe"],
        "capacite": row["capacite"],
        "niveau": row["niveau"],
        "rendement": row["rendement"],
        "puissance": row["puissance"],
        "technologie": row["techno"],
        "annee": row["annee"],
        "poste": row["poste"],
        "sources": _split(row["sources"]),
        "batiments": _split(row["batiments"]),
        "energie": _r(row["energie"], 1),
        "autonomie": _r(row["autonomie"]),
        "classesDeduites": definies,
    }


def _lister(**filtres):
    sparql = Q.lister(**filtres)
    return [_systeme(r) for r in store.select(sparql)], sparql


@bp.get("/systemes")
def lister():
    items, sparql = _lister(
        q=request.args.get("q", "").strip() or None,
        famille=request.args.get("famille") or None,
        definie=request.args.get("definie") or None,
        niveau_min=_float_arg("niveauMin"),
        niveau_max=_float_arg("niveauMax"),
        capacite_min=_float_arg("capaciteMin"),
        source=request.args.get("source") or None,
        batiment=request.args.get("batiment") or None,
        poste=request.args.get("poste") or None,
    )
    return jsonify({"items": items, "sparql": sparql.strip()})


@bp.get("/systemes/<sid>")
def detail(sid):
    items = [s for s in _lister()[0] if s["id"] == sid]
    if not items:
        return _err("Système de stockage introuvable", 404)
    sparql = Q.detail(sid)
    return jsonify({"item": items[0], "triplets": store.select(sparql), "sparql": sparql.strip()})


@bp.post("/systemes")
def creer():
    d = request.get_json(silent=True) or {}
    if erreurs := valider(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/systemes/<sid>")
def modifier(sid):
    if not store.ask(Q.ask_type(sid, "SystemeStockage")):
        return _err("Système de stockage introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": sid}
    if erreurs := valider(d, creation=False):
        return _invalide(erreurs)
    sparql = Q.modifier(d)
    store.update(sparql)
    return jsonify({"id": sid, "sparql": sparql.strip()})


@bp.patch("/systemes/<sid>/niveau")
def changer_niveau(sid):
    """Recharge / décharge : met à jour la seule valeur niveauCharge (DELETE/INSERT)."""
    if not store.ask(Q.ask_type(sid, "SystemeStockage")):
        return _err("Système de stockage introuvable", 404)
    d = request.get_json(silent=True) or {}
    try:
        niveau = float(d.get("niveau"))
    except (TypeError, ValueError):
        return _invalide({"niveau": "Doit être un nombre"})
    if not 0 <= niveau <= 100:
        return _invalide({"niveau": "Entre 0 et 100 % (niveauCharge only float[≥ 0, ≤ 100])"})
    sparql = Q.changer_niveau(sid, niveau)
    store.update(sparql)
    return jsonify({"id": sid, "niveau": niveau, "sparql": sparql.strip()})


@bp.delete("/systemes/<sid>")
def supprimer(sid):
    if not store.ask(Q.ask_type(sid, "SystemeStockage")):
        return _err("Système de stockage introuvable", 404)
    deps = store.select(Q.dependances(sid))
    if deps and request.args.get("force") != "true":
        return _err("Des individus d'autres modules pointent vers ce stockage", 409,
                    dependances=[{"id": r["s"], "relation": r["relation"]} for r in deps])
    store.forget_distinct(store.iri(sid))
    sparql = Q.supprimer(sid)
    store.update(sparql)
    return jsonify({"id": sid, "sparql": sparql.strip()})


# ------------------------------------------------------ vue d'ensemble ----

@bp.get("/stats")
def statistiques():
    s = store.select(Q.STATISTIQUES)[0]
    familles = {r["famille"]: {"nb": int(r["nb"] or 0), "capacite": float(r["capacite"] or 0)}
                for r in store.select(Q.PAR_FAMILLE)}
    return jsonify({
        "nb": int(s["nb"] or 0),
        "capaciteTotale": float(s["capaciteTotale"] or 0),
        "energieDisponible": float(s["energieDisponible"] or 0),
        "chargeMoyenne": _r(float(s["chargeMoyenne"] or 0), 1),
        "parClasseDefinie": {
            "StockageVert": int(s["nbVerts"] or 0),
            "StockageCritique": int(s["nbCritiques"] or 0),
            "StockageGrandeCapacite": int(s["nbGrands"] or 0),
            "StockageSecours": int(s["nbSecours"] or 0),
        },
        "parFamille": familles,
        "sparql": Q.STATISTIQUES.strip(),
    })


@bp.get("/options")
def options():
    """Listes de choix pour les formulaires (sources, bâtiments, postes)."""
    out = {"sources": [], "batiments": [], "postes": []}
    seen = set()
    for r in store.select(Q.OPTIONS):
        key = (r["groupe"], r["id"])
        if key in seen:
            continue
        seen.add(key)
        item = {"id": r["id"], "label": r["label"] or r["id"]}
        if r["groupe"] == "sources":
            item["renouvelable"] = bool(r["renouvelable"])
        out[r["groupe"]].append(item)
    return jsonify(out)


@bp.get("/batiments")
def batiments():
    """Bâtiments, stockages possédés (R2), sources renouvelables (direct, inverse, R1, R6)
    et classe définie BatimentAutonome déduite."""
    out = []
    for r in store.select(Q.BATIMENTS_AUTONOMES):
        sources = [dict(zip(("id", "via"), x.split("@", 1))) for x in _split(r["sourcesRenouvelables"])]
        stockages = _split(r["stockages"])
        out.append({
            "id": r["b"], "label": r["label"] or r["b"], "classe": r["classe"],
            "consommation": r["conso"], "stockages": stockages, "energie": _r(r["energie"], 1),
            "sourcesRenouvelables": sources,
            "autonome": bool(stockages) and bool(sources),
        })
    return jsonify({"items": out, "sparql": Q.BATIMENTS_AUTONOMES.strip()})


# ------------------------------------------------- scénario de coupure ----

def _calculer_scenario(poste, heures):
    sparql = Q.scenario_coupure(poste)
    batiments = []
    for r in store.select(sparql):
        conso_h = (r["conso"] or 0) / HEURES_PAR_AN          # kW moyen
        energie = float(r["energie"] or 0)                   # kWh disponibles
        puissance = float(r["puissance"] or 0)               # kW max en décharge
        stockages = _split(r["stockages"])
        if not stockages or energie <= 0 or conso_h <= 0:
            couverture, autonomie, fournie = 0.0, 0.0, 0.0
        else:
            appel = min(puissance or conso_h, conso_h)       # puissance réellement fournie
            couverture = appel / conso_h
            autonomie = energie / appel
            fournie = min(energie, appel * heures)
        if not stockages:
            statut = "coupe"
        elif couverture >= 0.999 and autonomie >= heures:
            statut = "tient"
        else:
            statut = "partiel"
        batiments.append({
            "id": r["b"], "label": r["label"] or r["b"], "stockages": stockages,
            "consoHoraire": _r(conso_h, 1), "energie": _r(energie, 1), "puissance": puissance or None,
            "couverture": _r(couverture * 100, 0), "autonomie": _r(autonomie, 2),
            "energieFournie": _r(fournie, 1), "statut": statut,
        })
    reseau = store.select(Q.stockages_du_poste(poste)) if poste else []
    return batiments, reseau, sparql


@bp.get("/scenario")
def scenario():
    """Coupure du poste ?poste= pendant ?heures= : qui tient grâce à son stockage ?"""
    poste = request.args.get("poste") or None
    if poste and not store.ask(Q.ask_type(poste, "PosteElectrique")):
        return _err("Poste introuvable", 404)
    heures = _float_arg("heures") or 2
    if not 0 < heures <= 72:
        return _err("Durée entre 0 et 72 heures", 422)
    batiments, reseau, sparql = _calculer_scenario(poste, heures)
    resume = {k: sum(1 for b in batiments if b["statut"] == k) for k in ("tient", "partiel", "coupe")}
    return jsonify({
        "poste": poste, "heures": heures, "batiments": batiments, "resume": resume,
        "stockagesReseau": [{"id": r["x"], "label": r["label"] or r["x"], "capacite": r["capacite"],
                             "niveau": r["niveau"], "puissance": r["puissance"],
                             "energie": _r((r["capacite"] or 0) * (r["niveau"] or 0) / 100, 1)}
                            for r in reseau],
        "sparql": sparql.strip(),
    })


@bp.post("/scenario/appliquer")
def appliquer_scenario():
    """Applique la coupure : décharge chaque stockage de l'énergie fournie (SPARQL UPDATE)."""
    d = request.get_json(silent=True) or {}
    poste = d.get("poste") or None
    try:
        heures = float(d.get("heures") or 2)
    except (TypeError, ValueError):
        return _invalide({"heures": "Doit être un nombre"})
    if not 0 < heures <= 72:
        return _invalide({"heures": "Durée entre 0 et 72 heures"})
    batiments, _, _ = _calculer_scenario(poste, heures)
    stockages = {s["id"]: s for s in _lister()[0]}

    requetes, changements = [], []
    for b in batiments:
        if not b["energieFournie"]:
            continue
        energies = {x: stockages[x]["energie"] or 0 for x in b["stockages"] if x in stockages}
        total = sum(energies.values())
        for x, e in energies.items():
            s = stockages[x]
            if not total or not s["capacite"]:
                continue
            retire = b["energieFournie"] * e / total        # au prorata de l'énergie de chaque stockage
            nouveau = max(0.0, round((e - retire) / s["capacite"] * 100, 1))
            sparql = Q.changer_niveau(x, nouveau)
            store.update(sparql)
            requetes.append(sparql.strip())
            changements.append({"id": x, "avant": s["niveau"], "apres": nouveau,
                                "critique": nouveau < Q.SEUIL_CRITIQUE})
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
