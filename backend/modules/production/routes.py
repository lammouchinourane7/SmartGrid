"""API REST du module Production d'énergie (Membre 1 · Wala Rezgui) : /api/production/..."""
from flask import Blueprint, jsonify, request

import store
from . import nlp
from . import queries as Q
from .validation import parse_date, valider

bp = Blueprint("production", __name__, url_prefix="/api/production")

# comment changer un chemin d'alimentation déduit (une déduction ne se supprime pas directement)
ORIGINE = {
    "produitEnergiePour": "lien direct déclaré dans ce module (formulaire de la source)",
    "estAlimentePar": "lien direct déclaré côté Bâtiments (module Bâtiments)",
    "R1": "déduit par R1 : modifier injecteDans (ici) ou transporteVers de la ligne (module Réseau)",
    "R7": "déduit par R7 : modifier injecteDans (ici) ou estRaccordeA du bâtiment (module Bâtiments)",
    "R6": "déduit par R6 : modifier stockeEnergieDe ou alimente du stockage (module Stockage)",
}


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
        v = float(raw) if raw not in (None, "") else None
        return v if v is None or v == v else None
    except ValueError:
        return None


def _iso(value):
    return str(value).replace(" ", "T") if value is not None else None


def _existe(source_id):
    return store.valid_id(source_id) and store.ask(Q.ask_type(source_id, "SourceEnergie"))


def _alimentation(source=None, batiment=None):
    """{source: {bâtiment: [{via, par, origine}]}} — un bâtiment, plusieurs justifications, sans doublon."""
    out = {}
    for r in store.select(Q.alimentation(source, batiment)):
        chemins = out.setdefault(r["s"], {}).setdefault(r["b"], [])
        chemin = {"via": r["via"], "par": r["par"], "origine": ORIGINE[r["via"]]}
        if chemin not in chemins:
            chemins.append(chemin)
    return out


def _source(row, alim=None):
    types = _split(row["types"])
    batiments = (alim or {}).get(row["s"], {})
    return {
        "id": row["s"],
        "label": row["label"] or row["s"],
        "type": types[0] if len(types) == 1 else None,
        "types": types,
        "famille": "renouvelable" if row["renouvelable"] else "non_renouvelable" if row["nonRenouvelable"] else "non_classee",
        "puissance": row["puissance"],
        "date": _iso(row["date"]),
        "lignes": _split(row["lignes"]),
        "nbBatiments": len(batiments),
        "batimentsDirects": sorted(b for b, ch in batiments.items()
                                   if any(c["via"] == "produitEnergiePour" for c in ch)),
    }


# ------------------------------------------------------------------ sources --

@bp.get("/sources")
def lister():
    date_min = parse_date(request.args.get("dateMin")) if request.args.get("dateMin") else None
    date_max = parse_date(request.args.get("dateMax")) if request.args.get("dateMax") else None
    if request.args.get("dateMin") and not date_min or request.args.get("dateMax") and not date_max:
        return _err("Date de filtre invalide (AAAA-MM-JJ)", 422)
    if date_max and len(request.args.get("dateMax", "")) == 10:
        date_max = date_max[:10] + "T23:59:59"  # la journée entière
    sparql = Q.lister(
        q=request.args.get("q", "").strip() or None,
        categorie=request.args.get("categorie") or None,
        puissance_min=_float_arg("puissanceMin"),
        puissance_max=_float_arg("puissanceMax"),
        sans_puissance=request.args.get("sansPuissance") == "true",
        date_min=date_min, date_max=date_max,
    )
    alim = _alimentation()
    return jsonify({"items": [_source(r, alim) for r in store.select(sparql)], "sparql": sparql.strip()})


@bp.get("/sources/<source_id>")
def detail(source_id):
    if not _existe(source_id):
        return _err("Source introuvable", 404)
    alim = _alimentation(source=source_id)
    item = _source(store.select(Q.lister(source=source_id))[0], alim)
    item["alimentation"] = [{"batiment": b, "chemins": ch} for b, ch in sorted(alim.get(source_id, {}).items())]
    item["liens"] = {"lignes": [], "stockages": [], "mesures": []}
    for r in store.select(Q.liens(source_id)):
        lien = {"id": r["x"], "label": r["label"] or r["x"]}
        if r["relation"] == "ligne":
            lien["tension"] = r["tension"]
        if r["relation"] == "mesure":
            lien |= {"valeurKWh": r["valeur"], "debut": _iso(r["debut"]), "fin": _iso(r["fin"])}
        groupe = item["liens"][r["relation"] + "s"]
        if lien not in groupe:
            groupe.append(lien)
    return jsonify({"item": item, "sparql": Q.alimentation(source_id).strip()})


