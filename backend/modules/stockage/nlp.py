"""Module NLP → SPARQL du Stockage (Membre 2 · Takoua Naceur).

Traduit une question en français en requête SPARQL exécutable, sans API de LLM.

Outils (spaCy 3 + modèle fr_core_news_sm) :
  - tokenisation, lemmatisation et étiquetage morpho-syntaxique (POS) ;
  - reconnaissance d'entités nommées (NER, étiquette LOC) pour les lieux ;
  - PhraseMatcher : relie les mots de la question aux individus de l'ontologie
    (libellés, identifiants, alias non ambigus) et au vocabulaire des classes
    (« lithium » → BatterieLithiumIon, « à recharger » → StockageCritique…) ;
  - Matcher (motifs de tokens) : repère les quantités « 500 kWh », « 20 % »,
    « entre 100 et 1000 kWh » avec leurs unités.

Étapes :
  1. analyse spaCy de la question ;
  2. liaison d'entités (PhraseMatcher) + lieux (NER + villes des postes) ;
  3. intention (lister, compter, somme, moyenne, max, min, existe) et cible
     (stockages, bâtiments, sources) ;
  4. contraintes : classes, classes définies, comparaisons numériques ;
  5. génération de la requête SPARQL (inférences OWL/SWRL réécrites), exécution RDFLib.
"""
import re
import unicodedata

from rdflib import Literal
from spacy.matcher import Matcher, PhraseMatcher
from spacy.util import filter_spans

import store
from ..reseau.nlp import nlp, normaliser  # même modèle spaCy partagé avec le module Réseau
from . import queries as Q

# ------------------------------------------------------------ vocabulaire --

CLASSES = {  # alias (normalisés) → classe OWL
    "BatterieLithiumIon": ["lithium", "lithium ion", "li ion", "batterie lithium", "batteries lithium",
                           "batterie lithium ion", "batteries lithium ion", "lfp", "nmc"],
    "BatteriePlomb": ["plomb", "batterie plomb", "batteries plomb", "plomb acide", "batterie au plomb",
                      "batteries au plomb"],
    "Batterie": ["batterie", "batteries", "accumulateur", "accumulateurs"],
    "StockageHydrogene": ["hydrogene", "h2", "stockage hydrogene", "stockages hydrogene", "electrolyse"],
    "STEP": ["step", "steps", "pompage", "station de pompage", "stations de pompage",
             "station de transfert", "pompage turbinage", "hydraulique"],
    "VolantInertie": ["volant", "volants", "volant d inertie", "volants d inertie", "inertie"],
}

DEFINIES = {  # alias → (clé de queries.DEFINIES, valeur booléenne)
    "vert": ["vert", "verts", "verte", "vertes", "renouvelable", "renouvelables", "propre", "propres",
             "energie verte", "energie renouvelable", "energies renouvelables"],
    "!vert": ["non renouvelable", "non renouvelables", "fossile", "fossiles", "pas renouvelable",
              "pas vert", "gaz"],
    "critique": ["critique", "critiques", "a recharger", "recharger", "faible charge", "presque vide",
                 "presque vides", "decharge", "decharges", "dechargee", "dechargees", "batterie faible",
                 "en alerte", "alerte"],
    "grande": ["grande capacite", "grandes capacites", "gros", "grosse", "grosses", "echelle reseau",
               "echelle du reseau", "grand stockage", "grands stockages"],
    "secours": ["secours", "de secours", "service public", "services publics", "batiment public",
                "batiments publics"],
}

CIBLES = {
    "batiment": {"batiment", "immeuble", "maison", "edifice", "consommateur", "site", "usine",
                 "hopital", "ecole"},
    "source": {"source", "centrale", "producteur", "parc", "eolienne", "panneau", "origine"},
    "stockage": {"stockage", "systeme", "batterie", "accumulateur", "step", "volant", "reservoir"},
}

