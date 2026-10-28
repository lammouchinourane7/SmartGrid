"""Module NLP → SPARQL de la Gestion et mesure (Membre 5 · Ibtihel Mechergui).

Traduit une question en français en requête SPARQL, sans API de LLM.
Outils : spaCy 3 + modèle fr_core_news_sm (tokenisation, lemmatisation,
étiquettes morpho-syntaxiques, entités nommées), PhraseMatcher de spaCy pour
relier les mots aux individus de l'ontologie et Matcher de spaCy (motifs de
tokens) pour les dates, les périodes et les quantités d'énergie.

Étapes :
  1. normalisation (minuscules, accents, ponctuation de liaison) puis analyse spaCy
     (tokens, lemmes, POS, NER) ;
  2. liaison d'entités : PhraseMatcher construit à partir des rdfs:label, des
     identifiants d'individus et des sg:identifiant des compteurs ; un nom qui désigne
     plusieurs individus déclenche une demande de précision (jamais d'URI inventée) ;
  3. Matcher : dates (« 1 janvier 2026 », « janvier 2026 », « 31/03/2026 »,
     « 2026-03-31 », « 1er trimestre 2025 », « en 2025 »), quantités (« 100 kWh »,
     « 2,5 MWh ») et comparateurs (« supérieures à », « au moins », « entre … et … ») ;
  4. intention (lister, compter, somme, moyenne, max, min, existe) et classe cible
     (compteurs, mesures, opérateurs, infrastructures) à partir des lemmes ;
  5. requête SPARQL construite par patrons contrôlés (R5 et R4 réécrites), exécutée
     ensuite par RDFLib. Lecture seule : les écritures passent par l'interface CRUD.
"""
import calendar
import re
import unicodedata
from datetime import datetime, timedelta

import spacy
from spacy.matcher import Matcher, PhraseMatcher
from spacy.util import filter_spans

import store
from . import queries as Q

# ------------------------------------------------------------ vocabulaire --

MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
ORDINAUX = {"1": 1, "1er": 1, "premier": 1, "2": 2, "2e": 2, "2eme": 2, "deuxieme": 2, "second": 2,
            "3": 3, "3e": 3, "3eme": 3, "troisieme": 3, "4": 4, "4e": 4, "4eme": 4, "quatrieme": 4}
UNITES = {"wh": 0.001, "kwh": 1, "mwh": 1000, "gwh": 1_000_000}

# formes normalisées (lemme spaCy ou forme de surface) → classe cible
CIBLES = {
    "compteur": {"compteur", "compteurs", "meter", "meters"},
    "mesure": {"mesure", "mesures", "releve", "releves", "relever", "lecture", "lectures", "enregistrement",
               "enregistrements", "donnee", "donnees"},
    "consommation": {"consommation", "consommations", "conso", "consos", "consommer", "consomme", "consommee",
                     "consommees", "consommes"},
    "production": {"production", "productions", "prod", "produire", "produit", "produite", "produites", "produits"},
    "operateur": {"operateur", "operateurs", "gestionnaire", "gestionnaires", "exploitant", "exploitants"},
    "infrastructure": {"infrastructure", "infrastructures", "poste", "postes", "ligne", "lignes",
                       "equipement", "equipements", "ouvrage", "ouvrages"},
}
ECRITURE = {"supprimer", "supprime", "supprimez", "effacer", "efface", "ajouter", "ajoute", "ajoutez",
            "creer", "cree", "creez", "modifier", "modifie", "modifiez", "inserer", "insere", "changer",
            "change", "remplacer", "renommer"}
SUPERLATIFS = {"grand": "max", "grande": "max", "elevee": "max", "eleve": "max", "fort": "max", "forte": "max",
               "important": "max", "importante": "max", "gros": "max", "grosse": "max",
               "faible": "min", "petit": "min", "petite": "min", "bas": "min", "basse": "min"}
COMPARATEURS = [  # (expression avant la quantité, opérateur SPARQL) : la plus longue d'abord
    ("superieur ou egal", ">="), ("superieure ou egale", ">="), ("superieures ou egales", ">="),
    ("inferieur ou egal", "<="), ("inferieure ou egale", "<="), ("inferieures ou egales", "<="),
    ("au moins", ">="), ("minimum", ">="), ("a partir de", ">="),
    ("au plus", "<="), ("maximum", "<="), ("jusqu a", "<="),
    ("au dessus de", ">"), ("en dessous de", "<"),
    ("plus de", ">"), ("plus que", ">"), ("moins de", "<"), ("moins que", "<"),
    ("superieur", ">"), ("superieure", ">"), ("superieurs", ">"), ("superieures", ">"),
    ("depasse", ">"), ("depassent", ">"), ("depassant", ">"), ("excede", ">"),
    ("inferieur", "<"), ("inferieure", "<"), ("inferieurs", "<"), ("inferieures", "<"),
    (">=", ">="), ("<=", "<="), (">", ">"), ("<", "<"),
]
SYMBOLES = {">": ">", ">=": "≥", "<": "<", "<=": "≤", "=": "="}

