"""Contrôle de saisie du module Stockage.

Le validateur renvoie un dict {champ: message} (vide si tout est valide) et
normalise les données reçues. Chaque règle reprend un axiome de l'ontologie :
  - SystemeStockage ⊑ stockeEnergieDe some SourceEnergie     → au moins une source
  - STEP ⊑ stockeEnergieDe only SourceRenouvelable           → sources toutes renouvelables
  - StockageHydrogene ⊑ stockeEnergieDe some SourceRenouvelable
  - VolantInertie ⊑ raccordeAuPoste exactly 1 PosteElectrique
  - SystemeStockage ⊑ niveauCharge only float[≥ 0, ≤ 100]
  - SystemeStockage ⊑ rendement only float[> 0, ≤ 100]
  - capaciteStockage, niveauCharge, rendement… sont fonctionnelles → une seule valeur
"""
import re
from datetime import date

import store
from . import queries as Q

CAPACITE_MAX = 10_000_000   # kWh (10 GWh)
PUISSANCE_MAX = 2_000_000   # kW
ANNEE_MIN = 1900


def _nombre(d, champ, erreurs, *, requis, mini=None, min_exclu=None, maxi=None, unite="", entier=False):
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
    elif mini is not None and valeur < mini:
        erreurs[champ] = f"Doit être au moins {mini}{unite}"
    elif maxi is not None and valeur > maxi:
        erreurs[champ] = f"Ne peut pas dépasser {maxi:,}{unite}".replace(",", " ")
    d[champ] = valeur


def _liste(d, champ):
    d[champ] = [x for x in dict.fromkeys(d.get(champ) or []) if isinstance(x, str) and x]
    return d[champ]


def valider(d, creation):
    erreurs = {}

    # identité
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
    elif store.ask(Q.ask_label_pris(d["label"], None if creation else d["id"])):
        erreurs["label"] = "Un autre système de stockage porte déjà ce libellé"

    # classe : une seule classe concrète (les familles sont disjointes deux à deux)
    d["classe"] = str(d.get("classe") or "")
    if d["classe"] not in Q.CLASSES:
        erreurs["classe"] = "Choisissez un type de stockage"

    # valeurs numériques (plages de l'ontologie)
    _nombre(d, "capacite", erreurs, requis=True, min_exclu=0, maxi=CAPACITE_MAX, unite=" kWh")
    _nombre(d, "niveau", erreurs, requis=False, mini=0, maxi=100, unite=" %")
    _nombre(d, "rendement", erreurs, requis=False, min_exclu=0, maxi=100, unite=" %")
    _nombre(d, "puissance", erreurs, requis=False, min_exclu=0, maxi=PUISSANCE_MAX, unite=" kW")
    _nombre(d, "annee", erreurs, requis=False, entier=True)
    if "annee" not in erreurs and d["annee"] is not None and not ANNEE_MIN <= d["annee"] <= date.today().year:
        erreurs["annee"] = f"Entre {ANNEE_MIN} et {date.today().year}"

    d["technologie"] = re.sub(r"\s+", " ", str(d.get("technologie") or "")).strip()
    if len(d["technologie"]) > 80:
        erreurs["technologie"] = "80 caractères au maximum"

    # poste (raccordeAuPoste est fonctionnelle : 0 ou 1 poste)
    d["poste"] = str(d.get("poste") or "").strip() or None
    if d["poste"] and not store.ask(Q.ask_type(d["poste"], "PosteElectrique")):
        erreurs["poste"] = f"sg:{d['poste']} n'est pas un PosteElectrique"
    elif d["classe"] == "VolantInertie" and not d["poste"]:
        erreurs["poste"] = "Un volant d'inertie est raccordé à exactement 1 poste (exactly 1)"

    # sources stockées
    sources = _liste(d, "sources")
    if not sources:
        erreurs["sources"] = "Au moins une source (SystemeStockage ⊑ stockeEnergieDe some SourceEnergie)"
    else:
        for s in sources:
            if not store.ask(Q.ask_type(s, "SourceEnergie")):
                erreurs["sources"] = f"sg:{s} n'est pas une SourceEnergie"
                break
        else:
            renouv = [s for s in sources if store.ask(Q.ask_type(s, "SourceRenouvelable"))]
            if d["classe"] == "STEP" and len(renouv) < len(sources):
                fossiles = ", ".join(s for s in sources if s not in renouv)
                erreurs["sources"] = (f"Une STEP ne stocke que du renouvelable "
                                      f"(STEP ⊑ stockeEnergieDe only SourceRenouvelable) : retirez {fossiles}")
            elif d["classe"] == "StockageHydrogene" and not renouv:
                erreurs["sources"] = ("L'hydrogène vert exige au moins une source renouvelable "
                                      "(StockageHydrogene ⊑ stockeEnergieDe some SourceRenouvelable)")

    # bâtiments alimentés
    for b in _liste(d, "batiments"):
        if not store.ask(Q.ask_type(b, "Batiment")):
            erreurs["batiments"] = f"sg:{b} n'est pas un Batiment"
            break
    return erreurs
