"""Module NLP → SPARQL de la Production d'énergie (Membre 1 · Wala Rezgui).

Traduit une question en français en requête SPARQL, sans API de LLM.
Outils : spaCy 3 + fr_core_news_sm (tokenisation, lemmatisation, POS, NER),
PhraseMatcher (liaison des mots aux individus : sources, lignes, bâtiments) et
Matcher (motifs de tokens : puissances avec unité, dates, années).

Étapes :
  1. normalisation (minuscules, accents, ponctuation de liaison) et analyse spaCy ;
  2. liaison d'entités par PhraseMatcher (libellés et identifiants) ; un nom ambigu
     déclenche une demande de précision, un identifiant inconnu aussi ;
  3. Matcher : « 100 kW », « 2,5 MW » (→ 2 500 kW), « 1 janvier 2020 », « après 2010 »… ;
     une énergie en kWh est refusée : la puissance installée s'exprime en kW ;
  4. intention (lister, compter, somme, moyenne, max, min, existe), cible (sources,
     lignes d'injection, bâtiments alimentés) et catégorie (renouvelable, solaire…)
     à partir des lemmes et formes normalisées ;
  5. requête SPARQL construite par patrons contrôlés (sous-classes, inverse, R1, R6, R7),
     exécutée par RDFLib. Lecture seule : le CRUD se fait dans les formulaires.
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
UNITES_PUISSANCE = {"w": 0.001, "kw": 1, "mw": 1000, "gw": 1_000_000}
UNITES_ENERGIE = {"wh", "kwh", "mwh", "gwh"}

CIBLES = {
    "source": {"source", "sources", "installation", "installations", "centrale", "centrales", "parc", "parcs",
               "producteur", "producteurs", "eolienne", "eoliennes", "panneau", "panneaux", "unite", "unites"},
    "ligne": {"ligne", "lignes", "cable", "cables"},
    "batiment": {"batiment", "batiments", "immeuble", "immeubles", "edifice", "edifices", "consommateur",
                 "consommateurs", "maison", "maisons"},
}
CATEGORIES = [  # (catégorie, formes normalisées) — « non renouvelable » est testé avant « renouvelable »
    ("non_renouvelable", {"fossile", "fossiles", "thermique", "thermiques", "gaz", "classique", "classiques"}),
    ("solaire", {"solaire", "solaires", "photovoltaique", "photovoltaiques", "panneau", "panneaux", "pv"}),
    ("eolien", {"eolien", "eoliens", "eolienne", "eoliennes", "vent"}),
    ("renouvelable", {"renouvelable", "renouvelables", "verte", "vertes", "vert", "verts", "propre", "propres"}),
]
ECRITURE = {"supprimer", "supprime", "supprimez", "effacer", "efface", "ajouter", "ajoute", "ajoutez", "creer",
            "cree", "creez", "modifier", "modifie", "modifiez", "inserer", "insere", "changer", "change", "renommer"}
SUPERLATIFS = {"puissant": "max", "puissante": "max", "puissants": "max", "puissantes": "max",
               "grand": "max", "grande": "max", "gros": "max", "grosse": "max", "important": "max",
               "importante": "max", "eleve": "max", "elevee": "max", "petit": "min", "petite": "min",
               "faible": "min", "recent": "max_date", "recente": "max_date", "ancien": "min_date",
               "ancienne": "min_date", "vieux": "min_date", "vieille": "min_date"}
COMPARATEURS = [
    ("superieur ou egal", ">="), ("superieure ou egale", ">="), ("superieures ou egales", ">="),
    ("inferieur ou egal", "<="), ("inferieure ou egale", "<="), ("inferieures ou egales", "<="),
    ("au moins", ">="), ("minimum", ">="), ("au plus", "<="), ("maximum", "<="),
    ("au dessus de", ">"), ("en dessous de", "<"), ("plus de", ">"), ("plus que", ">"),
    ("moins de", "<"), ("moins que", "<"),
    ("superieur", ">"), ("superieure", ">"), ("superieurs", ">"), ("superieures", ">"),
    ("depasse", ">"), ("depassent", ">"), ("depassant", ">"), ("excede", ">"),
    ("inferieur", "<"), ("inferieure", "<"), ("inferieurs", "<"), ("inferieures", "<"),
    (">=", ">="), ("<=", "<="), (">", ">"), ("<", "<"),
]
SYMBOLES = {">": ">", ">=": "≥", "<": "<", "<=": "≤", "=": "="}
TYPES_UTILES = {"source": {"source", "ligne", "batiment"}, "ligne": {"source", "ligne"},
                "batiment": {"source", "batiment"}}


def normaliser(texte):
    """minuscules, sans accents, ponctuation de liaison → espace (même longueur que l'entrée)."""
    sans_accents = "".join(unicodedata.normalize("NFD", c)[0] for c in texte.lower())
    return re.sub(r"[-–—_'’]", " ", sans_accents)


# ------------------------------------------------------------ pipeline spaCy --

_nlp = None
_matcher = None
_matcher_version = None
_individus = {}
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
    """Matcher spaCy (texte normalisé) : puissances, énergies, dates complètes, mois, années."""
    global _motifs
    if _motifs is None:
        m = Matcher(nlp().vocab)
        mois = {"LOWER": {"IN": list(MOIS)}}
        annee = {"TEXT": {"REGEX": r"^(19\d\d|20\d\d|2100)$"}}
        m.add("JOUR", [[{"TEXT": {"REGEX": r"^(\d{1,2}|1er)$"}}, mois, {**annee, "OP": "?"}]])
        m.add("MOIS", [[mois, {**annee, "OP": "?"}]])
        m.add("JJMMAAAA", [[{"TEXT": {"REGEX": r"^\d{1,2}/\d{1,2}/\d{4}$"}}]])
        m.add("ISO", [[annee, {"SHAPE": "dd"}, {"SHAPE": "dd"}]])
        m.add("ANNEE", [[{"LOWER": {"IN": ["en", "annee", "an", "depuis", "apres", "avant"]}}, annee]])
        m.add("ENTRE_ANNEES", [[{"LOWER": "entre"}, annee, {"LOWER": "et"}, annee]])
        m.add("PUISSANCE", [[{"LIKE_NUM": True}, {"LOWER": {"IN": list(UNITES_PUISSANCE)}}],
                            [{"LOWER": {"REGEX": r"^\d+([.,]\d+)?[kmg]?w$"}}]])
        m.add("ENERGIE", [[{"LIKE_NUM": True}, {"LOWER": {"IN": list(UNITES_ENERGIE)}}],
                          [{"LOWER": {"REGEX": r"^\d+([.,]\d+)?[kmg]?wh$"}}]])
        _motifs = m
    return _motifs


INDIVIDUS = """
SELECT ?x ?type ?label WHERE {
  { ?x a/rdfs:subClassOf* sg:SourceEnergie . BIND("source" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:LigneElectrique . BIND("ligne" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:Batiment . BIND("batiment" AS ?type) }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
}"""


def _alias(type_, ident, label):
    """(noms exacts, noms de lieu) ; un nom exact l'emporte sur un nom de lieu."""
    exacts = {ident, ident.replace("_", " ")}
    if label:
        exacts.add(label)
    lieux = set()
    if type_ == "ligne":
        reste = re.sub(r"^Ligne_((BT|MT|HT)_)?", "", ident).replace("_", " ")
        exacts |= {f"ligne {reste}", f"ligne de {reste}", f"ligne d {reste}", f"ligne du {reste}"}
    elif "_" in ident:
        lieux.add(ident.rsplit("_", 1)[-1])  # CentraleSolaire_Tozeur → « Tozeur »
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
        if r["x"] in _individus:
            continue
        _individus[r["x"]] = (r["type"], r["label"] or r["x"])
        exacts, lieux = _alias(r["type"], r["x"], r["label"])
        _matcher.add(f"exact|{r['type']}|{r['x']}", [nlp().make_doc(a) for a in exacts])
        if lieux:
            _matcher.add(f"lieu|{r['type']}|{r['x']}", [nlp().make_doc(a) for a in lieux])
    _matcher_version = version
    return _matcher


# ---------------------------------------------------------------- analyse --

def _dans(idx, plages):
    return any(a <= idx < b for a, b in plages)


def _entites(ndoc):
    candidats = {}
    for match_id, start, end in _matcher_a_jour()(ndoc):
        force, type_, ident = nlp().vocab.strings[match_id].split("|", 2)
        candidats.setdefault((start, end), {})[ident] = (force, type_)
    out = []
    for span in filter_spans([ndoc[s:e] for s, e in candidats]):
        c = candidats[(span.start, span.end)]
        garder = {i: t for i, (f, t) in c.items() if f == "exact"} or {i: t for i, (f, t) in c.items()}
        out.append({"texte": span.text, "debut": span.start_char, "fin": span.end_char,
                    "candidats": [{"id": i, "type": t, "label": _individus[i][1]} for i, t in garder.items()]})
    return out


def _intervalle(label, textes, annee_defaut):
    """Span de date → (début, fin, année manquante)."""
    annee = next((int(x) for x in textes if re.fullmatch(r"19\d\d|20\d\d|2100", x)), None)
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
        if label == "ENTRE_ANNEES":
            a1, a2 = (int(x) for x in textes if re.fullmatch(r"\d{4}", x))
            return datetime(a1, 1, 1), datetime(a2, 12, 31, 23, 59, 59), False
        manque = annee is None
        annee = annee or annee_defaut or 2000
        if label == "JOUR":
            d = datetime(annee, MOIS[textes[1]], 1 if textes[0] == "1er" else int(textes[0]))
            return d, d.replace(hour=23, minute=59, second=59), manque
        if label == "MOIS":
            m = MOIS[textes[0]]
            return (datetime(annee, m, 1), datetime(annee, m, calendar.monthrange(annee, m)[1], 23, 59, 59), manque)
    except (ValueError, KeyError, IndexError):
        return None
    return None


def _periode(ndoc, spans):
    """Dates de mise en service : « après le 1 janvier 2020 », « avant 2000 », « entre 2000 et 2015 »…"""
    dates = [(s, lab) for s, lab in spans if lab not in ("PUISSANCE", "ENERGIE")]
    if not dates:
        return None, None
    annees = [int(t.text) for s, _ in dates for t in s if re.fullmatch(r"19\d\d|20\d\d|2100", t.text)]
    defaut = annees[-1] if annees else None
    valeurs = []
    for s, lab in dates:
        v = _intervalle(lab, [t.text for t in s], defaut)
        if v is None:
            return None, f"Date invalide : « {s.text} »"
        valeurs.append((s, v))
    if any(v[2] for _, v in valeurs) and defaut is None:
        return None, f"Précisez l'année pour « {valeurs[0][0].text} » (ex. « janvier 2020 »)."
    (s1, (d1, f1, _)), (s2, (_, f2, _)) = valeurs[0], valeurs[-1]
    avant = " ".join(t.text for t in ndoc[max(0, s1.start - 3):s1.start + 1])
    if len(valeurs) >= 2 or "entre" in avant:
        debut, fin, sens = d1, f2, "entre"
    elif re.search(r"\bapres\b", avant):
        debut, fin, sens = f1 + timedelta(seconds=1), None, "après"
    elif re.search(r"\b(depuis|partir|des)\b", avant):
        debut, fin, sens = d1, None, "depuis"
    elif re.search(r"\bavant\b", avant):
        debut, fin, sens = None, d1 - timedelta(seconds=1), "avant"
    elif re.search(r"\bjusqu", avant):
        debut, fin, sens = None, f1, "jusqu'à"
    else:
        debut, fin, sens = d1, f1, "pendant"
    if debut and fin and fin < debut:
        return None, "La date de fin précède la date de début."
    fmt = lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") if d else None  # noqa: E731
    convention = "année reprise de l'autre date de la question" if any(v[2] for _, v in valeurs) else None
    return {"debut": fmt(debut), "fin": fmt(fin), "sens": sens, "convention": convention}, None


def _nombre(texte):
    try:
        return float(texte.replace(",", "."))
    except ValueError:
        return None


def _comparaisons(ndoc, spans, exclus):
    """Puissances en kW (MW, GW, W convertis) et comparateurs ; nombre sans unité après un comparateur → kW."""
    quantites = []
    for s, lab in spans:
        if lab != "PUISSANCE":
            continue
        if len(s) == 2:
            v, unite = _nombre(s[0].text), s[1].lower_
        else:
            m = re.fullmatch(r"(\d+(?:[.,]\d+)?)([kmg]?w)", s[0].lower_)
            v, unite = _nombre(m.group(1)), m.group(2)
        quantites.append({"start": s.start, "valeur": v * UNITES_PUISSANCE[unite], "unite": unite})
    pris = {i for s, _ in spans for i in range(s.start, s.end)}
    for t in ndoc:
        if t.i in pris or _dans(t.idx, exclus) or not t.like_num or _nombre(t.text) is None:
            continue
        avant = " ".join(x.text for x in ndoc[max(0, t.i - 4):t.i])
        if any(re.search(rf"(^|\s){re.escape(e)}(\s+a|\s+de)?$", avant) for e, _ in COMPARATEURS) \
                or re.search(r"(^|\s)entre$", avant) or re.search(r"(^|\s)et$", avant) and quantites:
            quantites.append({"start": t.i, "valeur": _nombre(t.text), "unite": None})
    quantites.sort(key=lambda q: q["start"])

    out, i = [], 0
    while i < len(quantites):
        q = quantites[i]
        avant = " ".join(x.text for x in ndoc[max(0, q["start"] - 4):q["start"]])
        if re.search(r"(^|\s)entre$", avant) and i + 1 < len(quantites):
            out.append({"op": "entre", "min": q["valeur"], "max": quantites[i + 1]["valeur"],
                        "unites": [q["unite"], quantites[i + 1]["unite"]]})
            i += 2
            continue
        op = next((s for e, s in COMPARATEURS if re.search(rf"(^|\s){re.escape(e)}(\s+a|\s+de)?$", avant)), "=")
        out.append({"op": op, "valeur": q["valeur"], "unites": [q["unite"]]})
        i += 1
    return out


def analyser(question):
    texte = unicodedata.normalize("NFC", re.sub(r"\s+", " ", question)).strip()
    doc = nlp()(texte)
    ndoc = nlp().make_doc(normaliser(texte))
    entites = _entites(ndoc)
    plages = [(e["debut"], e["fin"]) for e in entites]

    spans = [(ndoc[s:e], nlp().vocab.strings[mid]) for mid, s, e in motifs()(ndoc)]
    gardes = {(sp.start, sp.end) for sp in filter_spans([sp for sp, _ in spans])}
    spans = sorted({(sp.start, sp.end): (sp, lab) for sp, lab in spans
                    if (sp.start, sp.end) in gardes and not _dans(sp.start_char, plages)}.values(),
                   key=lambda x: x[0].start)
    exclus = plages + [(sp.start_char, sp.end_char) for sp, _ in spans]

    reste = [t for t in doc if not _dans(t.idx, plages)]
    formes = [(normaliser(t.lemma_ or t.text).strip(), normaliser(t.text).strip()) for t in reste]
    mots = [f for _, f in formes]
    texte_reste = " ".join(mots)
    contient = lambda vocab: any(l in vocab or f in vocab for l, f in formes)  # noqa: E731
    inconnus = [t.text for t in reste if re.fullmatch(r"[A-Za-z]+_[A-Za-z0-9_]+|[A-Z][a-z]+\d+", t.text)]

    # catégorie (sous-classes comprises) ; « non renouvelable » / « pas renouvelable » d'abord
    categorie = None
    if re.search(r"\b(non|pas) renouvelables?\b", texte_reste):
        categorie = "non_renouvelable"
    else:
        categorie = next((c for c, vocab in CATEGORIES if contient(vocab)), None)

    # classe cible : premier nom (hors entités) qui désigne sources, lignes ou bâtiments
    cible = None
    for l, f in formes:
        cible = next((c for c, vocab in CIBLES.items() if l in vocab or f in vocab), None)
        if cible:
            break
    alimente = any(f.startswith(("aliment", "fourni", "desser")) or l.startswith(("aliment", "fournir"))
                   for l, f in formes)
    injecte = any(f.startswith("inject") or l.startswith("inject") for l, f in formes)
    types = {c["type"] for e in entites for c in e["candidats"]}
    if cible is None:
        if "source" in types and alimente:
            cible = "batiment"
        elif "source" in types and injecte:
            cible = "ligne"
        elif types & {"source", "batiment", "ligne"} or categorie:
            cible = "source"

    ambigues = []
    for e in entites:
        utiles = [c for c in e["candidats"] if cible is None or c["type"] in TYPES_UTILES.get(cible, set())]
        if len(utiles) == 1 or (len(e["candidats"]) == 1 and not utiles):
            e.update(utiles[0] if utiles else e["candidats"][0])
        else:
            ambigues.append(e)

    intention, attribut = "lister", "puissance"
    if contient(ECRITURE):
        intention = "ecriture"
    elif "combien" in mots or "nombre" in mots:
        intention = "compter"
    elif re.search(r"\b(total|totale|totaux|totales|somme|cumul|cumule|cumulee|globale)\b", texte_reste):
        intention = "somme"
    elif re.search(r"\b(moyenne|moyen|moyennes)\b", texte_reste):
        intention = "moyenne"
    elif re.search(r"^(est ce qu|existe|y a t il)|existe t il", texte_reste):
        intention = "existe"
    else:
        for i, m in enumerate(mots[:-1]):
            if m in ("plus", "moins") and mots[i + 1] in SUPERLATIFS:
                sens = SUPERLATIFS[mots[i + 1]]
                if sens.endswith("_date"):
                    attribut, sens = "date", sens[:3]
                intention = sens if m == "plus" else ("min" if sens == "max" else "max")
                break
        if intention == "lister" and re.search(r"\b(maximale|maximal|max)\b", texte_reste):
            intention = "max"
        elif intention == "lister" and re.search(r"\b(minimale|minimal|min)\b", texte_reste):
            intention = "min"

    periode, erreur_date = _periode(ndoc, spans)
    energie = [sp.text for sp, lab in spans if lab == "ENERGIE"]
    comparaisons = _comparaisons(ndoc, spans, exclus)

    return {
        "question": texte,
        "tokens": [{"texte": t.text, "lemme": t.lemma_ or t.text, "pos": t.pos_} for t in doc],
        "ner": [{"texte": e.text, "label": e.label_} for e in doc.ents],
        "entites": [e for e in entites if "id" in e],
        "ambigues": ambigues,
        "inconnus": inconnus,
        "intention": intention,
        "cible": cible,
        "categorie": categorie,
        "attribut": attribut,
        "comparaisons": comparaisons,
        "periode": periode,
        "erreurDate": erreur_date,
        "energie": energie,
    }


# ------------------------------------------------------- génération SPARQL --

def _filtres_source(a, var="?source", puissance="?puissanceKW", date="?dateMiseEnService"):
    """Catégorie (sous-classes comprises), comparaisons de puissance, période de mise en service."""
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    out = []
    if a["categorie"]:
        out.append(Q.CATEGORIES[a["categorie"]].replace("?s ", f"{var} "))
    for c in a["comparaisons"]:
        if c["op"] == "entre":
            out.append(f"FILTER({puissance} >= {float(c['min'])} && {puissance} <= {float(c['max'])})")
        else:
            out.append(f"FILTER({puissance} {c['op']} {float(c['valeur'])})")
    if p := a["periode"]:
        if p["debut"]:
            out.append(f"FILTER({date} >= {Q.n3_date(p['debut'])})")
        if p["fin"]:
            out.append(f"FILTER({date} <= {Q.n3_date(p['fin'])})")
    for e in a["entites"]:
        if e["type"] == "source":
            out.append(f"FILTER({var} = {sg(e['id'])})")
    return out


def generer(a):
    """Construit la requête SPARQL à partir de l'analyse. Renvoie (sparql, est_ask)."""
    cible, intention = a["cible"], a["intention"]
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    par_type = lambda t: [e for e in a["entites"] if e["type"] == t]  # noqa: E731

    if cible == "source":
        base = ["?source a/rdfs:subClassOf* sg:SourceEnergie .",
                "OPTIONAL { ?source rdfs:label ?label }",
                "OPTIONAL { ?source sg:puissanceInstallee ?puissanceKW }",
                "OPTIONAL { ?source sg:dateMiseEnService ?dateMiseEnService }",
                "# type le plus précis (Solaire, Eolien…) ; les parents ne sont pas forcément assertés\n"
                "  OPTIONAL { ?source a ?type . ?type rdfs:subClassOf* sg:SourceEnergie .\n"
                "    FILTER NOT EXISTS { ?source a ?autre . ?autre rdfs:subClassOf+ ?type . FILTER(?autre != ?type) } }"]
        base += _filtres_source(a)
        for e in par_type("batiment"):
            base.append(f"# alimentation : estAlimentePar, produitEnergiePour (inverse), R1, R7, R6\n"
                        f"  {Q.chemins('?source', sg(e['id']), '?par', '?via')}")
        for e in par_type("ligne"):
            base.append(f"?source sg:injecteDans {sg(e['id'])} .")
        corps = "\n  ".join(base)
        if intention == "existe":
            return f"ASK {{\n  {corps}\n}}", True
        if intention == "compter":
            return f"SELECT (COUNT(DISTINCT ?source) AS ?nombre) WHERE {{\n  {corps}\n}}", False
        if intention in ("somme", "moyenne"):
            fn, alias = ("SUM", "?puissanceTotaleKW") if intention == "somme" else ("AVG", "?puissanceMoyenneKW")
            return (f"# puissance installée (kW) ; les sources sans puissance renseignée ne sont pas comptées comme 0\n"
                    f"SELECT ({fn}(?puissanceKW) AS {alias}) (COUNT(?puissanceKW) AS ?avecPuissance)\n"
                    f"       (COUNT(?source) AS ?nbSources) WHERE {{\n"
                    f"  {{ SELECT DISTINCT ?source ?puissanceKW WHERE {{\n  {corps}\n  }} }}\n}}"), False
        if par_type("batiment"):
            return (f"SELECT ?source ?label ?type\n"
                    f"       (GROUP_CONCAT(DISTINCT CONCAT(?via, COALESCE(CONCAT(\" via \", STRAFTER(STR(?par), \"#\")), \"\"));"
                    f" separator=\", \") AS ?justification)\nWHERE {{\n  {corps}\n}}\n"
                    f"GROUP BY ?source ?label ?type\nORDER BY ?label"), False
        select = "SELECT DISTINCT ?source ?label ?type ?puissanceKW ?dateMiseEnService"
        if intention in ("max", "min"):
            var = "?puissanceKW" if a["attribut"] == "puissance" else "?dateMiseEnService"
            ordre = f"DESC({var})" if intention == "max" else f"ASC({var})"
            return f"{select} WHERE {{\n  {corps}\n  FILTER(BOUND({var}))\n}}\nORDER BY {ordre}\nLIMIT 1", False
        return f"{select} WHERE {{\n  {corps}\n}}\nORDER BY DESC(?puissanceKW) ?label", False

    if cible == "ligne":
        motifs_ = ["?source sg:injecteDans ?ligne .", "?source a/rdfs:subClassOf* sg:SourceEnergie .",
                   "OPTIONAL { ?ligne rdfs:label ?label }", "OPTIONAL { ?ligne sg:tension ?tensionKV }",
                   "OPTIONAL { ?source sg:puissanceInstallee ?puissanceKW }",
                   "OPTIONAL { ?source sg:dateMiseEnService ?dateMiseEnService }"]
        motifs_ += _filtres_source(a)
        for e in par_type("ligne"):
            motifs_.append(f"FILTER(?ligne = {sg(e['id'])})")
        corps = "\n  ".join(motifs_)
        if intention == "compter":
            return f"SELECT (COUNT(DISTINCT ?ligne) AS ?nombre) WHERE {{\n  {corps}\n}}", False
        return f"SELECT DISTINCT ?ligne ?label ?tensionKV ?source WHERE {{\n  {corps}\n}}\nORDER BY ?label", False

    if cible == "batiment":
        motifs_ = ["?source a/rdfs:subClassOf* sg:SourceEnergie .",
                   "OPTIONAL { ?source sg:puissanceInstallee ?puissanceKW }",
                   "OPTIONAL { ?source sg:dateMiseEnService ?dateMiseEnService }",
                   f"# alimentation : estAlimentePar, produitEnergiePour (inverse), R1, R7, R6\n"
                   f"  {Q.chemins('?source', '?batiment', '?par', '?via')}",
                   "OPTIONAL { ?batiment rdfs:label ?label }"]
        motifs_ += _filtres_source(a)
        for e in par_type("batiment"):
            motifs_.append(f"FILTER(?batiment = {sg(e['id'])})")
        corps = "\n  ".join(motifs_)
        if intention == "compter":
            return f"SELECT (COUNT(DISTINCT ?batiment) AS ?nombre) WHERE {{\n  {corps}\n}}", False
        return (f"SELECT ?batiment ?label\n"
                f"       (GROUP_CONCAT(DISTINCT CONCAT(STRAFTER(STR(?source), \"#\"), \" : \", ?via,"
                f" COALESCE(CONCAT(\" via \", STRAFTER(STR(?par), \"#\")), \"\")); separator=\", \") AS ?justification)\n"
                f"WHERE {{\n  {corps}\n}}\nGROUP BY ?batiment ?label\nORDER BY ?label"), False
    return None, False


# ------------------------------------------------------------ restitution --

NOMS_CIBLES = {"source": "sources d'énergie", "ligne": "lignes d'injection", "batiment": "bâtiments alimentés"}
NOMS_INTENTIONS = {"lister": "Lister", "compter": "Compter", "max": "Maximum", "min": "Minimum",
                   "somme": "Somme", "moyenne": "Moyenne", "existe": "Existe-t-il", "ecriture": "Écriture"}
NOMS_CATEGORIES = {"renouvelable": "renouvelables (Solaire, Eolien compris)", "non_renouvelable": "non renouvelables",
                   "solaire": "solaires", "eolien": "éoliennes"}


def _fmt(x):
    return f"{x:,.0f}".replace(",", " ") if float(x).is_integer() else str(x)


def interpretation(a):
    m = [f"{NOMS_INTENTIONS[a['intention']]} · {NOMS_CIBLES.get(a['cible'], '?')}"]
    if a["intention"] in ("somme", "moyenne", "max", "min"):
        m.append("sur la puissance installée (kW)" if a["attribut"] == "puissance" else "sur la date de mise en service")
    if a["categorie"]:
        m.append(f"catégorie {NOMS_CATEGORIES[a['categorie']]}")
    for e in a["entites"]:
        m.append(f"{e['type']} = sg:{e['id']}")
    for c in a["comparaisons"]:
        if c["op"] == "entre":
            m.append(f"puissance entre {_fmt(c['min'])} et {_fmt(c['max'])} kW")
        else:
            m.append(f"puissance {SYMBOLES[c['op']]} {_fmt(c['valeur'])} kW")
    if p := a["periode"]:
        m.append(f"mise en service {p['sens']} : {p['debut'] or '…'} → {p['fin'] or '…'}")
    return " · ".join(m)


EXEMPLES = [
    "Affiche toutes les sources d'énergie.",
    "Quelles sont les sources renouvelables ?",
    "Liste les sources non renouvelables.",
    "Affiche les installations solaires.",
    "Quels sont les parcs éoliens ?",
    "Quelles sources ont une puissance supérieure à 100 kW ?",
    "Quelles sources ont une puissance comprise entre 50 et 500 kW ?",
    "Quelle est la puissance installée totale des sources solaires ?",
    "Quelles sources ont été mises en service après le 1 janvier 2020 ?",
    "Dans quelles lignes injecte ParcEolien_SidiDaoud ?",
    "Quels bâtiments sont alimentés par CentraleSolaire_Tozeur ?",
    "Quelles sources alimentent Maison1 ?",
]

AIDE = ("Questions prises en charge : sources d'énergie (catégorie, puissance en kW/MW, date de mise en service), "
        "puissance totale, moyenne, maximale ; lignes dans lesquelles une source injecte ; bâtiments alimentés "
        "par une source ; sources qui alimentent un bâtiment ou injectent dans une ligne.")


def colonnes(sparql):
    """Variables projetées par le SELECT : « (EXPR AS ?x) » compte pour ?x, quelle que soit l'imbrication."""
    entete = sparql.split("SELECT", 1)[1].split("WHERE", 1)[0]
    out, profondeur, debut = [], 0, 0
    for i, ch in enumerate(entete):
        if ch == "(":
            profondeur += 1
            debut = i if profondeur == 1 else debut
        elif ch == ")":
            profondeur -= 1
            if profondeur == 0:
                out += re.findall(r"\s+AS\s+\?(\w+)\s*$", entete[debut + 1:i])
        elif profondeur == 0 and ch == "?":
            out.append(re.match(r"\?(\w+)", entete[i:]).group(1))
    return out


def repondre(question):
    a = analyser(question)
    reponse = {"analyse": a, "interpretation": None, "sparql": None, "notes": []}

    if a["intention"] == "ecriture":
        reponse["erreur"] = ("Le traducteur est en lecture seule : créez, modifiez ou supprimez les sources dans "
                             "l'onglet Sources (avec confirmation).")
        return reponse
    if a["energie"]:
        reponse["erreur"] = (f"« {a['energie'][0]} » est une énergie (kWh), pas une puissance. La puissance installée "
                             "des sources s'exprime en kW (ou MW) ; l'énergie produite provient des mesures de "
                             "production (onglet Tableau de bord, ou module Mesure).")
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

    if any(None in c["unites"] for c in a["comparaisons"]):
        reponse["notes"].append("Valeur sans unité : kW par convention.")
    if any(u in ("mw", "gw", "w") for c in a["comparaisons"] for u in c["unites"]):
        reponse["notes"].append("Unité convertie en kW (1 MW = 1 000 kW, 1 GW = 1 000 000 kW, 1 W = 0,001 kW).")
    if a["periode"] and a["periode"]["convention"]:
        reponse["notes"].append(f"Date incomplète : {a['periode']['convention']}.")
    if (a["comparaisons"] or a["periode"]) and a["cible"] == "source":
        reponse["notes"].append("Les sources dont la puissance ou la date n'est pas renseignée sont exclues des filtres.")
    if a["cible"] == "batiment" or a["entites"] and any(e["type"] == "batiment" for e in a["entites"]):
        reponse["notes"].append("Alimentation : liens directs (estAlimentePar, produitEnergiePour) et déduits "
                                "(R1, R7, R6), recalculés sur le graphe courant ; un bâtiment n'apparaît qu'une fois.")

    if est_ask:
        reponse["booleen"] = store.ask(sparql)
        reponse["colonnes"], reponse["lignes"] = [], []
        return reponse
    lignes = store.select(sparql)
    reponse["colonnes"] = colonnes(sparql)
    reponse["lignes"] = [{k: (str(v).replace(" ", "T") if k == "dateMiseEnService" and v else v)
                          for k, v in r.items()} for r in lignes]

    if a["intention"] in ("somme", "moyenne") and lignes:
        r = lignes[0]
        sans = int(r["nbSources"] or 0) - int(r["avecPuissance"] or 0)
        if sans:
            reponse["notes"].append(f"{sans} source(s) sans puissance renseignée : non comptée(s), pas assimilée(s) à 0 kW.")
    vide = not lignes or (len(lignes) == 1 and lignes[0].get("nombre") == 0) \
        or (len(lignes) == 1 and lignes[0].get("nbSources") == 0)
    if vide:
        reponse["notes"].append("Aucun résultat : aucune source de l'ontologie ne satisfait tous ces critères.")
    return reponse