# types d'entités utiles pour chaque cible (sert aussi à lever une ambiguïté)
TYPES_UTILES = {
    "compteur": {"compteur", "batiment", "mesure"},
    "mesure": {"compteur", "batiment", "source", "mesure"},
    "operateur": {"operateur", "poste", "ligne"},
    "infrastructure": {"operateur", "poste", "ligne"},
}


def normaliser(texte):
    """minuscules, sans accents, ponctuation de liaison → espace (même longueur que l'entrée)."""
    sans_accents = "".join(unicodedata.normalize("NFD", c)[0] for c in texte.lower())
    return re.sub(r"[-–—_'’]", " ", sans_accents)


# ------------------------------------------------------------ pipeline spaCy --

_nlp = None
_matcher = None
_matcher_version = None
_individus = {}  # id → (type, label)
_motifs = None


def nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("fr_core_news_sm")
        except OSError:  # modèle absent : tokeniseur seul (python -m spacy download fr_core_news_sm)
            _nlp = spacy.blank("fr")
    return _nlp


def motifs():
    """Matcher spaCy : dates, trimestres, années et quantités d'énergie (sur le texte normalisé)."""
    global _motifs
    if _motifs is None:
        m = Matcher(nlp().vocab)
        mois = {"LOWER": {"IN": list(MOIS)}}
        annee = {"TEXT": {"REGEX": r"^(20\d\d|2100)$"}}
        m.add("JOUR", [[{"TEXT": {"REGEX": r"^(\d{1,2}|1er)$"}}, mois, {**annee, "OP": "?"}]])
        m.add("MOIS", [[mois, {**annee, "OP": "?"}]])
        m.add("JJMMAAAA", [[{"TEXT": {"REGEX": r"^\d{1,2}/\d{1,2}/\d{4}$"}}]])
        m.add("ISO", [[annee, {"SHAPE": "dd"}, {"SHAPE": "dd"}]])
        m.add("TRIMESTRE", [[{"LOWER": {"IN": list(ORDINAUX)}}, {"LOWER": "trimestre"}, {**annee, "OP": "?"}],
                            [{"LOWER": {"REGEX": r"^t[1-4]$"}}, {**annee, "OP": "?"}]])
        m.add("ANNEE", [[{"LOWER": {"IN": ["en", "annee", "an", "depuis", "apres", "avant"]}}, annee]])
        m.add("QUANTITE", [[{"LIKE_NUM": True}, {"LOWER": {"IN": list(UNITES)}}],
                           [{"LOWER": {"REGEX": r"^\d+([.,]\d+)?[kmg]?wh$"}}]])
        _motifs = m
    return _motifs


INDIVIDUS = """
SELECT ?x ?type ?label ?identifiant ?ville WHERE {
  { ?x a sg:CompteurIntelligent . BIND("compteur" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:Mesure . BIND("mesure" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:Batiment . BIND("batiment" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:SourceEnergie . BIND("source" AS ?type) }
  UNION { ?x a sg:PosteElectrique . BIND("poste" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:LigneElectrique . BIND("ligne" AS ?type) }
  UNION { ?x a sg:OperateurReseau . BIND("operateur" AS ?type) }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  OPTIONAL { ?x sg:identifiant ?identifiant }
  OPTIONAL { ?x sg:ville ?ville }
}"""


def _alias(type_, ident, label, identifiant, ville):
    """(nom exact, noms de lieu) : un nom exact l'emporte toujours sur un nom de lieu."""
    exacts = {ident, ident.replace("_", " ")}
    if label:
        exacts.add(label)
    if identifiant:
        exacts.add(identifiant)
    lieux = set()
    if type_ == "poste":
        lieu = ville or ident.removeprefix("Poste_").replace("_", " ")
        exacts |= {f"poste {lieu}", f"poste de {lieu}", f"poste d {lieu}", f"poste du {lieu}"}
        lieux.add(lieu)
    if type_ in ("batiment", "source") and "_" in ident:
        lieux.add(ident.rsplit("_", 1)[-1])  # Usine_Sfax → « Sfax »
    norm = lambda noms: {normaliser(n).strip() for n in noms if n and len(n) > 2}  # noqa: E731
    exacts = norm(exacts)
    return exacts, norm(lieux) - exacts


