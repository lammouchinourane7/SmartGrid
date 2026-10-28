"""Contrôle de saisie du module Bâtiments.

Le validateur renvoie un dict {champ: message} (vide si tout est valide) et
normalise les données reçues. Chaque règle reprend un axiome de l'ontologie :
  - Batiment ⊑ estRaccordeA some LigneElectrique             → au moins une ligne
  - BatimentIndustriel ⊑ estRaccordeA some (LigneMoyenneTension ⊔ LigneHauteTension)
  - BatimentPublic ⊑ estAlimentePar min 2 SourceEnergie      → 2 sources (directes ou déduites R7/R6/R1)
  - Résidentiel / Industriel / Public / Commercial disjointes → un seul type
  - Batiment ⊑ consommationAnnuelle only float[≥ 0]
  - Batiment ⊑ surface only float[> 0] · nombreOccupants only integer[≥ 0]
  - Batiment ⊑ classeEnergetique only {"A", …, "G"}
  - consommationAnnuelle, surface, classeEnergetique… sont fonctionnelles → une seule valeur
"""
import re
from datetime import date

import store
from . import queries as Q

CONSO_MAX = 1_000_000_000   # kWh / an (1 TWh)
SURFACE_MAX = 5_000_000     # m²
PUISSANCE_MAX = 1_000_000   # kW
OCCUPANTS_MAX = 1_000_000
ANNEE_MIN = 1800


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


def _texte(d, champ):
    d[champ] = re.sub(r"\s+", " ", str(d.get(champ) or "")).strip()
    return d[champ]


def valider(d, creation):
    erreurs = {}

    # identité
    d["id"] = str(d.get("id") or "").strip()
    _texte(d, "label")
    if not store.valid_id(d["id"]):
        erreurs["id"] = "2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre"
    elif creation and store.ask(Q.ask_existe(d["id"])):
        erreurs["id"] = f"L'individu sg:{d['id']} existe déjà"
    if len(d["label"]) < 3:
        erreurs["label"] = "Au moins 3 caractères"
    elif len(d["label"]) > 120:
        erreurs["label"] = "120 caractères au maximum"
    elif store.ask(Q.ask_label_pris(d["label"], None if creation else d["id"])):
        erreurs["label"] = "Un autre bâtiment porte déjà ce libellé"

    # type : un seul usage (les 4 classes sont disjointes deux à deux)
    d["classe"] = str(d.get("classe") or "")
    if d["classe"] not in Q.TYPES:
        erreurs["classe"] = "Choisissez un type de bâtiment"

    if len(_texte(d, "adresse")) > 160:
        erreurs["adresse"] = "160 caractères au maximum"

    # valeurs numériques (plages de l'ontologie)
    _nombre(d, "consommation", erreurs, requis=True, mini=0, maxi=CONSO_MAX, unite=" kWh")
    _nombre(d, "surface", erreurs, requis=False, min_exclu=0, maxi=SURFACE_MAX, unite=" m²")
    _nombre(d, "occupants", erreurs, requis=False, mini=0, maxi=OCCUPANTS_MAX, entier=True)
    _nombre(d, "puissance", erreurs, requis=False, min_exclu=0, maxi=PUISSANCE_MAX, unite=" kW")
    _nombre(d, "annee", erreurs, requis=False, entier=True)
    if "annee" not in erreurs and d["annee"] is not None and not ANNEE_MIN <= d["annee"] <= date.today().year:
        erreurs["annee"] = f"Entre {ANNEE_MIN} et {date.today().year}"

    # classe énergétique : énumération {"A", …, "G"}
    d["dpe"] = str(d.get("dpe") or "").strip().upper() or None
    if d["dpe"] and d["dpe"] not in Q.CLASSES_ENERGETIQUES:
        erreurs["dpe"] = 'Une lettre de A à G (classeEnergetique only {"A", …, "G"})'

    # lignes : Batiment ⊑ estRaccordeA some LigneElectrique
    lignes = _liste(d, "lignes")
    if not lignes:
        erreurs["lignes"] = "Au moins une ligne (Batiment ⊑ estRaccordeA some LigneElectrique)"
    else:
        inconnue = next((l for l in lignes if not store.ask(Q.ask_type(l, "LigneElectrique"))), None)
        if inconnue:
            erreurs["lignes"] = f"sg:{inconnue} n'est pas une LigneElectrique"
        elif d["classe"] == "BatimentIndustriel":
            tensions = [r["tension"] for r in store.select(Q.tensions(lignes))]
            if not any(t is not None and t > Q.SEUIL_MT for t in tensions):
                erreurs["lignes"] = ("Un site industriel est raccordé en moyenne ou haute tension "
                                     "(BatimentIndustriel ⊑ estRaccordeA some (LigneMoyenneTension ⊔ LigneHauteTension))")

    # sources directes et stockages
    for s in _liste(d, "sources"):
        if not store.ask(Q.ask_type(s, "SourceEnergie")):
            erreurs["sources"] = f"sg:{s} n'est pas une SourceEnergie"
            break
    for x in _liste(d, "stockages"):
        if not store.ask(Q.ask_type(x, "SystemeStockage")):
            erreurs["stockages"] = f"sg:{x} n'est pas un SystemeStockage"
            break

    # BatimentPublic ⊑ estAlimentePar min 2 SourceEnergie (directes + déduites)
    if d["classe"] == "BatimentPublic" and not {"lignes", "sources", "stockages"} & erreurs.keys():
        toutes = set(d["sources"])
        sparql = Q.sources_deduites(None if creation else d["id"], lignes, d["stockages"])
        if sparql:
            toutes |= {r["s"] for r in store.select(sparql)}
        if len(toutes) < 2:
            erreurs["sources"] = (f"Un bâtiment public est alimenté par au moins 2 sources "
                                  f"(BatimentPublic ⊑ estAlimentePar min 2 SourceEnergie) : "
                                  f"{len(toutes)} trouvée(s), directes ou déduites par R7 / R6")
    return erreurs
