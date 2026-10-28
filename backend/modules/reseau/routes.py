"""API REST du module Réseau : /api/reseau/..."""
from flask import Blueprint, jsonify, request

import store
from . import nlp
from . import queries as Q
from .validation import valider_ligne, valider_poste

bp = Blueprint("reseau", __name__, url_prefix="/api/reseau")


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


# ------------------------------------------------------------------ lignes --

def _ligne(row):
    return {
        "id": row["ligne"],
        "label": row["label"] or row["ligne"],
        "tension": row["tension"],
        "longueur": row["longueur"],
        "annee": row["annee"],
        "categorie": row["categorie"],
        "postes": _split(row["postes"]),
        "batiments": _split(row["batiments"]),
        "gestionnaires": _split(row["gestionnaires"]),
    }


@bp.get("/lignes")
def lister_lignes():
    sparql = Q.lister_lignes(
        q=request.args.get("q", "").strip() or None,
        categorie=request.args.get("categorie") or None,
        tension_min=_float_arg("tensionMin"),
        tension_max=_float_arg("tensionMax"),
        poste=request.args.get("poste") or None,
    )
    return jsonify({"items": [_ligne(r) for r in store.select(sparql)], "sparql": sparql.strip()})


@bp.get("/lignes/<ligne_id>")
def detail_ligne(ligne_id):
    rows = [r for r in store.select(Q.lister_lignes()) if r["ligne"] == ligne_id]
    if not rows:
        return _err("Ligne introuvable", 404)
    ligne = _ligne(rows[0])
    sparql = Q.detail_ligne(ligne_id)
    liens = store.select(sparql)
    ligne["sources"] = [r["cible"] for r in liens if r["relation"] == "injecteDans"]
    ligne["batimentsRaccordes"] = [r["cible"] for r in liens if r["relation"] == "estRaccordeA"]
    return jsonify({"item": ligne, "sparql": sparql.strip()})



@bp.post("/lignes")
def creer_ligne():
    d = request.get_json(silent=True) or {}
    if erreurs := valider_ligne(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer_ligne(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/lignes/<ligne_id>")
def modifier_ligne(ligne_id):
    if not store.ask(Q.ask_type(ligne_id, "LigneElectrique")):
        return _err("Ligne introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": ligne_id}
    if erreurs := valider_ligne(d, creation=False):
        return _invalide(erreurs)
    sparql = Q.modifier_ligne(d)
    store.update(sparql)
    return jsonify({"id": ligne_id, "sparql": sparql.strip()})


@bp.delete("/lignes/<ligne_id>")
def supprimer_ligne(ligne_id):
    if not store.ask(Q.ask_type(ligne_id, "LigneElectrique")):
        return _err("Ligne introuvable", 404)
    deps = store.select(Q.dependances(ligne_id))
    if deps and request.args.get("force") != "true":
        return _err("Des individus d'autres modules pointent vers cette ligne", 409,
                    dependances=[{"id": r["s"], "relation": r["relation"]} for r in deps])
    store.forget_distinct(store.iri(ligne_id))
    sparql = Q.supprimer(ligne_id)
    store.update(sparql)
    return jsonify({"id": ligne_id, "sparql": sparql.strip()})


# ------------------------------------------------------------------ postes --

def _poste(row):
    return {
        "id": row["poste"],
        "label": row["label"] or row["poste"],
        "ville": row["ville"],
        "capacite": row["capacite"],
        "annee": row["annee"],
        "nbLignes": int(row["nbLignes"] or 0),
        "lignes": _split(row["lignes"]),
        "connexions": _split(row["connexions"]),
        "secours": _split(row["secours"]),
        "secourusPar": _split(row["secourusPar"]),
        "gestionnaires": _split(row["gestionnaires"]),
        "batimentsDesservis": _split(row["batimentsDesservis"]),
    }


@bp.get("/postes")
def lister_postes():
    sparql = Q.lister_postes(request.args.get("q", "").strip() or None)
    return jsonify({"items": [_poste(r) for r in store.select(sparql)], "sparql": sparql.strip()})



@bp.post("/postes")
def creer_poste():
    d = request.get_json(silent=True) or {}
    if erreurs := valider_poste(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer_poste(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/postes/<poste_id>")
def modifier_poste(poste_id):
    if not store.ask(Q.ask_type(poste_id, "PosteElectrique")):
        return _err("Poste introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": poste_id}
    if erreurs := valider_poste(d, creation=False):
        return _invalide(erreurs)
    sparql = Q.modifier_poste(d)
    store.update(sparql)
    return jsonify({"id": poste_id, "sparql": sparql.strip()})


@bp.delete("/postes/<poste_id>")
def supprimer_poste(poste_id):
    if not store.ask(Q.ask_type(poste_id, "PosteElectrique")):
        return _err("Poste introuvable", 404)
    orphelines = [r["ligne"] for r in store.select(Q.lignes_orphelines(poste_id))]
    if orphelines and request.args.get("force") != "true":
        return _err("Ces lignes n'auraient plus aucun poste (relie min 1 PosteElectrique)", 409,
                    dependances=[{"id": l, "relation": "relie"} for l in orphelines])
    store.forget_distinct(store.iri(poste_id))
    sparql = Q.supprimer(poste_id)
    store.update(sparql)
    return jsonify({"id": poste_id, "sparql": sparql.strip()})


# ------------------------------------------------------ vue d'ensemble ----

@bp.get("/stats")
def statistiques():
    s = store.select(Q.STATISTIQUES)[0]
    n = store.select(Q.NB_POSTES)[0]
    return jsonify({
        "nbLignes": int(s["nbLignes"] or 0),
        "nbPostes": int(n["n"] or 0),
        "longueurTotale": float(s["longueurTotale"] or 0),
        "tensionMax": float(s["tensionMax"] or 0),
        "parCategorie": {k: int(s[f"nb{k}"] or 0) for k in ("HT", "MT", "BT")},
        "sparql": Q.STATISTIQUES.strip(),
    })


@bp.get("/options")
def options():
    """Listes de choix pour les formulaires (postes, bâtiments, opérateurs, sources)."""
    out = {"postes": [], "batiments": [], "operateurs": [], "sources": []}
    seen = set()
    for r in store.select(Q.OPTIONS):
        key = (r["groupe"], r["id"])
        if key not in seen:
            seen.add(key)
            out[r["groupe"]].append({"id": r["id"], "label": r["label"] or r["id"]})
    return jsonify(out)


@bp.get("/graphe")
def graphe():
    """Nœuds et arêtes du réseau pour la visualisation."""
    opts = options().get_json()
    types = {o["id"]: g for g, items in opts.items() for o in items}
    labels = {o["id"]: o["label"] for items in opts.values() for o in items}
    lignes = {l["id"]: l for l in (_ligne(r) for r in store.select(Q.lister_lignes()))}

    edges, used = [], set()
    for r in store.select(Q.GRAPHE):
        s, o = r["s"], r["o"]
        if s is None or o is None:
            continue
        edges.append({"source": s, "target": o, "relation": r["relation"]})
        used.update((s, o))

    nodes = []
    for node_id in sorted(used | set(lignes)):
        if node_id in lignes:
            l = lignes[node_id]
            nodes.append({"id": node_id, "label": l["label"], "type": "ligne",
                          "categorie": l["categorie"], "tension": l["tension"]})
        elif node_id in types:
            nodes.append({"id": node_id, "label": labels[node_id], "type": types[node_id][:-1]})
    return jsonify({"nodes": nodes, "edges": edges, "sparql": Q.GRAPHE.strip()})


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