def _matcher_a_jour():
    """(Re)construit le PhraseMatcher quand le graphe a changé (CRUD)."""
    global _matcher, _matcher_version, _individus
    version = len(store.graph)
    if _matcher is not None and version == _matcher_version:
        return _matcher
    _matcher = PhraseMatcher(nlp().vocab, attr="LOWER")
    _individus = {}
    for r in store.select(INDIVIDUS):
        if r["x"] in _individus:  # un individu ne garde que son premier type
            continue
        _individus[r["x"]] = (r["type"], r["label"] or r["x"])
        exacts, lieux = _alias(r["type"], r["x"], r["label"], r["identifiant"], r["ville"])
        _matcher.add(f"exact|{r['type']}|{r['x']}", [nlp().make_doc(a) for a in exacts])
        if lieux:
            _matcher.add(f"lieu|{r['type']}|{r['x']}", [nlp().make_doc(a) for a in lieux])
    _matcher_version = version
    return _matcher


# ---------------------------------------------------------------- analyse --

def _entites(ndoc):
    """Spans de l'ontologie ; chaque span garde tous ses candidats (pour l'ambiguïté)."""
    candidats = {}
    for match_id, start, end in _matcher_a_jour()(ndoc):
        force, type_, ident = nlp().vocab.strings[match_id].split("|", 2)
        candidats.setdefault((start, end), {})[ident] = (force, type_)
    spans = filter_spans([ndoc[s:e] for s, e in candidats])  # le plus long gagne
    out = []
    for span in spans:
        c = candidats[(span.start, span.end)]
        exacts = {i: t for i, (f, t) in c.items() if f == "exact"}
        garder = exacts or {i: t for i, (f, t) in c.items()}
        out.append({"texte": span.text, "debut": span.start_char, "fin": span.end_char,
                    "candidats": [{"id": i, "type": t, "label": _individus[i][1]} for i, t in garder.items()]})
    return out


def _dans(idx, plages):
    return any(a <= idx < b for a, b in plages)


def _date_span(label, toks, annee_defaut=None):
    """Span du Matcher → (début, fin, année_manquante) en datetime, ou None si invalide."""
    textes = [t.text for t in toks]
    annee = next((int(x) for x in textes if re.fullmatch(r"20\d\d|2100", x)), None)
    try:
        if label == "JJMMAAAA":
            j, m, a = (int(x) for x in textes[0].split("/"))
            d = datetime(a, m, j)
            return d, d.replace(hour=23, minute=59, second=59), False
        if label == "ISO":
            d = datetime(int(textes[0]), int(textes[1]), int(textes[2]))
            return d, d.replace(hour=23, minute=59, second=59), False
        if label == "ANNEE":
            return datetime(annee, 1, 1), datetime(annee, 12, 31, 23, 59, 59), False
        manque = annee is None
        annee = annee or annee_defaut or 2000
        if label == "JOUR":
            jour = 1 if textes[0] == "1er" else int(textes[0])
            d = datetime(annee, MOIS[textes[1]], jour)
            return d, d.replace(hour=23, minute=59, second=59), manque
        if label == "MOIS":
            m = MOIS[textes[0]]
            dernier = calendar.monthrange(annee, m)[1]
            return datetime(annee, m, 1), datetime(annee, m, dernier, 23, 59, 59), manque
        if label == "TRIMESTRE":
            q = ORDINAUX.get(textes[0]) or int(textes[0][1])
            m1, m3 = 3 * q - 2, 3 * q
            return (datetime(annee, m1, 1),
                    datetime(annee, m3, calendar.monthrange(annee, m3)[1], 23, 59, 59), manque)
    except (ValueError, KeyError, IndexError):
        return None
    return None


def _periode(ndoc, spans):
    """Combine les dates trouvées en un intervalle [début, fin] ; signale une année manquante."""
    dates = [(s, lab) for s, lab in spans if lab not in ("QUANTITE",)]
    if not dates:
        return None, None
    annees = [int(t.text) for s, _ in dates for t in s if re.fullmatch(r"20\d\d|2100", t.text)]
    defaut = annees[-1] if annees else None
    valeurs = []
    for s, lab in dates:
        v = _date_span(lab, list(s), defaut)
        if v is None:
            return None, f"Date invalide : « {s.text} »"
        valeurs.append((s, v))
    if any(v[2] for _, v in valeurs) and defaut is None:
        return None, (f"Précisez l'année pour « {valeurs[0][0].text} » (ex. « janvier 2026 »).")

    premier, dernier = valeurs[0], valeurs[-1]
    # mots qui précèdent la première date (son premier token inclus : « depuis 2025 »)
    avant = " ".join(t.text for t in ndoc[max(0, premier[0].start - 3):premier[0].start + 1])
    convention = ("année reprise de l'autre date de la question"
                  if any(v[2] for _, v in valeurs) else None)
    if len(valeurs) >= 2:
        debut, fin = premier[1][0], dernier[1][1]
    elif re.search(r"\b(depuis|apres|partir|des)\b", avant):
        debut, fin = premier[1][0], None
    elif re.search(r"\b(avant)\b", avant):
        debut, fin = None, premier[1][0] - timedelta(seconds=1)
    elif re.search(r"\b(jusqu)\b", avant):
        debut, fin = None, premier[1][1]
    else:
        debut, fin = premier[1][0], premier[1][1]
    if debut and fin and fin < debut:
        return None, "La date de fin précède la date de début."
    fmt = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") if d else None  # noqa: E731
    return {"debut": fmt(debut), "fin": fmt(fin), "convention": convention}, None


