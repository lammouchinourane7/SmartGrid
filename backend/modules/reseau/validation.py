"""Contrôle de saisie du module Réseau.

Chaque validateur renvoie un dict {champ: message} (vide si tout est valide)
et normalise les données reçues (nombres, listes sans doublons, espaces).
Les règles reprennent les axiomes de l'ontologie quand il y en a un.
"""
import re
from datetime import date

import store
from . import queries as Q

TENSION_MAX = 1000      # kV : au-delà, aucune ligne réelle
LONGUEUR_MAX = 2000     # km
CAPACITE_MAX = 5000     # MVA
ANNEE_MIN = 1900
_VILLE_RE = re.compile(r"^[A-Za-zÀ-ÿ' -]{2,60}$")


def _nombre(d, champ, erreurs, *, requis, min_exclu=None, maxi=None, unite="", entier=False):
    raw = d.get(champ)
    if raw in (None, ""):
        d[champ] = None
        if requis:
            erreurs[champ] = "Champ obligatoire"
        return
    try:
        valeur = float(raw)
        if entier:
            if valeur != int(valeur):
                raise ValueError
            valeur = int(valeur)
    except (TypeError, ValueError):
        erreurs[champ] = "Doit être un nombre entier" if entier else "Doit être un nombre"
        return
    if min_exclu is not None and valeur <= min_exclu:
        erreurs[champ] = f"Doit être supérieur à {min_exclu}{unite}"
    elif maxi is not None and valeur > maxi:
        erreurs[champ] = f"Ne peut pas dépasser {maxi}{unite}"
    d[champ] = valeur


def _annee(d, erreurs):
    _nombre(d, "annee", erreurs, requis=False, entier=True)
    if "annee" not in erreurs and d["annee"] is not None:
        if not ANNEE_MIN <= d["annee"] <= date.today().year:
            erreurs["annee"] = f"Entre {ANNEE_MIN} et {date.today().year}"


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


def _liste(d, champ):
    d[champ] = [x for x in dict.fromkeys(d.get(champ) or []) if isinstance(x, str) and x]
    return d[champ]


def _types(ids, classe, champ, erreurs):
    for x in ids:
        if not store.ask(Q.ask_type(x, classe)):
            erreurs[champ] = f"sg:{x} n'est pas un {classe}"
            return


def valider_ligne(d, creation):
    erreurs = {}
    _identite(d, erreurs, "LigneElectrique", creation)
    _nombre(d, "tension", erreurs, requis=True, min_exclu=0, maxi=TENSION_MAX, unite=" kV")
    _nombre(d, "longueur", erreurs, requis=False, min_exclu=0, maxi=LONGUEUR_MAX, unite=" km")
    _annee(d, erreurs)

    postes = _liste(d, "postes")
    if not postes:
        erreurs["postes"] = "Au moins un poste (LigneElectrique ⊑ relie min 1 PosteElectrique)"
    elif "tension" not in erreurs and d["tension"] >= 63 and len(postes) < 2:
        erreurs["postes"] = "Une ligne haute tension relie au moins 2 postes (LigneHauteTension ⊑ relie min 2)"
    else:
        _types(postes, "PosteElectrique", "postes", erreurs)
    _types(_liste(d, "batiments"), "Batiment", "batiments", erreurs)
    return erreurs


def valider_poste(d, creation):
    erreurs = {}
    _identite(d, erreurs, "PosteElectrique", creation)
    d["ville"] = re.sub(r"\s+", " ", str(d.get("ville") or "")).strip()
    if d["ville"] and not _VILLE_RE.match(d["ville"]):
        erreurs["ville"] = "Lettres, espaces, apostrophes et tirets uniquement (2 à 60)"
    _nombre(d, "capacite", erreurs, requis=False, min_exclu=0, maxi=CAPACITE_MAX, unite=" MVA")
    _annee(d, erreurs)

    connexions = [p for p in _liste(d, "connexions") if p != d["id"]]
    d["connexions"] = connexions
    _types(connexions, "PosteElectrique", "connexions", erreurs)

    secours = _liste(d, "secours")
    if d["id"] in secours:
        erreurs["secours"] = "Un poste ne peut pas se secourir lui-même (secourt est irréflexive)"
    else:
        _types(secours, "PosteElectrique", "secours", erreurs)
        for p in secours:
            if "secours" not in erreurs and store.ask(Q.ask_secourt(p, d["id"])):
                erreurs["secours"] = f"sg:{p} secourt déjà ce poste (secourt est asymétrique)"

    _types(_liste(d, "gestionnaires"), "OperateurReseau", "gestionnaires", erreurs)
    return erreurs
