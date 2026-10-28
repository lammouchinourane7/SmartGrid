"""API REST du module Gestion et mesure (Membre 5 · Ibtihel Mechergui) : /api/mesure/..."""
from datetime import date

from flask import Blueprint, jsonify, request

import store
from . import nlp
from . import queries as Q
from .validation import parse_date, valider_compteur, valider_mesure, valider_operateur

bp = Blueprint("mesure", __name__, url_prefix="/api/mesure")

POLITIQUES = ("reaffecter", "conserver")


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


def _id_arg(name):
    """Identifiant d'individu passé en paramètre : refusé s'il ne respecte pas le format."""
    raw = (request.args.get(name) or "").strip()
    return raw if store.valid_id(raw) else None


def _iso(value):
    """datetime RDFLib ('2025-01-01 00:00:00') → '2025-01-01T00:00:00'."""
    return str(value).replace(" ", "T") if value is not None else None


def _existe(individu_id, classe):
    return store.valid_id(individu_id) and store.ask(Q.ask_type(individu_id, classe))


def _references_externes(individu_id, permises):
    """Références entrantes qui ne relèvent pas du module (bloquent la suppression)."""
    return [{"id": r["s"], "relation": r["relation"]}
            for r in store.select(Q.references_entrantes(individu_id)) if r["relation"] not in permises]


# ---------------------------------------------------------------- compteurs --

def _compteur(row):
    return {
        "id": row["c"],
        "label": row["label"] or row["c"],
        "identifiant": row["identifiant"],
        "batiments": _split(row["batiments"]),
        "nbBatiments": int(row["nbBatiments"] or 0),
        "mesures": _split(row["mesures"]),
        "nbMesures": int(row["nbMesures"] or 0),
    }


@bp.get("/compteurs")
def lister_compteurs():
    sparql = Q.lister_compteurs(q=request.args.get("q", "").strip() or None, batiment=_id_arg("batiment"))
    return jsonify({"items": [_compteur(r) for r in store.select(sparql)], "sparql": sparql.strip()})


@bp.get("/compteurs/<compteur_id>")
def detail_compteur(compteur_id):
    if not _existe(compteur_id, "CompteurIntelligent"):
        return _err("Compteur introuvable", 404)
    item = _compteur(store.select(Q.lister_compteurs(compteur=compteur_id))[0])
    sparql = Q.lister_mesures(compteur=compteur_id)
    item["detailMesures"] = [_mesure(r) for r in store.select(sparql)]
    return jsonify({"item": item, "sparql": sparql.strip()})


def _impact(compteur_id, nouveau):
    """Conséquences d'un changement de bâtiment sur les mesures de consommation du compteur."""
    anciens = [r["b"] for r in store.select(Q.batiments_du_compteur(compteur_id))]
    if nouveau in anciens and len(anciens) == 1:
        return anciens, []
    impactees = {}
    for r in store.select(Q.mesures_impactees(compteur_id)):
        m = impactees.setdefault(r["m"], {"id": r["m"], "label": r["label"] or r["m"], "concerneAssertee": []})
        if r["direct"]:
            m["concerneAssertee"].append(r["direct"])
    return anciens, list(impactees.values())


def _apercu(compteur_id, anciens, nouveau, impactees):
    """Triplets exacts retirés / ajoutés et cible finale, pour chaque politique (affichés avant confirmation)."""
    ancien = anciens[0] if len(anciens) == 1 else None
    jour = date.today().isoformat()
    out = {"reaffecter": [], "conserver": []}
    for m in impactees:
        assertes = [f"sg:{m['id']} sg:concerne sg:{b}" for b in m["concerneAssertee"]]
        out["reaffecter"].append({
            "mesure": m["id"], "retires": assertes, "ajoutes": [],
            "resultat": f"concerne sg:{nouveau} (déduit par R5 : sg:{compteur_id} installeDans sg:{nouveau})"})
        if ancien:
            out["conserver"].append({
                "mesure": m["id"],
                "retires": assertes + [f"sg:{compteur_id} sg:enregistre sg:{m['id']}"],
                "ajoutes": [f"sg:{m['id']} sg:concerne sg:{ancien}",
                            f"sg:{m['id']} rdfs:comment \"{Q.note_conserver(compteur_id, ancien, jour)}\""],
                "resultat": f"concerne sg:{ancien} (asserté) ; R5 ne s'applique plus (plus de lien enregistre)"})
    return out