ATTRIBUTS = {  # lemme → attribut
    "capacite": "capacite", "taille": "capacite",
    "charge": "niveau", "niveau": "niveau", "remplissage": "niveau", "soc": "niveau",
    "rendement": "rendement", "efficacite": "rendement",
    "puissance": "puissance",
    "annee": "annee", "installation": "annee", "date": "annee",
    "energie": "energie", "disponible": "energie",
    "autonomie": "autonomie", "duree": "autonomie",
}

UNITES = {  # unité → (attribut, facteur vers l'unité de l'ontologie)
    "kwh": ("capacite", 1), "mwh": ("capacite", 1000), "gwh": ("capacite", 1_000_000),
    "kw": ("puissance", 1), "mw": ("puissance", 1000),
    "%": ("niveau", 1), "pourcent": ("niveau", 1), "pourcents": ("niveau", 1),
    "h": ("autonomie", 1), "heure": ("autonomie", 1), "heures": ("autonomie", 1),
}

SUPERLATIFS = {  # adjectif (lemme) → (sens, attribut)
    "grand": ("max", "capacite"), "gros": ("max", "capacite"), "important": ("max", "capacite"),
    "petit": ("min", "capacite"),
    "charge": ("max", "niveau"), "plein": ("max", "niveau"), "rempli": ("max", "niveau"),
    "vide": ("min", "niveau"),
    "efficace": ("max", "rendement"), "performant": ("max", "rendement"),
    "puissant": ("max", "puissance"),
    "recent": ("max", "annee"), "nouveau": ("max", "annee"), "moderne": ("max", "annee"),
    "ancien": ("min", "annee"), "vieux": ("min", "annee"),
    "autonome": ("max", "autonomie"), "long": ("max", "autonomie"),
}

COMPARATEURS = [  # expression juste avant le nombre → opérateur
    ("au moins", ">="), ("a partir de", ">="), ("depuis", ">="), ("minimum", ">="), ("min", ">="),
    ("au plus", "<="), ("jusqu a", "<="), ("maximum", "<="), ("max", "<="),
    ("plus de", ">"), ("plus que", ">"), ("superieur a", ">"), ("superieure a", ">"),
    ("superieurs a", ">"), ("superieures a", ">"), ("au dessus de", ">"), ("depasse", ">"),
    ("depassant", ">"), ("apres", ">"), (">", ">"),
    ("moins de", "<"), ("moins que", "<"), ("inferieur a", "<"), ("inferieure a", "<"),
    ("inferieurs a", "<"), ("inferieures a", "<"), ("en dessous de", "<"), ("sous", "<"),
    ("avant", "<"), ("<", "<"),
]

VARIABLES = {"capacite": "?capacite", "niveau": "?niveau", "rendement": "?rendement",
             "puissance": "?puissance", "annee": "?annee", "energie": "?energie", "autonomie": "?autonomie"}
UNITE_AFFICHEE = {"capacite": " kWh", "niveau": " %", "rendement": " %", "puissance": " kW",
                  "annee": "", "energie": " kWh", "autonomie": " h"}


# --------------------------------------------------------- outils spaCy --

_matcher = None
_matcher_version = None
_individus = {}            # id → (type, label)
_villes = {}               # ville normalisée → [postes]
_quantites = None


INDIVIDUS = """
SELECT ?x ?type ?label ?ville WHERE {
  { ?x a/rdfs:subClassOf* sg:SystemeStockage . BIND("stockage" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:SourceEnergie . BIND("source" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:Batiment . BIND("batiment" AS ?type) }
  UNION { ?x a sg:PosteElectrique . BIND("poste" AS ?type) }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  OPTIONAL { ?x sg:ville ?ville }
}"""

_ARTICLES = r"^(le|la|les|l|du|de|des|d)\s+"