def _nombre(texte):
    try:
        return float(texte.replace(",", "."))
    except ValueError:
        return None


def _comparaisons(ndoc, spans, exclus):
    """Quantités d'énergie (en kWh) et comparateurs : « supérieures à 100 kWh », « entre 100 et 500 kWh »."""
    quantites = []
    for s, lab in spans:
        if lab != "QUANTITE":
            continue
        if len(s) == 2:
            v, unite = _nombre(s[0].text), s[1].lower_
        else:
            m = re.fullmatch(r"(\d+(?:[.,]\d+)?)([kmg]?wh)", s[0].lower_)
            v, unite = _nombre(m.group(1)), m.group(2)
        quantites.append({"start": s.start, "valeur": v * UNITES[unite], "unite": unite})
    pris = {i for s, _ in spans for i in range(s.start, s.end)}
    for t in ndoc:  # nombre sans unité après un comparateur : kWh par convention
        if t.i in pris or _dans(t.idx, exclus) or not t.like_num or _nombre(t.text) is None:
            continue
        avant = " ".join(x.text for x in ndoc[max(0, t.i - 4):t.i])
        if any(re.search(rf"(^|\s){re.escape(e)}$", avant) for e, _ in COMPARATEURS) or avant.endswith("entre"):
            quantites.append({"start": t.i, "valeur": _nombre(t.text), "unite": None})
    quantites.sort(key=lambda q: q["start"])

    out = []
    i = 0
    while i < len(quantites):
        q = quantites[i]
        avant = " ".join(x.text for x in ndoc[max(0, q["start"] - 4):q["start"]])
        if re.search(r"(^|\s)entre$", avant) and i + 1 < len(quantites):
            out.append({"op": "entre", "min": q["valeur"], "max": quantites[i + 1]["valeur"]})
            i += 2
            continue
        op = next((s for e, s in COMPARATEURS if re.search(rf"(^|\s){re.escape(e)}(\s+a|\s+de)?$", avant)), "=")
        out.append({"op": op, "valeur": q["valeur"], "uniteSupposee": q["unite"] is None})
        i += 1
    return out


