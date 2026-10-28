"""Contrôle de saisie du module Production.

Chaque validateur renvoie un dict {champ: message} (vide si tout est valide) et normalise
les données. Toute la validation a lieu AVANT l'écriture : une erreur laisse le graphe inchangé.

Axiomes appliqués (cités dans les messages) et règles applicatives :
  - un seul type de la hiérarchie par source ; Solaire ⊓ Eolien et Renouvelable ⊓ NonRenouvelable
    sont disjointes : un seul type précis élimine les combinaisons incompatibles ;
  - Eolien ⊑ injecteDans some LigneElectrique : sous l'hypothèse du monde ouvert, une éolienne
    sans ligne n'est pas incohérente pour HermiT ; l'application exige donc au moins une ligne
    (règle applicative qui matérialise la restriction existentielle) ;
  - puissanceInstallee fonctionnelle : une seule valeur, finie et ≥ 0 (règle applicative) ;
  - stockeEnergieDe only C (ex. STEP) : une source stockée par un tel stockage doit rester de type C.
"""
import math
import re
from datetime import date, datetime

import store
from . import queries as Q

PUISSANCE_MAX = 10_000_000   # kW (10 GW) : au-delà, erreur de saisie
ANNEE_MIN = 1900
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_date(raw):
    """'2019-05-10' ou '2019-05-10T00:00:00' → '2019-05-10T00:00:00' (format de l'ontologie), sinon None."""
    raw = str(raw or "").strip()
    if _DATE_RE.match(raw):
        raw += "T00:00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is not None or dt.year < ANNEE_MIN:
        return None
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def _liste(d, champ):
    valeurs = d.get(champ) or []
    if not isinstance(valeurs, list):
        valeurs = []
    d[champ] = [x for x in dict.fromkeys(valeurs) if isinstance(x, str) and x]
    return d[champ]


def _references(ids, classe, champ, erreurs):
    for x in ids:
        if not store.valid_id(x) or not store.ask(Q.ask_type(x, classe)):
            erreurs[champ] = f"sg:{x} n'est pas un individu {classe}"
            return


def valider(d, creation):
    erreurs = {}
    d["id"] = str(d.get("id") or "").strip()
    d["label"] = re.sub(r"\s+", " ", str(d.get("label") or "")).strip()
    if not store.valid_id(d["id"]):
        erreurs["id"] = "2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre"
    elif creation and store.ask(Q.ask_existe(d["id"])):
        erreurs["id"] = f"L'URI sg:{d['id']} est déjà utilisée"
    if len(d["label"]) < 3:
        erreurs["label"] = "Au moins 3 caractères"
    elif len(d["label"]) > 120:
        erreurs["label"] = "120 caractères au maximum"
    elif store.valid_id(d["id"]) and store.ask(Q.ask_label_pris(d["label"], None if creation else d["id"])):
        erreurs["label"] = "Une autre source porte déjà ce libellé (convention du projet)"

    if d.get("type") not in Q.TYPES:
        erreurs["type"] = f"Type attendu parmi : {', '.join(Q.TYPES)}"

    raw = d.get("puissance")
    if raw in (None, ""):
        d["puissance"] = None  # non renseignée : jamais remplacée par 0
    else:
        try:
            valeur = float(raw)
            if isinstance(raw, bool) or not math.isfinite(valeur):
                raise ValueError
            d["puissance"] = valeur
            if valeur < 0:
                erreurs["puissance"] = "La puissance installée ne peut pas être négative"
            elif valeur > PUISSANCE_MAX:
                erreurs["puissance"] = f"Ne peut pas dépasser {PUISSANCE_MAX:,} kW".replace(",", " ")
        except (TypeError, ValueError):
            erreurs["puissance"] = "Doit être un nombre fini (kW)"

    if d.get("date") in (None, ""):
        d["date"] = None
    else:
        d["date"] = parse_date(d["date"])
        if d["date"] is None:
            erreurs["date"] = f"Date invalide (AAAA-MM-JJ, à partir de {ANNEE_MIN})"
        elif d["date"][:10] > date.today().isoformat():
            erreurs["date"] = "Une date de mise en service ne peut pas être dans le futur"

    lignes = _liste(d, "lignes")
    _references(lignes, "LigneElectrique", "lignes", erreurs)
    _references(_liste(d, "batiments"), "Batiment", "batiments", erreurs)
    if d.get("type") == "Eolien" and not lignes and "lignes" not in erreurs:
        erreurs["lignes"] = "Une source éolienne injecte dans au moins une ligne (Eolien ⊑ injecteDans some LigneElectrique)"

    if not creation and d.get("type") in Q.TYPES and store.valid_id(d["id"]):
        for r in store.select(Q.stockages_contraignants(d["id"])):
            if not store.ask(Q.ask_sous_classe(d["type"], r["c"])):
                erreurs["type"] = (f"sg:{r['x']} ({r['classeStockage']}) stocke cette source et impose "
                                   f"stockeEnergieDe only {r['c']} : le type doit rester un {r['c']}")
                break
    return erreurs