def _alias(type_, ident, label, ville):
    """Toutes les façons d'écrire un individu dans une question."""
    noms = {ident.replace("_", " ")}
    if label:
        noms.add(label)
        noms.add(re.sub(r"\s+de l\s+", " de ", normaliser(label)))   # « de l'hôpital » → « de hôpital »
    if type_ == "poste" and ville:
        noms |= {f"poste {ville}", f"poste de {ville}", f"poste d {ville}"}
    if type_ == "batiment" and label:
        noms.add(label.split(" ", 1)[-1])                            # « Hôpital Charles Nicolle » → « Charles Nicolle »
    return {normaliser(n).strip() for n in noms if n and len(n) > 2}


def _alias_courts(rows):
    """Dernier mot de l'identifiant (« Sejnane », « Gabes »…), seulement s'il est non ambigu."""
    compte = {}
    for r in rows:
        mot = normaliser(r["x"].split("_")[-1]).strip()
        compte.setdefault(mot, set()).add(r["x"])
    return {next(iter(ids)): mot for mot, ids in compte.items() if len(ids) == 1 and len(mot) > 3
            and not mot.isdigit() and mot not in {"hopital", "ecole", "maison1"}}


def _matcher_a_jour():
    """(Re)construit le PhraseMatcher quand le graphe a changé (CRUD)."""
    global _matcher, _matcher_version, _individus, _villes
    version = len(store.graph)
    if _matcher is not None and version == _matcher_version:
        return _matcher
    vocab = nlp().vocab
    _matcher = PhraseMatcher(vocab, attr="LOWER")
    _individus, _villes = {}, {}
    rows = store.select(INDIVIDUS)
    courts = _alias_courts(rows)
    vus = set()
    for r in rows:
        if r["x"] in vus:
            continue
        vus.add(r["x"])
        _individus[r["x"]] = (r["type"], r["label"] or r["x"])
        alias = _alias(r["type"], r["x"], r["label"], r["ville"])
        if r["x"] in courts:
            alias.add(courts[r["x"]])
        if r["ville"]:
            _villes.setdefault(normaliser(r["ville"]).strip(), []).append(r["x"])
        _matcher.add(f"{r['type']}|{r['x']}", [nlp().make_doc(a) for a in alias])
    for classe, alias in CLASSES.items():
        _matcher.add(f"classe|{classe}", [nlp().make_doc(a) for a in alias])
    for cle, alias in DEFINIES.items():
        _matcher.add(f"definie|{cle}", [nlp().make_doc(a) for a in alias])
    _matcher_version = version
    return _matcher


def _matcher_quantites():
    """Matcher à motifs de tokens : nombres avec unité, et intervalles « entre X et Y »."""
    global _quantites
    if _quantites is None:
        _quantites = Matcher(nlp().vocab)
        unites = list(UNITES)
        nombre = {"TEXT": {"REGEX": r"^\d+([.,]\d+)?$"}}
        _quantites.add("ENTRE", [[{"LOWER": "entre"}, nombre, {"LOWER": {"IN": unites}, "OP": "?"},
                                  {"LOWER": "et"}, nombre, {"LOWER": {"IN": unites}, "OP": "?"}]])
        _quantites.add("QUANTITE", [[nombre, {"LOWER": {"IN": unites}, "OP": "?"}]])
    return _quantites


# ---------------------------------------------------------------- analyse --

def _spans(texte_norm):
    """Entités et mots-clés reconnus par le PhraseMatcher (le plus long gagne)."""
    doc = nlp().make_doc(texte_norm)
    spans = []
    for match_id, start, end in _matcher_a_jour()(doc):
        type_, ident = nlp().vocab.strings[match_id].split("|", 1)
        span = doc[start:end]
        span.label_, span.kb_id_ = type_, ident
        spans.append(span)
    return doc, filter_spans(spans)


def _nombre(texte):
    return float(texte.replace(",", "."))