def analyser(question):
    texte = unicodedata.normalize("NFC", re.sub(r"\s+", " ", question)).strip()
    doc = nlp()(texte)                 # pipeline complet : lemmes, POS, NER
    norm = normaliser(texte)
    ndoc = nlp().make_doc(norm)        # tokens normalisés pour PhraseMatcher / Matcher
    entites = _entites(ndoc)
    plages = [(e["debut"], e["fin"]) for e in entites]

    spans = [(ndoc[s:e], nlp().vocab.strings[mid]) for mid, s, e in motifs()(ndoc)]
    gardes = {(sp.start, sp.end) for sp in filter_spans([sp for sp, _ in spans])}
    spans = sorted({(sp.start, sp.end): (sp, lab) for sp, lab in spans
                    if (sp.start, sp.end) in gardes and not _dans(sp.start_char, plages)}.values(),
                   key=lambda x: x[0].start)
    plages_dates = plages + [(sp.start_char, sp.end_char) for sp, lab in spans]

    reste = [t for t in doc if not _dans(t.idx, plages)]
    formes = [(normaliser(t.lemma_ or t.text).strip(), normaliser(t.text).strip()) for t in reste]
    mots = [f for _, f in formes]
    texte_reste = " ".join(mots)
    contient = lambda vocab: any(l in vocab or f in vocab for l, f in formes)  # noqa: E731

    # identifiants inconnus : forme d'identifiant d'individu mais aucune entité reconnue
    inconnus = [t.text for t in reste if re.fullmatch(r"[A-Za-z]+_[A-Za-z0-9_]+|[A-Z][a-z]+\d+|CPT-\d+", t.text)]

    # classe cible : premier mot (hors entités) qui désigne une classe du module
    cible, type_mesure = None, None
    for l, f in formes:
        for nom, vocab in CIBLES.items():
            if (l in vocab or f in vocab) and cible is None:
                cible = "mesure" if nom in ("consommation", "production") else nom
    if contient(CIBLES["consommation"]):
        type_mesure = "consommation"
    elif contient(CIBLES["production"]):
        type_mesure = "production"
    if cible is None and "qui" in mots and any(f.startswith("ger") for _, f in formes):
        cible = "operateur"

    if cible is None:
        types = {c["type"] for e in entites for c in e["candidats"]} if entites else set()
        if "operateur" in types:
            cible = "infrastructure"
        elif types & {"poste", "ligne"}:
            cible = "operateur"
        elif "compteur" in types and any(f in ("installe", "installes", "ou") for f in mots):
            cible = "compteur"
        elif types & {"compteur", "batiment", "source", "mesure"}:
            cible = "mesure"
    if cible == "compteur" and type_mesure and not any(f.startswith("install") for f in mots):
        cible = "mesure"  # « consommation enregistrée par les compteurs … »

    # ambiguïtés : on garde les candidats compatibles avec la cible avant de demander
    ambigues = []
    for e in entites:
        utiles = [c for c in e["candidats"] if cible is None or c["type"] in TYPES_UTILES.get(cible, set())]
        if len(utiles) == 1 or (len(e["candidats"]) == 1 and not utiles):
            e.update(utiles[0] if utiles else e["candidats"][0])
        else:
            ambigues.append(e)

    # intention
    intention = "lister"
    if contient(ECRITURE):
        intention = "ecriture"
    elif "combien" in mots or "nombre" in mots:
        intention = "compter"
    elif re.search(r"\b(total|totale|totaux|totales|somme|cumul|cumule|cumulee|bilan)\b", texte_reste):
        intention = "somme"
    elif re.search(r"\b(moyenne|moyen|moyennes)\b", texte_reste):
        intention = "moyenne"
    elif re.search(r"^(est ce qu|existe|y a t il)|existe t il", texte_reste):
        intention = "existe"
    else:
        for i, m in enumerate(mots[:-1]):
            if m in ("plus", "moins") and mots[i + 1] in SUPERLATIFS:
                sens = SUPERLATIFS[mots[i + 1]]
                intention = sens if m == "plus" else ("min" if sens == "max" else "max")
                break
        if re.search(r"\b(maximale|maximal|max)\b", texte_reste):
            intention = "max"
        elif re.search(r"\b(minimale|minimal|min)\b", texte_reste):
            intention = "min"
    if (intention == "lister" and cible == "mesure" and type_mesure and "mesure" not in mots
            and "mesures" not in mots and re.search(r"\bquel(le)?s? (est|sont|etait)\b", texte_reste)):
        intention = "somme"  # « Quelle est la consommation de Maison1 en janvier 2025 ? »

    periode, erreur_date = _periode(ndoc, spans)
    comparaisons = _comparaisons(ndoc, spans, plages_dates)

    type_infra = None
    if cible == "infrastructure":
        if any(f in ("poste", "postes") for f in mots):
            type_infra = "poste"
        elif any(f in ("ligne", "lignes") for f in mots):
            type_infra = "ligne"

    return {
        "question": texte,
        "tokens": [{"texte": t.text, "lemme": t.lemma_ or t.text, "pos": t.pos_} for t in doc],
        "ner": [{"texte": e.text, "label": e.label_} for e in doc.ents],
        "entites": [e for e in entites if "id" in e],
        "ambigues": ambigues,
        "inconnus": inconnus,
        "intention": intention,
        "cible": cible,
        "typeMesure": type_mesure,
        "typeInfrastructure": type_infra,
        "comparaisons": comparaisons,
        "periode": periode,
        "erreurDate": erreur_date,
    }


# ------------------------------------------------------- génération SPARQL --

def _type_bind(var):
    return Q.TYPE_BIND.replace("?m ", f"{var} ")


def _filtre_valeur(c, var="?valeurKWh"):
    if c["op"] == "entre":
        return f"FILTER({var} >= {float(c['min'])} && {var} <= {float(c['max'])})"
    return f"FILTER({var} {c['op']} {float(c['valeur'])})"


