"""Contrôle de saisie du module Gestion et mesure.

Chaque validateur renvoie un dict {champ: message} (vide si tout est valide)
et normalise les données reçues (nombres, dates ISO, listes sans doublons).

Sous l'hypothèse du monde ouvert, HermiT ne signale pas un compteur sans bâtiment
ni une mesure sans valeur : ces contrôles applicatifs complètent les axiomes.
Le message indique l'axiome appliqué quand il y en a un, sinon « règle applicative ».
"""
import re
from datetime import datetime

import store
from . import queries as Q

VALEUR_MAX = 1e10            # kWh : 10 TWh, au-delà c'est une erreur de saisie
ANNEE_MIN, ANNEE_MAX = 2000, 2100
_IDENTIFIANT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _identite(d, erreurs, classe, creation):
    d["id"] = str(d.get("id") or "").strip()
    d["label"] = re.sub(r"\s+", " ", str(d.get("label") or "")).strip()
    if not store.valid_id(d["id"]):
        erreurs["id"] = "2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre"
    elif creation and store.ask(Q.ask_existe(d["id"])):
        erreurs["id"] = f"L'individu sg:{d['id']} existe déjà"
    if len(d["label"]) < 3:
        erreurs["label"] = "Au moins 3 caractères"
    elif len(d["label"]) > 120:
        erreurs["label"] = "120 caractères au maximum"
    elif store.ask(Q.ask_label_pris(d["label"], classe, None if creation else d["id"])):
        erreurs["label"] = "Un autre individu de cette classe porte déjà ce libellé"


def _reference(d, champ, classe, erreurs, requis, message_requis=None):
    """Un identifiant d'individu existant de la classe donnée (ou None)."""
    valeur = d.get(champ)
    valeur = valeur.strip() if isinstance(valeur, str) else None
    d[champ] = valeur or None
    if not d[champ]:
        if requis:
            erreurs[champ] = message_requis or "Champ obligatoire"
        return
    if not store.valid_id(d[champ]) or not store.ask(Q.ask_type(d[champ], classe)):
        erreurs[champ] = f"sg:{d[champ]} n'est pas un individu {classe}"


def parse_date(raw, fin=False):
    """'2025-01-31' ou '2025-01-31T12:00[:00]' → '2025-01-31T23:59:59' (ou None si invalide).

    Une date sans heure couvre la journée entière : 00:00:00 au début, 23:59:59 à la fin,
    comme les mesures de l'ontologie.
    """
    raw = str(raw or "").strip()
    if _DATE_RE.match(raw):
        raw += "T23:59:59" if fin else "T00:00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is not None or not ANNEE_MIN <= dt.year <= ANNEE_MAX:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def valider_compteur(d, creation):
    erreurs = {}
    _identite(d, erreurs, "CompteurIntelligent", creation)

    d["identifiant"] = str(d.get("identifiant") or "").strip()
    if not d["identifiant"]:
        erreurs["identifiant"] = "Champ obligatoire"
    elif not _IDENTIFIANT_RE.match(d["identifiant"]):
        erreurs["identifiant"] = "2 à 40 caractères : lettres, chiffres, - et _"
    elif store.ask(Q.compteur_identifiant_pris(d["identifiant"], None if creation else d["id"])):
        erreurs["identifiant"] = "Identifiant déjà attribué à un autre compteur (règle applicative)"

    if isinstance(d.get("batiment"), list):
        erreurs["batiment"] = "Un seul bâtiment (CompteurIntelligent ⊑ installeDans exactly 1 Batiment)"
    else:
        _reference(d, "batiment", "Batiment", erreurs, requis=True,
                   message_requis="Bâtiment obligatoire (installeDans exactly 1 Batiment)")
    return erreurs


def valider_mesure(d, creation):
    erreurs = {}
    _identite(d, erreurs, "Mesure", creation)

    if d.get("type") not in Q.TYPES:
        erreurs["type"] = "Choisir consommation ou production"

    raw = d.get("valeur")
    if raw in (None, ""):
        erreurs["valeur"] = "Champ obligatoire (valeurKWh)"
    else:
        try:
            d["valeur"] = float(raw)
            if d["valeur"] != d["valeur"] or d["valeur"] < 0:  # NaN ou négatif
                erreurs["valeur"] = "Doit être un nombre positif ou nul"
            elif d["valeur"] > VALEUR_MAX:
                erreurs["valeur"] = f"Ne peut pas dépasser {VALEUR_MAX:.0e} kWh"
        except (TypeError, ValueError):
            erreurs["valeur"] = "Doit être un nombre"

    for champ, est_fin in (("debut", False), ("fin", True)):
        if not d.get(champ):
            erreurs[champ] = "Champ obligatoire"
            continue
        d[champ] = parse_date(d[champ], fin=est_fin)
        if d[champ] is None:
            erreurs[champ] = f"Date invalide (AAAA-MM-JJ, années {ANNEE_MIN}–{ANNEE_MAX})"
    if "debut" not in erreurs and "fin" not in erreurs and d["fin"] <= d["debut"]:
        erreurs["fin"] = "La date de fin doit être postérieure à la date de début"

    _reference(d, "compteur", "CompteurIntelligent", erreurs, requis=False)
    d["concerne"] = None
    if d.get("type") == "production":
        _reference(d, "cible", "SourceEnergie", erreurs, requis=True,
                   message_requis="Source d'énergie obligatoire (MesureProduction ⊑ concerne only SourceEnergie)")
        d["concerne"] = d["cible"]
    elif d.get("type") == "consommation":
        _reference(d, "cible", "Batiment", erreurs, requis=not d["compteur"],
                   message_requis="Bâtiment obligatoire sans compteur (MesureConsommation ⊑ concerne only Batiment)")
        if d["compteur"] and "compteur" not in erreurs and "cible" not in erreurs:
            batiments = [r["b"] for r in store.select(Q.batiments_du_compteur(d["compteur"]))]
            if len(batiments) != 1:
                erreurs["compteur"] = (f"Ce compteur est installé dans {len(batiments)} bâtiment(s) : "
                                       "corrigez d'abord son installation (exactly 1 Batiment)")
            elif d["cible"] and d["cible"] != batiments[0]:
                erreurs["cible"] = (f"Le compteur est installé dans sg:{batiments[0]} : R5 en déduirait un second "
                                    "bâtiment (MesureConsommation ⊑ concerne max 1 Batiment)")
            else:
                d["cible"] = batiments[0]  # déduit par R5, non asserté
        elif not d["compteur"]:
            d["concerne"] = d["cible"]
    return erreurs


def valider_operateur(d, creation):
    erreurs = {}
    _identite(d, erreurs, "OperateurReseau", creation)
    gere = d.get("gere") or []
    if not isinstance(gere, list):
        gere = []
    d["gere"] = [x for x in dict.fromkeys(gere) if isinstance(x, str) and x]
    for x in d["gere"]:
        if not store.valid_id(x) or not store.ask(Q.ask_type(x, "InfrastructureReseau")):
            erreurs["gere"] = f"sg:{x} n'est pas une InfrastructureReseau (range de gere)"
            break
    return erreurs