def _quantites_dans(doc, spans, texte_reste):
    """Comparaisons numériques : (attribut, opérateur, valeur[s])."""
    pris = {i for s in spans for i in range(s.start, s.end)}
    matches = filter_spans([doc[s:e] for _, s, e in _matcher_quantites()(doc)])
    attribut_cite = next((a for mot, a in ATTRIBUTS.items() if re.search(rf"\b{mot}\b", texte_reste)), None)
    out = []
    for span in sorted(matches, key=lambda s: s.start):
        if any(i in pris for i in range(span.start, span.end)):
            continue  # nombre qui fait partie d'un nom (« Maison1 »)
        toks = [t.text for t in span]
        unite = next((t.lower() for t in toks if t.lower() in UNITES), None)
        nombres = [_nombre(t) for t in toks if re.fullmatch(r"\d+([.,]\d+)?", t)]
        if unite:
            attribut, facteur = UNITES[unite]
            if unite == "%" and attribut_cite == "rendement":
                attribut = "rendement"
            if attribut == "capacite" and attribut_cite == "energie":
                attribut = "energie"
        elif len(nombres) == 1 and 1900 <= nombres[0] <= 2100:
            attribut, facteur = "annee", 1
        else:
            attribut, facteur = attribut_cite or "capacite", 1
        nombres = [n * facteur for n in nombres]
        if len(nombres) == 2:
            out.append({"attribut": attribut, "op": "entre", "min": min(nombres), "max": max(nombres)})
            continue
        avant = " ".join(t.text for t in doc[max(0, span.start - 4):span.start])
        op = next((sym for expr, sym in COMPARATEURS if re.search(rf"(^|\s){re.escape(expr)}$", avant)), None)
        if op is None:
            op = next((sym for expr, sym in COMPARATEURS if re.search(rf"(^|\s){re.escape(expr)}(\s|$)", avant)), "=")
        out.append({"attribut": attribut, "op": op, "valeur": nombres[0]})
    return out


def _racines(mot, lemme):
    """Formes candidates d'un adjectif : « chargées » → chargees, charger, chargee, charge…"""
    out = [lemme, mot]
    for fin in ("ees", "ee", "es", "s", "e"):
        if mot.endswith(fin) and len(mot) - len(fin) > 2:
            out.append(mot[: -len(fin)])
    return out