def _corps_mesures(a, avec_periode=True):
    """Motifs SPARQL des mesures ; la période est en chevauchement pour une liste,
    en inclusion pour un agrégat (on n'additionne que des mesures entièrement dans la période)."""
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    motifs_ = ["?mesure a/rdfs:subClassOf* sg:Mesure .",
               "OPTIONAL { ?mesure rdfs:label ?label }",
               "OPTIONAL { ?mesure sg:valeurKWh ?valeurKWh }",
               "OPTIONAL { ?mesure sg:dateDebut ?dateDebut }",
               "OPTIONAL { ?mesure sg:dateFin ?dateFin }",
               _type_bind("?mesure"),
               "OPTIONAL { ?compteur sg:enregistre ?mesure }",
               "# cible : concerne asserté, ou bâtiment déduit par R5\n"
               f"  OPTIONAL {{ {Q.cible('?mesure', '?cible', via='?via')} }}"]
    if a["typeMesure"]:
        motifs_.append(f"?mesure a sg:{Q.TYPES[a['typeMesure']]} .")
    for e in a["entites"]:
        if e["type"] == "compteur":
            motifs_.append(f"FILTER(?compteur = {sg(e['id'])})")
        elif e["type"] in ("batiment", "source"):
            motifs_.append(f"FILTER(?cible = {sg(e['id'])})")
        elif e["type"] == "mesure":
            motifs_.append(f"FILTER(?mesure = {sg(e['id'])})")
    for c in a["comparaisons"]:
        motifs_.append(_filtre_valeur(c))
    if avec_periode and a["periode"]:
        mode = "inclusion" if a["intention"] in ("somme", "moyenne") else "chevauchement"
        motifs_ += Q._periode(a["periode"]["debut"], a["periode"]["fin"], mode, "?dateDebut", "?dateFin")
    return "\n  ".join(motifs_)


def generer(a, avec_periode=True):
    """Construit la requête SPARQL à partir de l'analyse. Renvoie (sparql, est_ask)."""
    cible, intention = a["cible"], a["intention"]
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    par_type = lambda *t: [e for e in a["entites"] if e["type"] in t]  # noqa: E731

    if cible == "mesure":
        corps = _corps_mesures(a, avec_periode)
        if intention == "existe":
            return f"ASK {{\n  {corps}\n}}", True
        if intention == "compter":
            return f"SELECT ?type (COUNT(DISTINCT ?mesure) AS ?nombre) WHERE {{\n  {corps}\n}}\nGROUP BY ?type", False
        if intention in ("somme", "moyenne"):
            fn, alias = ("SUM", "?totalKWh") if intention == "somme" else ("AVG", "?moyenneKWh")
            return (f"# consommation et production ne sont jamais additionnées ensemble\n"
                    f"SELECT ?type ({fn}(?valeurKWh) AS {alias}) (COUNT(?mesure) AS ?nombre) WHERE {{\n"
                    f"  {{ SELECT DISTINCT ?mesure ?type ?valeurKWh WHERE {{\n  {corps}\n  FILTER(BOUND(?valeurKWh))\n  }} }}\n"
                    f"}}\nGROUP BY ?type"), False
        select = "SELECT DISTINCT ?mesure ?label ?type ?valeurKWh ?dateDebut ?dateFin ?compteur ?cible ?via"
        if intention in ("max", "min"):
            ordre = "DESC(?valeurKWh)" if intention == "max" else "ASC(?valeurKWh)"
            return f"{select} WHERE {{\n  {corps}\n  FILTER(BOUND(?valeurKWh))\n}}\nORDER BY {ordre}\nLIMIT 1", False
        return f"{select} WHERE {{\n  {corps}\n}}\nORDER BY DESC(?dateDebut) ?label", False

    if cible == "compteur":
        motifs_ = ["?compteur a sg:CompteurIntelligent .",
                   "OPTIONAL { ?compteur rdfs:label ?label }",
                   "OPTIONAL { ?compteur sg:identifiant ?identifiant }",
                   f"# installeDans, ou son inverse equipeDe\n  OPTIONAL {{ {Q.installation('?compteur', '?batiment')} }}"]
        for e in par_type("batiment"):
            motifs_.append(f"FILTER(?batiment = {sg(e['id'])})")
        for e in par_type("compteur"):
            motifs_.append(f"FILTER(?compteur = {sg(e['id'])})")
        for e in par_type("mesure"):
            motifs_.append(f"?compteur sg:enregistre {sg(e['id'])} .")
        corps = "\n  ".join(motifs_)
        if intention == "compter":
            return f"SELECT (COUNT(DISTINCT ?compteur) AS ?nombre) WHERE {{\n  {corps}\n}}", False
        if intention == "existe":
            return f"ASK {{\n  {corps}\n}}", True
        return (f"SELECT DISTINCT ?compteur ?label ?identifiant ?batiment WHERE {{\n  {corps}\n}}\n"
                f"ORDER BY ?identifiant"), False

    if cible == "operateur":
        motifs_ = ["?operateur a sg:OperateurReseau .", "OPTIONAL { ?operateur rdfs:label ?label }"]
        infras = par_type("poste", "ligne")
        for e in infras:
            x = sg(e["id"])
            motifs_.append(f"# gere asserté, ou R4 : gere(o, p) ∧ relie(l, p) → gere(o, l)\n"
                           f"  {{ ?operateur sg:gere {x} . BIND(\"gere\" AS ?via) }}\n"
                           f"  UNION {{ ?operateur sg:gere ?p4 . {x} sg:relie ?p4 . BIND(\"R4\" AS ?via) }}\n"
                           f"  BIND({x} AS ?infrastructure)")
        for e in par_type("operateur"):
            motifs_.append(f"FILTER(?operateur = {sg(e['id'])})")
        corps = "\n  ".join(motifs_)
        if intention == "compter":
            return f"SELECT (COUNT(DISTINCT ?operateur) AS ?nombre) WHERE {{\n  {corps}\n}}", False
        if infras:
            return f"SELECT DISTINCT ?operateur ?label ?infrastructure ?via WHERE {{\n  {corps}\n}}\nORDER BY ?label", False
        return (f"SELECT ?operateur ?label (COUNT(DISTINCT ?g) AS ?nbInfrastructures) WHERE {{\n  {corps}\n"
                f"  OPTIONAL {{ ?operateur sg:gere ?g }}\n}}\nGROUP BY ?operateur ?label\nORDER BY ?label"), False

    if cible == "infrastructure":
        motifs_ = []
        ops = par_type("operateur")
        if ops:
            motifs_.append("VALUES ?operateur { " + " ".join(sg(e["id"]) for e in ops) + " }")
        motifs_ += ["?operateur a sg:OperateurReseau .",
                    "{ ?operateur sg:gere ?infrastructure . BIND(\"gere\" AS ?via) }\n"
                    "  UNION { # R4 : gere(o, p) ∧ relie(l, p) → gere(o, l)\n"
                    "    ?operateur sg:gere ?p4 . ?infrastructure sg:relie ?p4 .\n"
                    "    FILTER NOT EXISTS { ?operateur sg:gere ?infrastructure } BIND(\"R4\" AS ?via) }",
                    "?infrastructure a ?classe . ?classe rdfs:subClassOf* sg:InfrastructureReseau .",
                    "OPTIONAL { ?infrastructure rdfs:label ?label }"]
        if a["typeInfrastructure"] == "poste":
            motifs_.append("?infrastructure a sg:PosteElectrique .")
        elif a["typeInfrastructure"] == "ligne":
            motifs_.append("?infrastructure a/rdfs:subClassOf* sg:LigneElectrique .")
        for e in par_type("poste", "ligne"):
            motifs_.append(f"FILTER(?infrastructure = {sg(e['id'])})")
        corps = "\n  ".join(motifs_)
        if intention == "compter":
            return f"SELECT (COUNT(DISTINCT ?infrastructure) AS ?nombre) WHERE {{\n  {corps}\n}}", False
        return (f"SELECT DISTINCT ?infrastructure ?label ?classe ?operateur ?via WHERE {{\n  {corps}\n}}\n"
                f"ORDER BY ?via ?classe ?label"), False
    return None, False