@bp.post("/sources")
def creer():
    d = request.get_json(silent=True) or {}
    if erreurs := valider(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/sources/<source_id>")
def modifier(source_id):
    if not _existe(source_id):
        return _err("Source introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": source_id}
    if erreurs := valider(d, creation=False):
        return _invalide(erreurs)
    sparql = Q.modifier(d)
    store.update(sparql)
    return jsonify({"id": source_id, "sparql": sparql.strip()})


@bp.get("/sources/<source_id>/dependances")
def dependances(source_id):
    if not _existe(source_id):
        return _err("Source introuvable", 404)
    return jsonify(_dependances(source_id))


def _dependances(source_id):
    """Bloquantes : toute relation entrante (autre module) ou sortante non possédée par Production.
    Supprimées avec la source : ses propres triplets (injecteDans, produitEnergiePour…)."""
    bloquantes, supprimees = [], []
    for r in store.select(Q.references(source_id)):
        lien = {"id": r["x"], "relation": r["relation"], "sens": r["sens"]}
        if r["sens"] == "entrante" or r["relation"] not in Q.PROPRIETES_PROPRES:
            bloquantes.append(lien)
        elif r["relation"] in ("injecteDans", "produitEnergiePour"):
            supprimees.append(lien)
    return {"bloquantes": bloquantes, "supprimees": supprimees}


@bp.delete("/sources/<source_id>")
def supprimer(source_id):
    if not _existe(source_id):
        return _err("Source introuvable", 404)
    deps = _dependances(source_id)
    if deps["bloquantes"]:
        return _err("Cette source est référencée par d'autres modules : suppression bloquée. "
                    "Retirez d'abord ces liens dans les modules concernés.", 409, dependances=deps["bloquantes"])
    store.forget_distinct(store.iri(source_id))
    sparql = Q.supprimer(source_id)
    store.update(sparql)
    return jsonify({"id": source_id, "supprimees": deps["supprimees"], "sparql": sparql})


# ------------------------------------------------------- vue d'ensemble ----

@bp.get("/")
def statut():
    return jsonify({"module": "production", "membre": "Wala Rezgui", "statut": "implémenté"})


@bp.get("/options")
def options():
    out = {"lignes": [], "batiments": [], "sources": []}
    seen = set()
    for r in store.select(Q.OPTIONS):
        if (r["groupe"], r["id"]) in seen:
            continue
        seen.add((r["groupe"], r["id"]))
        item = {"id": r["id"], "label": r["label"] or r["id"], "classe": r["classe"]}
        if r["groupe"] == "lignes":
            item["tension"] = r["tension"]
        out[r["groupe"]].append(item)
    return jsonify(out)


@bp.get("/stats")
def statistiques():
    s = store.select(Q.STATISTIQUES)[0]
    e = store.select(Q.ENERGIE_MESUREE)[0]
    nb = int(s["nb"] or 0)
    return jsonify({
        "nbSources": nb,
        "nbRenouvelables": int(s["nbRenouvelables"] or 0),
        "nbNonRenouvelables": int(s["nbNonRenouvelables"] or 0),
        "nbAvecPuissance": int(s["nbAvecPuissance"] or 0),
        "nbSansPuissance": nb - int(s["nbAvecPuissance"] or 0),
        "puissanceTotaleKW": float(s["puissanceTotale"] or 0),
        "parType": [{"type": r["type"], "nb": int(r["nb"] or 0), "nbAvecPuissance": int(r["nbAvecPuissance"] or 0),
                     "puissanceKW": float(r["puissance"] or 0)} for r in store.select(Q.PAR_TYPE)],
        "energieMesuree": {
            "nbMesures": int(e["nbMesures"] or 0), "nbSources": int(e["nbSources"] or 0),
            "totalKWh": float(e["totalKWh"] or 0), "debut": _iso(e["debut"]), "fin": _iso(e["fin"]),
            "chevauchements": [{"m1": r["m1"], "m2": r["m2"], "source": r["s"]} for r in store.select(Q.CHEVAUCHEMENTS)],
            "regle": ("Somme des valeurKWh des mesures de production (module Mesure) qui concernent une source, "
                      "toutes périodes confondues. Ce n'est pas une estimation à partir de la puissance installée."),
        },
        "sparql": Q.STATISTIQUES.strip(),
    })


# ------------------------------------------------------------ NLP → SPARQL --

@bp.post("/nlp")
def question_nlp():
    """Question en français → analyse spaCy → requête SPARQL → résultats (lecture seule)."""
    question = str((request.get_json(silent=True) or {}).get("question", "")).strip()
    if len(question) < 3:
        return _err("Posez une question d'au moins 3 caractères", 422)
    if len(question) > 300:
        return _err("Question trop longue (300 caractères au maximum)", 422)
    return jsonify(nlp.repondre(question))


@bp.get("/nlp/exemples")
def exemples_nlp():
    return jsonify(nlp.EXEMPLES)