def analyser(question):
    texte = unicodedata.normalize("NFC", re.sub(r"\s+", " ", question)).strip()
    doc = nlp()(texte)                       # pipeline complet : lemmes, POS, NER
    norm = normaliser(texte)
    ndoc, spans = _spans(norm)

    entites = [{"texte": s.text, "type": s.label_, "id": s.kb_id_, "label": _individus[s.kb_id_][1]}
               for s in spans if s.label_ in ("stockage", "source", "batiment", "poste")]
    classes = [s.kb_id_ for s in spans if s.label_ == "classe"]
    definies = {}
    for s in spans:
        if s.label_ == "definie":
            cle = s.kb_id_.lstrip("!")
            definies[cle] = not s.kb_id_.startswith("!")

    # mots qui ne font partie d'aucune entité reconnue (positions sur le texte normalisé)
    pris = [(s.start_char, s.end_char) for s in spans]
    reste = [t for t in doc if not any(a <= t.idx < b for a, b in pris)]
    lemmes = [normaliser(t.lemma_ or t.text).strip() for t in reste]
    mots = [normaliser(t.text).strip() for t in reste]
    texte_reste = " ".join(mots)

    # lieux : entités LOC de spaCy (noms propres) ou villes connues des postes,
    # quand elles ne sont pas déjà reliées à un individu par le PhraseMatcher
    lieux = []
    for e in doc.ents:
        n = normaliser(e.text).strip()
        if (e.label_ == "LOC" and e.text[:1].isupper() and not any(t.is_stop for t in e)
                and not any(a <= e.start_char < b for a, b in pris)):
            lieux.append({"texte": e.text, "norm": n, "postes": _villes.get(n, []), "source": "NER"})
    for ville, postes in _villes.items():
        if re.search(rf"\b{re.escape(ville)}\b", texte_reste) and all(l["norm"] != ville for l in lieux):
            lieux.append({"texte": ville, "norm": ville, "postes": postes, "source": "ville"})

    # cible : premier nom de classe rencontré (stockage par défaut)
    cible = None
    for l in lemmes:
        cible = next((c for c, syn in CIBLES.items() if l in syn or l.rstrip("sx") in syn), None)
        if cible:
            break
    if re.search(r"\bautonome", texte_reste) and cible != "stockage":
        cible = "batiment"
    if cible == "source" and not entites and not re.search(r"\b(stocke|stockee|stockees|stockent)\b", texte_reste):
        cible = "stockage"   # « stockages de source renouvelable » parle encore des stockages
    if cible is None:
        cible = "stockage"

    # intention
    intention = "lister"
    if re.match(r"^(est ce qu|existe|y a t il|il y a t il)", texte_reste) or "existe t il" in texte_reste:
        intention = "existe"
    if "combien" in mots or "nombre" in lemmes:
        intention = "compter"
    elif re.search(r"\b(total|totale|somme|cumul|cumulee|ensemble)\b", texte_reste):
        intention = "somme"
    elif re.search(r"\b(moyen|moyenne|en moyenne)\b", texte_reste):
        intention = "moyenne"

    attribut = next((ATTRIBUTS[l] for l in lemmes if l in ATTRIBUTS), None)

    if intention in ("lister", "existe"):
        for i, m in enumerate(mots[:-1]):
            if m in ("plus", "moins"):
                adj = next((r for r in _racines(mots[i + 1], lemmes[i + 1]) if r in SUPERLATIFS), None)
                if adj:
                    sens, attr = SUPERLATIFS[adj]
                    if m == "moins":
                        sens = "min" if sens == "max" else "max"
                    intention, attribut = sens, attribut or attr
                    break
        if intention == "lister" and re.search(r"\b(meilleur|maximal|maximale|maximum)\b", texte_reste) \
                and not re.search(r"\bau maximum\b", texte_reste):
            intention = "max"
        elif intention == "lister" and re.search(r"\b(pire|minimal|minimale|minimum)\b", texte_reste) \
                and not re.search(r"\bau minimum\b", texte_reste):
            intention = "min"
    if intention in ("max", "min", "somme", "moyenne") and attribut is None:
        attribut = {"somme": "capacite", "moyenne": "niveau"}.get(intention, "capacite")

    comparaisons = _quantites_dans(ndoc, spans, texte_reste)

    return {
        "question": texte,
        "tokens": [{"texte": t.text, "lemme": t.lemma_ or t.text, "pos": t.pos_} for t in doc],
        "ner": [{"texte": e.text, "label": e.label_} for e in doc.ents],
        "entites": entites,
        "classes": classes,
        "definies": definies,
        "lieux": lieux,
        "intention": intention,
        "cible": cible,
        "attribut": attribut,
        "comparaisons": comparaisons,
    }


# ------------------------------------------------------- génération SPARQL --

def _filtre(c):
    var = VARIABLES[c["attribut"]]
    if c["op"] == "entre":
        return f"FILTER({var} >= {c['min']} && {var} <= {c['max']})"
    return f"FILTER({var} {c['op']} {c['valeur']})"


def _lieu(var, lieu):
    """Lieu repéré : stockages raccordés aux postes de cette ville, sinon libellé qui la contient."""
    if lieu["postes"]:
        alts = " ".join(store.iri(p).n3() for p in lieu["postes"])
        return (f"# lieu « {lieu['texte']} » ({lieu['source']}) → postes de la ville\n"
                f"  {var} sg:raccordeAuPoste ?pl . VALUES ?pl {{ {alts} }}")
    texte = Literal(lieu["texte"].lower()).n3()
    return (f"# lieu « {lieu['texte']} » (NER spaCy)\n"
            f"  FILTER(CONTAINS(LCASE(STR(?label)), {texte}))")