@bp.get("/compteurs/<compteur_id>/impact")
def impact_compteur(compteur_id):
    """Aperçu, avant enregistrement, des mesures touchées par un changement de bâtiment."""
    if not _existe(compteur_id, "CompteurIntelligent"):
        return _err("Compteur introuvable", 404)
    nouveau = _id_arg("batiment")
    if not nouveau:
        return _err("Paramètre batiment manquant ou invalide", 422)
    anciens, impactees = _impact(compteur_id, nouveau)
    return jsonify({"anciens": anciens, "nouveau": nouveau, "mesures": impactees,
                    "apercu": _apercu(compteur_id, anciens, nouveau, impactees)})


@bp.post("/compteurs")
def creer_compteur():
    d = request.get_json(silent=True) or {}
    if erreurs := valider_compteur(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer_compteur(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/compteurs/<compteur_id>")
def modifier_compteur(compteur_id):
    if not _existe(compteur_id, "CompteurIntelligent"):
        return _err("Compteur introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": compteur_id}
    if erreurs := valider_compteur(d, creation=False):
        return _invalide(erreurs)

    anciens, impactees = _impact(compteur_id, d["batiment"])
    politique = request.args.get("politique")
    if impactees and politique not in POLITIQUES:
        return _err("Changer de bâtiment modifie le bâtiment déduit (R5) de ces mesures de consommation : "
                    "choisissez une politique", 409, anciens=anciens, nouveau=d["batiment"], mesures=impactees,
                    apercu=_apercu(compteur_id, anciens, d["batiment"], impactees))
    if impactees and politique == "conserver" and len(anciens) != 1:
        return _err("Impossible de conserver l'ancien bâtiment : le compteur n'en avait pas exactement un", 422)

    sparql = Q.modifier_compteur(d, politique, anciens[0] if anciens else None, [m["id"] for m in impactees],
                                 date.today().isoformat())
    store.update(sparql)
    return jsonify({"id": compteur_id, "politique": politique if impactees else None, "sparql": sparql.strip()})


@bp.delete("/compteurs/<compteur_id>")
def supprimer_compteur(compteur_id):
    if not _existe(compteur_id, "CompteurIntelligent"):
        return _err("Compteur introuvable", 404)
    # equipeDe est l'inverse de installeDans : c'est l'installation du compteur lui-même
    externes = _references_externes(compteur_id, {"equipeDe", "first"})
    if externes:
        return _err("D'autres individus font référence à ce compteur : suppression bloquée", 409,
                    dependances=externes, bloquant=True)
    mesures = store.select(Q.lister_mesures(compteur=compteur_id))
    if mesures and request.args.get("force") != "true":
        return _err("Ce compteur a enregistré des mesures. Elles seront conservées ; le bâtiment déduit "
                    "par R5 sera écrit en concerne explicite.", 409,
                    dependances=[{"id": r["m"], "relation": "enregistre"} for r in mesures])
    sparql = Q.figer_r5(compteur_id).strip() + " ;\n" + Q.supprimer(compteur_id)
    store.forget_distinct(store.iri(compteur_id))
    store.update(sparql)
    return jsonify({"id": compteur_id, "sparql": sparql})


# ------------------------------------------------------------------ mesures --

def _mesure(row):
    assertees, r5 = _split(row["ciblesAssertees"]), _split(row["ciblesR5"])
    cibles = [{"id": c, "via": "assertion"} for c in assertees]
    cibles += [{"id": c, "via": "R5"} for c in r5 if c not in assertees]
    return {
        "id": row["m"],
        "label": row["label"] or row["m"],
        "type": row["type"],
        "valeur": row["valeur"],
        "debut": _iso(row["debut"]),
        "fin": _iso(row["fin"]),
        "compteurs": _split(row["compteurs"]),
        "cibles": cibles,
    }


def _filtres_mesures():
    mode = request.args.get("mode")
    return dict(
        q=request.args.get("q", "").strip() or None,
        type_=request.args.get("type") or None,
        compteur=_id_arg("compteur"),
        cible_id=_id_arg("cible"),
        valeur_min=_float_arg("valeurMin"),
        valeur_max=_float_arg("valeurMax"),
        debut=parse_date(request.args.get("debut")) if request.args.get("debut") else None,
        fin=parse_date(request.args.get("fin"), fin=True) if request.args.get("fin") else None,
        mode="inclusion" if mode == "inclusion" else "chevauchement",
    )


@bp.get("/mesures")
def lister_mesures():
    f = _filtres_mesures()
    if request.args.get("debut") and not f["debut"] or request.args.get("fin") and not f["fin"]:
        return _err("Date de filtre invalide (AAAA-MM-JJ)", 422)
    if f["debut"] and f["fin"] and f["fin"] < f["debut"]:
        return _err("La date de fin du filtre précède la date de début", 422)
    sparql = Q.lister_mesures(**f)
    return jsonify({"items": [_mesure(r) for r in store.select(sparql)], "mode": f["mode"], "sparql": sparql.strip()})


@bp.get("/mesures/<mesure_id>")
def detail_mesure(mesure_id):
    if not _existe(mesure_id, "Mesure"):
        return _err("Mesure introuvable", 404)
    sparql = Q.lister_mesures(mesure=mesure_id)
    item = _mesure(store.select(sparql)[0])
    item["historique"] = [r["note"] for r in store.select(Q.historique(mesure_id))]
    return jsonify({"item": item, "sparql": sparql.strip()})


@bp.post("/mesures")
def creer_mesure():
    d = request.get_json(silent=True) or {}
    if erreurs := valider_mesure(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer_mesure(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/mesures/<mesure_id>")
def modifier_mesure(mesure_id):
    if not _existe(mesure_id, "Mesure"):
        return _err("Mesure introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": mesure_id}
    if erreurs := valider_mesure(d, creation=False):
        return _invalide(erreurs)
    # rattacher à un compteur une mesure qui concernait (assertion) un autre bâtiment la réaffecte via R5 :
    # jamais en silence, il faut le confirmer
    if d["type"] == "consommation" and d["compteur"] and not d["concerne"]:
        assertes = [r["b"] for r in store.select(Q.concerne_batiment_asserte(mesure_id))]
        autres = [b for b in assertes if b != d["cible"]]
        if autres and d.get("confirmerReaffectation") is not True:
            return _err(f"Cette mesure concerne sg:{', sg:'.join(autres)} (assertion). Avec ce compteur, R5 la ferait "
                        f"concerner sg:{d['cible']} : l'assertion serait retirée. Confirmez la réaffectation.", 409,
                        reaffectation={"de": autres, "vers": d["cible"]})
    sparql = Q.modifier_mesure(d)
    store.update(sparql)
    return jsonify({"id": mesure_id, "sparql": sparql.strip()})


@bp.delete("/mesures/<mesure_id>")
def supprimer_mesure(mesure_id):
    if not _existe(mesure_id, "Mesure"):
        return _err("Mesure introuvable", 404)
    externes = _references_externes(mesure_id, {"enregistre", "first"})
    if externes:
        return _err("D'autres individus font référence à cette mesure : suppression bloquée", 409,
                    dependances=externes, bloquant=True)
    store.forget_distinct(store.iri(mesure_id))
    sparql = Q.supprimer(mesure_id)
    store.update(sparql)
    return jsonify({"id": mesure_id, "sparql": sparql})


# --------------------------------------------------------------- opérateurs --

def _operateur(row):
    return {"id": row["o"], "label": row["label"] or row["o"],
            "gere": _split(row["gere"]), "lignesR4": _split(row["lignesR4"])}


@bp.get("/operateurs")
def lister_operateurs():
    sparql = Q.lister_operateurs(q=request.args.get("q", "").strip() or None,
                                 infrastructure=_id_arg("infrastructure"))
    return jsonify({"items": [_operateur(r) for r in store.select(sparql)], "sparql": sparql.strip()})


@bp.post("/operateurs")
def creer_operateur():
    d = request.get_json(silent=True) or {}
    if erreurs := valider_operateur(d, creation=True):
        return _invalide(erreurs)
    sparql = Q.creer_operateur(d)
    store.update(sparql)
    store.declare_distinct(store.iri(d["id"]))
    return jsonify({"id": d["id"], "sparql": sparql.strip()}), 201


@bp.put("/operateurs/<operateur_id>")
def modifier_operateur(operateur_id):
    if not _existe(operateur_id, "OperateurReseau"):
        return _err("Opérateur introuvable", 404)
    d = {**(request.get_json(silent=True) or {}), "id": operateur_id}
    if erreurs := valider_operateur(d, creation=False):
        return _invalide(erreurs)
    sparql = Q.modifier_operateur(d)
    store.update(sparql)
    return jsonify({"id": operateur_id, "sparql": sparql.strip()})


@bp.delete("/operateurs/<operateur_id>")
def supprimer_operateur(operateur_id):
    if not _existe(operateur_id, "OperateurReseau"):
        return _err("Opérateur introuvable", 404)
    externes = _references_externes(operateur_id, {"first"})
    if externes:
        return _err("D'autres individus font référence à cet opérateur : suppression bloquée", 409,
                    dependances=externes, bloquant=True)
    gere = store.select(Q.lister_operateurs())
    gere = next((_operateur(r)["gere"] for r in gere if r["o"] == operateur_id), [])
    if gere and request.args.get("force") != "true":
        return _err("Seules les relations gere de l'opérateur seront retirées : aucune infrastructure "
                    "n'est supprimée.", 409, dependances=[{"id": x, "relation": "gere"} for x in gere])
    store.forget_distinct(store.iri(operateur_id))
    sparql = Q.supprimer(operateur_id)
    store.update(sparql)
    return jsonify({"id": operateur_id, "sparql": sparql})


# ------------------------------------------------------- vue d'ensemble ----

@bp.get("/")
def statut():
    return jsonify({"module": "mesure", "membre": "Ibtihel Mechergui", "statut": "implémenté"})


@bp.get("/options")
def options():
    """Listes de choix pour les formulaires et les filtres."""
    out = {k: [] for k in ("batiments", "sources", "infrastructures", "compteurs", "operateurs")}
    seen = set()
    for r in store.select(Q.OPTIONS):
        key = (r["groupe"], r["id"])
        if key not in seen:
            seen.add(key)
            out[r["groupe"]].append({"id": r["id"], "label": r["label"] or r["id"], "classe": r["classe"]})
    return jsonify(out)


@bp.get("/stats")
def statistiques():
    c = store.select(Q.COMPTES)[0]
    return jsonify({k: int(c[k] or 0) for k in ("compteurs", "consommations", "productions", "operateurs")}
                   | {"sparql": Q.COMPTES.strip()})


@bp.get("/bilan")
def bilan():
    """Consommation et production sur une période : mesures entièrement incluses, jamais proratisées."""
    debut = parse_date(request.args.get("debut")) if request.args.get("debut") else None
    fin = parse_date(request.args.get("fin"), fin=True) if request.args.get("fin") else None
    if request.args.get("debut") and not debut or request.args.get("fin") and not fin:
        return _err("Date invalide (AAAA-MM-JJ)", 422)
    if debut and fin and fin < debut:
        return _err("La date de fin précède la date de début", 422)

    totaux = {t: {"nombre": 0, "totalKWh": 0.0} for t in ("consommation", "production")}
    for r in store.select(Q.bilan_types(debut, fin)):
        if r["type"] in totaux:
            totaux[r["type"]] = {"nombre": int(r["nombre"] or 0), "totalKWh": float(r["totalKWh"] or 0)}
    cibles = [{"type": r["type"], "cible": r["cible"], "via": r["via"], "nombre": int(r["nombre"] or 0),
               "totalKWh": float(r["totalKWh"] or 0)} for r in store.select(Q.bilan_cibles(debut, fin))]
    exclues = [{"id": r["m"], "type": r["type"], "debut": _iso(r["debut"]), "fin": _iso(r["fin"])}
               for r in store.select(Q.bilan_exclues(debut, fin))] if (debut or fin) else []
    chev = [{"m1": r["m1"], "m2": r["m2"], "cible": r["cible"]}
            for r in store.select(Q.chevauchements(debut, fin))]
    return jsonify({
        "debut": debut, "fin": fin,
        "regle": ("Seules les mesures dont la période [dateDebut, dateFin] est entièrement comprise "
                  "dans l'intervalle sont additionnées (aucune proratisation). Consommation et production "
                  "sont totalisées séparément."),
        "totaux": totaux, "parCible": cibles, "exclues": exclues, "chevauchements": chev,
        "sparql": Q.bilan_types(debut, fin).strip(),
    })


@bp.get("/coherence")
def coherence():
    """Contrôle des axiomes du module sur les données (assertions + R5)."""
    rows = store.select(Q.COHERENCE)
    return jsonify({"anomalies": [{"id": r["x"], "probleme": r["probleme"], "detail": r["detail"]} for r in rows],
                    "sparql": Q.COHERENCE.strip()})


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