# ------------------------------------------------------------ restitution --

NOMS_CIBLES = {"compteur": "compteurs", "mesure": "mesures", "operateur": "opérateurs",
               "infrastructure": "infrastructures gérées"}
NOMS_INTENTIONS = {"lister": "Lister", "compter": "Compter", "max": "Maximum", "min": "Minimum",
                   "somme": "Somme", "moyenne": "Moyenne", "existe": "Existe-t-il", "ecriture": "Écriture"}


def _fmt(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def interpretation(a):
    morceaux = [f"{NOMS_INTENTIONS[a['intention']]} · {NOMS_CIBLES.get(a['cible'], '?')}"]
    if a["typeMesure"]:
        morceaux.append(f"type {a['typeMesure']}")
    if a["typeInfrastructure"]:
        morceaux.append(f"type {a['typeInfrastructure']}")
    for e in a["entites"]:
        morceaux.append(f"{e['type']} = sg:{e['id']}")
    for c in a["comparaisons"]:
        if c["op"] == "entre":
            morceaux.append(f"valeur entre {_fmt(c['min'])} et {_fmt(c['max'])} kWh")
        else:
            morceaux.append(f"valeur {SYMBOLES[c['op']]} {_fmt(c['valeur'])} kWh")
    if p := a["periode"]:
        morceaux.append(f"période {p['debut'] or '…'} → {p['fin'] or '…'}")
    return " · ".join(morceaux)


EXEMPLES = [
    "Affiche tous les compteurs intelligents.",
    "Quels compteurs sont installés dans Maison1 ?",
    "Quelles mesures sont enregistrées par Compteur_M1 ?",
    "Affiche les mesures de consommation supérieures à 100 kWh.",
    "Affiche les mesures de production inférieures à 500 kWh.",
    "Quelle est la consommation totale de Maison1 en janvier 2025 ?",
    "Affiche les mesures entre le 1 janvier 2025 et le 31 mars 2025.",
    "Quels opérateurs gèrent Poste_Rades ?",
    "Quelles infrastructures sont gérées par STEG ?",
    "Combien de mesures de consommation au 1er trimestre 2025 ?",
    "Quelle est la plus grande mesure de production ?",
    "Qui gère la ligne Tunis Sousse ?",
]

AIDE = ("Questions prises en charge : compteurs (liste, bâtiment d'installation), mesures (type, compteur, "
        "bâtiment ou source, seuil en kWh/MWh, période), totaux et moyennes par type, opérateurs qui gèrent une "
        "infrastructure, infrastructures gérées par un opérateur.")


def repondre(question):
    a = analyser(question)
    reponse = {"analyse": a, "interpretation": None, "sparql": None, "notes": []}

    if a["intention"] == "ecriture":
        reponse["erreur"] = ("Le traducteur est en lecture seule : créez, modifiez ou supprimez les compteurs, "
                             "mesures et opérateurs dans les onglets du module (confirmation demandée).")
        return reponse
    if a["inconnus"] and not a["entites"]:
        reponse["precision"] = {"message": f"Je ne connais pas « {', '.join(a['inconnus'])} » dans l'ontologie. "
                                           "Vérifiez l'identifiant ou le libellé.", "candidats": []}
        return reponse
    if a["inconnus"]:
        reponse["notes"].append(f"Ignoré car inconnu de l'ontologie : {', '.join(a['inconnus'])}.")
    if a["ambigues"]:
        e = a["ambigues"][0]
        reponse["precision"] = {"message": f"« {e['texte']} » peut désigner plusieurs individus : lequel ?",
                                "candidats": e["candidats"]}
        return reponse
    if a["erreurDate"]:
        reponse["precision"] = {"message": a["erreurDate"], "candidats": []}
        return reponse

    sparql, est_ask = generer(a)
    if sparql is None:
        reponse["erreur"] = "Je n'ai pas reconnu de quoi parle la question. " + AIDE
        return reponse
    reponse["interpretation"] = interpretation(a)
    reponse["sparql"] = sparql

    if a["periode"]:
        if a["intention"] in ("somme", "moyenne"):
            reponse["notes"].append("Période : seules les mesures entièrement comprises dans l'intervalle "
                                    "sont agrégées (aucune proratisation).")
        elif a["cible"] == "mesure":
            reponse["notes"].append("Période : mesures dont la période chevauche l'intervalle demandé.")
        if a["periode"]["convention"]:
            reponse["notes"].append(f"Date incomplète : {a['periode']['convention']}.")
    if any(c.get("uniteSupposee") for c in a["comparaisons"]):
        reponse["notes"].append("Valeur sans unité : kWh par convention.")
    if a["periode"] and a["cible"] != "mesure":
        reponse["notes"].append("La période ne s'applique qu'aux mesures : elle est ignorée ici.")

    if est_ask:
        reponse["booleen"] = store.ask(sparql)
        reponse["colonnes"], reponse["lignes"] = [], []
        return reponse

    lignes = store.select(sparql)
    # colonnes du SELECT : « (SUM(?v) AS ?total) » compte pour ?total
    entete = sparql.split("SELECT", 1)[1].split("WHERE", 1)[0]
    entete = re.sub(r"\([^()]*\([^()]*\)\s+AS\s+(\?\w+)\)", r"\1", entete)
    reponse["colonnes"] = re.findall(r"\?(\w+)", entete)
    reponse["lignes"] = [{k: (str(v).replace(" ", "T") if k in ("dateDebut", "dateFin") and v else v)
                          for k, v in r.items()} for r in lignes]

    vide = not lignes or (len(lignes) == 1 and lignes[0].get("nombre") == 0)
    if a["cible"] == "mesure" and a["intention"] in ("somme", "moyenne") and lignes:
        ids = {m["mesure"] for m in store.select(
            "SELECT DISTINCT ?mesure WHERE {\n  " + _corps_mesures(a) + "\n}")}
        paires = [r for r in store.select(Q.chevauchements()) if r["m1"] in ids and r["m2"] in ids]
        if paires:
            reponse["notes"].append("Attention : des mesures additionnées se chevauchent pour une même cible ("
                                    + ", ".join(f"{p['m1']} / {p['m2']}" for p in paires) + ").")
    if vide and a["cible"] == "mesure" and a["periode"]:
        plage = store.select("SELECT (MIN(?dateDebut) AS ?min) (MAX(?dateFin) AS ?max) WHERE {\n  "
                             + _corps_mesures(a, avec_periode=False) + "\n}")
        if plage and plage[0]["min"]:
            reponse["notes"].append(f"Aucune mesure dans cette période. Les mesures correspondant aux autres "
                                    f"critères couvrent {str(plage[0]['min'])[:10]} → {str(plage[0]['max'])[:10]}.")
        else:
            reponse["notes"].append("Aucune mesure ne correspond aux autres critères, quelle que soit la période.")
    return reponse