def _corps_stockage(a):
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    m = ["?x a/rdfs:subClassOf* sg:SystemeStockage ; a ?classe .",
         "?classe rdfs:subClassOf* sg:SystemeStockage .",
         "FILTER NOT EXISTS { ?x a ?autre . ?autre rdfs:subClassOf+ ?classe . FILTER(?autre != ?classe) }",
         "OPTIONAL { ?x rdfs:label ?label }",
         "OPTIONAL { ?x sg:capaciteStockage ?capacite }",
         "OPTIONAL { ?x sg:niveauCharge ?niveau }",
         "OPTIONAL { ?x sg:rendement ?rendement }",
         "OPTIONAL { ?x sg:puissanceDecharge ?puissance }",
         "OPTIONAL { ?x sg:anneeInstallation ?annee }"]
    if a["classes"]:
        alts = " ".join(f"sg:{c}" for c in dict.fromkeys(a["classes"]))
        m.append(f"?x a/rdfs:subClassOf* ?cl . VALUES ?cl {{ {alts} }}")
    m.append(Q.INFERENCES.strip())
    for cle, valeur in a["definies"].items():
        m.append(f"FILTER({'' if valeur else '!'}?{cle})  # classe définie sg:{Q.DEFINIES[cle]}"
                 + ("" if valeur else " (négation)"))
    for e in a["entites"]:
        if e["type"] == "stockage":
            m.append(f"FILTER(?x = {sg(e['id'])})")
        elif e["type"] == "source":
            m.append(f"?x sg:stockeEnergieDe {sg(e['id'])} .")
        elif e["type"] == "batiment":
            m.append(f"?x sg:alimente {sg(e['id'])} .   # R2 : le bâtiment possède ce stockage")
        elif e["type"] == "poste":
            m.append(f"?x sg:raccordeAuPoste {sg(e['id'])} .")
    for lieu in a["lieux"]:
        m.append(_lieu("?x", lieu))
    return m, "?x", ["?x", "?label", "?classe", "?capacite", "?niveau", "?rendement", "?puissance",
                     "?annee", "?energie", "?autonomie"]


def _corps_batiment(a):
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    m = ["?b a/rdfs:subClassOf* sg:Batiment ; a owl:NamedIndividual .",
         "OPTIONAL { ?b rdfs:label ?label }",
         "OPTIONAL { ?b sg:consommationAnnuelle ?consommation }",
         "# R2 : SystemeStockage(?x) ∧ alimente(?x, ?b) → possedeStockage(?b, ?x)",
         "{ ?x sg:alimente ?b } UNION { ?b sg:possedeStockage ?x }",
         "OPTIONAL { ?x sg:capaciteStockage ?capacite }",
         "OPTIONAL { ?x sg:niveauCharge ?niveau }"]
    if re.search(r"autonome", a["question"].lower()):
        m.append("# BatimentAutonome ≡ Batiment ⊓ estAlimentePar some SourceRenouvelable ⊓ possedeStockage some SystemeStockage\n"
                 "  FILTER EXISTS {\n"
                 "    { ?b sg:estAlimentePar ?s } UNION { ?s sg:produitEnergiePour ?b }\n"
                 "    UNION { ?s sg:injecteDans ?l . ?l sg:transporteVers ?b }        # R1\n"
                 "    UNION { ?xs sg:alimente ?b ; sg:stockeEnergieDe ?s }             # R6\n"
                 "    ?s a/rdfs:subClassOf* sg:SourceRenouvelable\n"
                 "  }")
    if a["classes"]:
        alts = " ".join(f"sg:{c}" for c in dict.fromkeys(a["classes"]))
        m.append(f"?x a/rdfs:subClassOf* ?cl . VALUES ?cl {{ {alts} }}")
    if a["definies"].get("critique"):
        m.append(f"FILTER(?niveau < {Q.SEUIL_CRITIQUE})  # StockageCritique")
    for e in a["entites"]:
        if e["type"] == "stockage":
            m.append(f"FILTER(?x = {sg(e['id'])})")
        elif e["type"] == "batiment":
            m.append(f"FILTER(?b = {sg(e['id'])})")
        elif e["type"] == "source":
            m.append(f"?x sg:stockeEnergieDe {sg(e['id'])} .")
        elif e["type"] == "poste":
            m.append(f"# R3 : le bâtiment est desservi par ce poste\n"
                     f"  {{ ?b sg:estRaccordeA ?lp . ?lp sg:relie {sg(e['id'])} }} "
                     f"UNION {{ ?lp sg:transporteVers ?b . ?lp sg:relie {sg(e['id'])} }}")
    return m, "?b", ["?b", "?label", "?consommation", "?x", "?capacite", "?niveau"]


def _corps_source(a):
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    m = ["?s a/rdfs:subClassOf* sg:SourceEnergie ; a ?classe .",
         "?classe rdfs:subClassOf* sg:SourceEnergie .",
         "FILTER NOT EXISTS { ?s a ?autre . ?autre rdfs:subClassOf+ ?classe . FILTER(?autre != ?classe) }",
         "OPTIONAL { ?s rdfs:label ?label }",
         "# estStockePar est l'inverse de stockeEnergieDe",
         "{ ?x sg:stockeEnergieDe ?s } UNION { ?s sg:estStockePar ?x }"]
    if a["classes"]:
        alts = " ".join(f"sg:{c}" for c in dict.fromkeys(a["classes"]))
        m.append(f"?x a/rdfs:subClassOf* ?cl . VALUES ?cl {{ {alts} }}")
    if "vert" in a["definies"]:
        neg = "" if a["definies"]["vert"] else "!"
        m.append(f"FILTER({neg}EXISTS {{ ?s a/rdfs:subClassOf* sg:SourceRenouvelable }})")
    for e in a["entites"]:
        if e["type"] == "stockage":
            m.append(f"FILTER(?x = {sg(e['id'])})")
        elif e["type"] == "source":
            m.append(f"FILTER(?s = {sg(e['id'])})")
        elif e["type"] == "batiment":
            m.append(f"?x sg:alimente {sg(e['id'])} .")
    return m, "?s", ["?s", "?label", "?classe", "?x"]


def generer(a):
    """Construit la requête SPARQL à partir de l'analyse. Renvoie (sparql, est_ask)."""
    corps_de = {"stockage": _corps_stockage, "batiment": _corps_batiment, "source": _corps_source}
    motifs, var, colonnes = corps_de[a["cible"]](a)
    for c in a["comparaisons"]:
        if re.search(rf"\{VARIABLES[c['attribut']]}\b", "\n".join(motifs)):
            motifs.append(_filtre(c))

    corps = "\n  ".join(motifs)
    intention = a["intention"]
    attr_var = VARIABLES.get(a["attribut"] or "")
    if attr_var not in colonnes:
        attr_var = None

    if intention == "existe":
        return f"ASK {{\n  {corps}\n}}", True
    if intention == "compter":
        return f"SELECT (COUNT(DISTINCT {var}) AS ?nombre) WHERE {{\n  {corps}\n}}", False
    if intention in ("somme", "moyenne") and attr_var:
        fn, alias = ("SUM", "?total") if intention == "somme" else ("AVG", "?moyenne")
        # sous-requête DISTINCT : chaque individu n'est compté qu'une fois
        return (f"SELECT ({fn}({attr_var}) AS {alias}) (COUNT({var}) AS ?nombre) WHERE {{\n"
                f"  {{ SELECT DISTINCT {var} {attr_var} WHERE {{\n  {corps}\n  FILTER(BOUND({attr_var}))\n  }} }}\n}}"), False
    select = "SELECT DISTINCT " + " ".join(colonnes)
    if intention in ("max", "min") and attr_var:
        ordre = f"DESC({attr_var})" if intention == "max" else f"ASC({attr_var})"
        return f"{select} WHERE {{\n  {corps}\n  FILTER(BOUND({attr_var}))\n}}\nORDER BY {ordre}\nLIMIT 1", False
    ordre = "DESC(?capacite)" if "?capacite" in colonnes else "?label"
    return f"{select} WHERE {{\n  {corps}\n}}\nORDER BY {ordre}", False


# ------------------------------------------------------------ restitution --

NOMS_CIBLES = {"stockage": "systèmes de stockage", "batiment": "bâtiments", "source": "sources stockées"}
NOMS_INTENTIONS = {"lister": "Lister", "compter": "Compter", "max": "Maximum", "min": "Minimum",
                   "somme": "Somme", "moyenne": "Moyenne", "existe": "Existe-t-il"}
SYMBOLES = {">": ">", ">=": "≥", "<": "<", "<=": "≤", "=": "="}


def _fmt(x):
    return str(int(x)) if float(x).is_integer() else str(x)


def interpretation(a):
    morceaux = [f"{NOMS_INTENTIONS[a['intention']]} · {NOMS_CIBLES[a['cible']]}"]
    if a["attribut"] and a["intention"] in ("max", "min", "somme", "moyenne"):
        morceaux.append(f"sur {a['attribut']}")
    for c in dict.fromkeys(a["classes"]):
        morceaux.append(f"classe {c}")
    for cle, v in a["definies"].items():
        morceaux.append(f"{'' if v else 'non '}{Q.DEFINIES[cle]}")
    if a["cible"] == "batiment" and "autonome" in a["question"].lower():
        morceaux.append("BatimentAutonome")
    for e in a["entites"]:
        morceaux.append(f"{e['type']} = sg:{e['id']}")
    for l in a["lieux"]:
        morceaux.append(f"lieu « {l['texte']} »")
    for c in a["comparaisons"]:
        u = UNITE_AFFICHEE[c["attribut"]]
        if c["op"] == "entre":
            morceaux.append(f"{c['attribut']} entre {_fmt(c['min'])} et {_fmt(c['max'])}{u}")
        else:
            morceaux.append(f"{c['attribut']} {SYMBOLES[c['op']]} {_fmt(c['valeur'])}{u}")
    return " · ".join(morceaux)


EXEMPLES = [
    "Quels sont les stockages critiques à recharger ?",
    "Combien de batteries lithium-ion y a-t-il ?",
    "Quelle est la capacité totale des stockages verts ?",
    "Stockages de plus de 10 MWh",
    "Quel stockage a le meilleur rendement ?",
    "Batteries chargées à moins de 50 %",
    "Quels bâtiments sont autonomes ?",
    "Quelles sources sont stockées par la STEP de Sejnane ?",
    "Stockages non renouvelables raccordés au poste de Radès",
    "Batteries installées après 2020 entre 100 et 1000 kWh",
    "Existe-t-il un stockage hydrogène à Gabès ?",
    "Charge moyenne des batteries de secours",
]


def repondre(question):
    a = analyser(question)
    sparql, est_ask = generer(a)
    reponse = {"analyse": a, "interpretation": interpretation(a), "sparql": sparql}
    if est_ask:
        reponse["booleen"] = store.ask(sparql)
        reponse["colonnes"], reponse["lignes"] = [], []
        return reponse
    lignes = store.select(sparql)
    entete = sparql.split("WHERE")[0]
    reponse["colonnes"] = (re.findall(r"AS \?(\w+)", entete) if " AS ?" in entete
                           else re.findall(r"\?(\w+)", entete))
    reponse["lignes"] = lignes
    return reponse
