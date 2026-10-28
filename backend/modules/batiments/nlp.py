"""Module NLP → SPARQL des Bâtiments (Membre 3 · Abir Mosrati).

Traduit une question en français en requête SPARQL exécutable, sans API de LLM.

Outils (spaCy 3 + modèle fr_core_news_sm) :
  - tokenisation, lemmatisation et étiquetage morpho-syntaxique (POS) ;
  - reconnaissance d'entités nommées (NER, étiquette LOC) pour les lieux ;
  - PhraseMatcher : relie les mots de la question aux individus de l'ontologie
    (libellés, identifiants, alias non ambigus) et au vocabulaire des classes
    (« usine » → BatimentIndustriel, « énergivore » → GrosConsommateur,
    « sans batterie » → ¬ possedeStockage…) ;
  - Matcher (motifs de tokens) : quantités avec unités et conversion
    (« 2 GWh » → 2 000 000 kWh, « 500 m² », « 200 kWh/m² », « 1 MW »),
    intervalles « entre 1000 et 5000 m² ».

Étapes :
  1. analyse spaCy de la question ;
  2. liaison d'entités (PhraseMatcher) + lieux (NER + villes des postes) ;
  3. intention (lister, compter, somme, moyenne, max, min, existe) et cible
     (bâtiments, sources qui les alimentent, postes qui les desservent) ;
  4. contraintes : types, classes définies, classe DPE, comparaisons numériques ;
  5. génération de la requête SPARQL (inférences OWL/SWRL réécrites), exécution RDFLib.
"""
import re
import unicodedata

from rdflib import Literal
from spacy.matcher import Matcher, PhraseMatcher
from spacy.util import filter_spans

import store
from ..reseau.nlp import nlp, normaliser  # même modèle spaCy partagé avec les autres modules
from . import queries as Q

# ------------------------------------------------------------ vocabulaire --

CLASSES = {  # alias (normalisés) → classe OWL
    "BatimentResidentiel": ["residentiel", "residentiels", "residentielle", "residentielles", "logement",
                            "logements", "habitation", "habitations", "maison", "maisons", "villa", "villas",
                            "immeuble", "immeubles", "appartement", "appartements", "domestique", "domestiques"],
    "BatimentIndustriel": ["industriel", "industriels", "industrielle", "industrielles", "usine", "usines",
                           "industrie", "industries", "site industriel", "sites industriels", "cimenterie",
                           "cimenteries", "fabrique", "fabriques"],
    "BatimentPublic": ["public", "publics", "publique", "publiques", "hopital", "hopitaux", "ecole", "ecoles",
                       "mairie", "mairies", "administration", "administrations", "service public",
                       "services publics", "lycee", "lycees", "college", "colleges", "universite", "clinique"],
    "BatimentCommercial": ["commercial", "commerciaux", "commerciale", "commerciales", "commerce", "commerces",
                           "centre commercial", "centres commerciaux", "magasin", "magasins", "bureau",
                           "bureaux", "hotel", "hotels", "boutique", "boutiques", "tertiaire"],
}

DEFINIES = {  # alias → clé (préfixe « ! » = négation)
    "vert": ["vert", "verts", "verte", "vertes", "renouvelable", "renouvelables", "ecologique", "ecologiques",
             "propre", "propres", "energie verte", "energie renouvelable", "energies renouvelables"],
    "!vert": ["non renouvelable", "non renouvelables", "fossile", "fossiles", "pas vert", "pas verts",
              "pas renouvelable", "non vert", "non verts"],
    "autonome": ["autonome", "autonomes", "autosuffisant", "autosuffisants", "auto suffisant",
                 "auto suffisants", "independant", "independants", "independante", "independantes"],
    "!autonome": ["non autonome", "non autonomes", "pas autonome", "pas autonomes", "dependant", "dependants"],
    "gros": ["gros consommateur", "gros consommateurs", "grand consommateur", "grands consommateurs",
             "grosse consommatrice", "energivore", "energivores", "gourmand", "gourmands", "gourmande",
             "gourmandes"],
    "!gros": ["petit consommateur", "petits consommateurs", "faible consommation", "faibles consommateurs",
              "peu energivore", "peu energivores"],
    "intelligent": ["intelligent", "intelligents", "intelligente", "intelligentes", "connecte", "connectes",
                    "connectee", "connectees", "smart", "compteur intelligent", "compteurs intelligents",
                    "avec compteur", "avec un compteur", "equipe d un compteur", "equipes d un compteur",
                    "equipes de compteurs"],
    "!intelligent": ["sans compteur", "sans compteurs", "non connecte", "non connectes"],
    "ht": ["haute tension", "ht", "tres haute tension", "en haute tension"],
    "stockage": ["avec stockage", "avec un stockage", "avec batterie", "avec une batterie", "avec batteries",
                 "possede un stockage", "possedant un stockage", "possedent un stockage", "ayant un stockage",
                 "ayant une batterie", "equipe d une batterie", "equipes d une batterie", "avec du stockage"],
    "!stockage": ["sans stockage", "sans batterie", "sans batteries", "sans systeme de stockage"],
}

CIBLES = {
    "source": {"source", "centrale", "producteur", "parc", "eolienne", "panneau", "origine", "fournisseur"},
    "poste": {"poste", "station", "sous station"},
    "batiment": {"batiment", "immeuble", "edifice", "consommateur", "site", "construction", "local",
                 "maison", "usine", "hopital", "ecole", "mairie", "villa", "centre", "logement"},
}

ATTRIBUTS = {  # mot ou lemme → attribut
    "consommation": "consommation", "conso": "consommation", "consommer": "consommation",
    "consomme": "consommation", "consomment": "consommation", "energie": "consommation",
    "surface": "surface", "surfacer": "surface", "superficie": "surface", "taille": "surface",
    "occupant": "occupants", "occupants": "occupants", "habitant": "occupants", "habitants": "occupants",
    "personne": "occupants", "personnes": "occupants",
    "annee": "annee", "construction": "annee", "construit": "annee", "construire": "annee", "age": "annee",
    "puissance": "puissance", "souscrit": "puissance", "souscrite": "puissance",
    "intensite": "intensite", "performance": "intensite",
}

UNITES = {  # unité → (attribut, facteur vers l'unité de l'ontologie)
    "kwh": ("consommation", 1), "mwh": ("consommation", 1000), "gwh": ("consommation", 1_000_000),
    "kwhpm2": ("intensite", 1), "kwhpm²": ("intensite", 1),
    "m2": ("surface", 1), "m²": ("surface", 1),
    "kw": ("puissance", 1), "kva": ("puissance", 1), "mw": ("puissance", 1000),
    "occupants": ("occupants", 1), "habitants": ("occupants", 1), "personnes": ("occupants", 1),
}

SUPERLATIFS = {  # adjectif (racine) → (sens, attribut)
    "grand": ("max", "surface"), "vaste": ("max", "surface"), "spacieux": ("max", "surface"),
    "petit": ("min", "surface"),
    "ancien": ("min", "annee"), "vieux": ("min", "annee"), "vieil": ("min", "annee"),
    "recent": ("max", "annee"), "nouveau": ("max", "annee"), "moderne": ("max", "annee"),
    "jeune": ("max", "annee"),
    "energivore": ("max", "consommation"), "gourmand": ("max", "consommation"),
    "consommateur": ("max", "consommation"),
    "econome": ("min", "intensite"), "sobre": ("min", "intensite"), "efficace": ("min", "intensite"),
    "performant": ("min", "intensite"),
    "peuple": ("max", "occupants"), "frequente": ("max", "occupants"),
    "puissant": ("max", "puissance"),
}

COMPARATEURS = [  # expression juste avant le nombre → opérateur
    ("au moins", ">="), ("a partir de", ">="), ("depuis", ">="), ("minimum", ">="), ("min", ">="),
    ("au plus", "<="), ("jusqu a", "<="), ("maximum", "<="), ("max", "<="),
    ("plus de", ">"), ("plus que", ">"), ("superieur a", ">"), ("superieure a", ">"),
    ("superieurs a", ">"), ("superieures a", ">"), ("au dessus de", ">"), ("depasse", ">"),
    ("depassant", ">"), ("depassent", ">"), ("apres", ">"), (">", ">"),
    ("moins de", "<"), ("moins que", "<"), ("inferieur a", "<"), ("inferieure a", "<"),
    ("inferieurs a", "<"), ("inferieures a", "<"), ("en dessous de", "<"), ("sous", "<"),
    ("avant", "<"), ("<", "<"),
]

VARIABLES = {"consommation": "?conso", "surface": "?surface", "occupants": "?occupants",
             "annee": "?annee", "puissance": "?puissance", "intensite": "?intensite"}
UNITE_AFFICHEE = {"consommation": " kWh", "surface": " m²", "occupants": "", "annee": "",
                  "puissance": " kW", "intensite": " kWh/m²"}

# Les classes définies, réécrites en FILTER SPARQL (une entrée par clé)
CONDITIONS = {
    "vert": f"EXISTS {{ {Q.CHEMINS_SOURCES.strip()}\n    ?s a/rdfs:subClassOf* sg:SourceRenouvelable }}",
    "stockage": "EXISTS { { ?xa sg:alimente ?b } UNION { ?b sg:possedeStockage ?xa } }",
    "gros": f"(BOUND(?conso) && ?conso >= {Q.SEUIL_GROS})",
    "intelligent": "EXISTS { { ?b sg:equipeDe ?ci } UNION { ?ci sg:installeDans ?b } }",
    "ht": f"EXISTS {{ ?b sg:estRaccordeA ?lh . ?lh sg:tension ?th . FILTER(?th >= {Q.SEUIL_HT}) }}",
}
COMMENTAIRES = {
    "vert": "BatimentVert ≡ Batiment ⊓ estAlimentePar some SourceRenouvelable (direct, inverse, R1, R6, R7)",
    "autonome": "BatimentAutonome ≡ BatimentVert ⊓ possedeStockage some SystemeStockage (R2)",
    "stockage": "possedeStockage some SystemeStockage (R2)",
    "gros": f"GrosConsommateur ≡ Batiment ⊓ consommationAnnuelle some float[≥ {Q.SEUIL_GROS}]",
    "intelligent": "BatimentIntelligent ≡ Batiment ⊓ equipeDe some CompteurIntelligent",
    "ht": "BatimentRaccordeHT ≡ Batiment ⊓ estRaccordeA some LigneHauteTension",
}
NOMS_DEFINIES = {**Q.DEFINIES, "stockage": "possedeStockage"}


# --------------------------------------------------------- outils spaCy --

_matcher = None
_matcher_version = None
_individus = {}            # id → (type, label)
_villes = {}               # ville normalisée → (ville, [postes])
_quantites = None

INDIVIDUS = """
SELECT ?x ?type ?label ?ville WHERE {
  { ?x a/rdfs:subClassOf* sg:Batiment . BIND("batiment" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:SourceEnergie . BIND("source" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:LigneElectrique . BIND("ligne" AS ?type) }
  UNION { ?x a sg:PosteElectrique . BIND("poste" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:SystemeStockage . BIND("stockage" AS ?type) }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  OPTIONAL { ?x sg:ville ?ville }
}"""


def _norm(texte):
    return re.sub(r"\s+", " ", normaliser(texte)).strip()


def _alias(type_, ident, label, ville):
    """(alias sûrs, alias dérivés) d'un individu ; les dérivés ne sont gardés que s'ils sont non ambigus."""
    surs = {ident.replace("_", " "), ident}
    derives = set()
    if label:
        surs.add(label)
        surs.add(re.sub(r"\s+de l\s+", " de ", normaliser(label)))   # « de l'école » → « de école »
        reste = re.split(r"\s(?:de|des|du|d')\s?", label, maxsplit=1)
        if len(reste) == 2:
            derives.add(reste[1])                                     # « Parc éolien de Sidi Daoud » → « Sidi Daoud »
        if type_ == "batiment":
            derives.add(label.split(" ", 1)[-1])                      # « Hôpital Charles Nicolle » → « Charles Nicolle »
    if type_ == "poste" and ville:
        surs |= {f"poste {ville}", f"poste de {ville}", f"poste d {ville}"}
    derives.add(ident.split("_")[-1])                                 # dernier mot de l'identifiant
    derives = {re.sub(r"^((l|la|le|les|du|de|des|d)\s+)+", "", _norm(a)) for a in derives if a}
    return ({_norm(a) for a in surs if a and len(a) > 2},
            {a for a in derives if len(a) > 3 and not a.isdigit()})


def _matcher_a_jour():
    """(Re)construit le PhraseMatcher quand le graphe a changé (CRUD)."""
    global _matcher, _matcher_version, _individus, _villes
    version = len(store.graph)
    if _matcher is not None and version == _matcher_version:
        return _matcher
    rows, vus = [], set()
    for r in store.select(INDIVIDUS):
        if r["x"] not in vus:
            vus.add(r["x"])
            rows.append(r)
    _individus = {r["x"]: (r["type"], r["label"] or r["x"]) for r in rows}
    _villes = {}
    for r in rows:
        if r["ville"]:
            _villes.setdefault(_norm(r["ville"]), (r["ville"], []))[1].append(r["x"])
    mots_vocabulaire = {a for alias in list(CLASSES.values()) + list(DEFINIES.values()) for a in alias}

    alias_par_individu, compte = {}, {}
    for r in rows:
        surs, derives = _alias(r["type"], r["x"], r["label"], r["ville"])
        alias_par_individu[r["x"]] = (surs, derives)
        for a in surs | derives:
            compte.setdefault(a, set()).add(r["x"])

    _matcher = PhraseMatcher(nlp().vocab, attr="LOWER")
    for r in rows:
        surs, derives = alias_par_individu[r["x"]]
        garde = surs | {a for a in derives if len(compte[a]) == 1 and a not in _villes
                        and a not in mots_vocabulaire}
        _matcher.add(f"{r['type']}|{r['x']}", [nlp().make_doc(a) for a in garde])
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
        elif len(nombres) == 1 and 1800 <= nombres[0] <= 2100 and attribut_cite in (None, "annee"):
            attribut, facteur = "annee", 1
        else:
            attribut, facteur = attribut_cite or "consommation", 1
        nombres = [n * facteur for n in nombres]
        if len(nombres) == 2:
            out.append({"attribut": attribut, "op": "entre", "min": min(nombres), "max": max(nombres)})
            continue
        avant = " ".join(t.text for t in doc[max(0, span.start - 4):span.start])
        op = next((sym for expr, sym in COMPARATEURS if re.search(rf"(^|\s){re.escape(expr)}$", avant)), None)
        if op is None:
            op = next((sym for expr, sym in COMPARATEURS if re.search(rf"(^|\s){re.escape(expr)}(\s|$)", avant)), "=")
        apres = " ".join(t.text for t in doc[span.end:span.end + 2])
        if op == "=" and re.match(r"^(ou|et) (plus|davantage)", apres):
            op = ">="                                                 # « 1 GWh ou plus »
        elif op == "=" and re.match(r"^(ou|et) moins", apres):
            op = "<="
        out.append({"attribut": attribut, "op": op, "valeur": nombres[0]})
    return out


def _racines(mot, lemme):
    """Formes candidates d'un adjectif : « anciennes » → anciennes, ancienne, ancien…"""
    out = [lemme, mot]
    for fin in ("nes", "ne", "ees", "ee", "es", "s", "e", "x"):
        if mot.endswith(fin) and len(mot) - len(fin) > 2:
            out.append(mot[: -len(fin)])
    return out


def _classe_dpe(norm):
    """« classe énergétique C », « DPE D ou pire », « étiquette B ou mieux »."""
    m = re.search(r"\b(?:classe|dpe|etiquette)(?: energetique)?(?: dpe)? ([a-g])\b(?: (ou mieux|ou plus|ou moins bien|ou pire))?", norm)
    if not m:
        return None
    lettre, suite = m.group(1).upper(), m.group(2)
    op = "<=" if suite in ("ou mieux", "ou plus") else ">=" if suite in ("ou moins bien", "ou pire") else "="
    return {"lettre": lettre, "op": op, "debut": m.start(), "fin": m.end()}


def analyser(question):
    texte = unicodedata.normalize("NFC", re.sub(r"\s+", " ", question)).strip()
    texte = re.sub(r"(?<=\d)[   ](?=\d{3}(?!\d))", "", texte)       # « 1 000 000 » → « 1000000 »
    doc = nlp()(texte)                       # pipeline complet : lemmes, POS, NER
    norm = normaliser(texte)
    norm = norm.replace("kwh/m2", "kwhpm2").replace("kwh/m²", "kwhpm²")       # même longueur
    dpe = _classe_dpe(norm)
    if dpe:  # « classe a » ne doit pas être lu comme un mot du vocabulaire
        norm = norm[:dpe["debut"]] + " " * (dpe["fin"] - dpe["debut"]) + norm[dpe["fin"]:]
    ndoc, spans = _spans(norm)

    entites = [{"texte": s.text, "type": s.label_, "id": s.kb_id_, "label": _individus[s.kb_id_][1]}
               for s in spans if s.label_ in ("batiment", "source", "ligne", "poste", "stockage")]
    classes = list(dict.fromkeys(s.kb_id_ for s in spans if s.label_ == "classe"))
    definies = {}
    for s in spans:
        if s.label_ == "definie":
            definies[s.kb_id_.lstrip("!")] = not s.kb_id_.startswith("!")

    # mots qui ne font partie d'aucune entité reconnue (positions sur le texte normalisé)
    pris = [(s.start_char, s.end_char) for s in spans]
    if dpe:
        pris.append((dpe["debut"], dpe["fin"]))
    reste = [t for t in doc if not any(a <= t.idx < b for a, b in pris)]
    lemmes = [normaliser(t.lemma_ or t.text).strip() for t in reste]
    mots = [normaliser(t.text).strip() for t in reste]
    texte_reste = " ".join(mots)

    # lieux : entités LOC de spaCy ou villes connues des postes, non déjà reliées à un individu
    lieux = []
    for e in doc.ents:
        n = _norm(e.text)
        precede = _norm(doc[e.start - 1].text) if e.start > 0 else ""
        if (e.label_ == "LOC" and e.text[:1].isupper() and not any(t.is_stop for t in e)
                and not any(a <= e.start_char < b for a, b in pris)
                and precede in ("a", "de", "d", "en", "dans", "sur", "pres", "vers")   # « à Hammamet »
                and n not in ATTRIBUTS and n.rstrip("s") not in CIBLES["batiment"]):
            ville, postes = _villes.get(n, (e.text, []))
            lieux.append({"texte": ville, "norm": n, "postes": postes, "source": "NER"})
    for n, (ville, postes) in _villes.items():
        if re.search(rf"\b{re.escape(n)}\b", texte_reste) and all(l["norm"] != n for l in lieux):
            lieux.append({"texte": ville, "norm": n, "postes": postes, "source": "ville"})

    # cible : premier nom de classe rencontré (bâtiments par défaut)
    cible = None
    for l, m in zip(lemmes, mots):
        cible = next((c for c, syn in CIBLES.items()
                      if l in syn or l.rstrip("sx") in syn or m.rstrip("sx") in syn), None)
        if cible:
            break
    if cible is None:
        cible = "batiment"

    # intention
    intention = "lister"
    if re.match(r"^(est ce qu|existe|y a t il|il y a t il)", texte_reste) or "existe t il" in texte_reste:
        intention = "existe"
    somme = re.search(r"\b(total|totale|somme|cumul|cumulee|ensemble)\b", texte_reste)
    if ("combien" in mots or "nombre" in lemmes) and not somme:
        intention = "compter"
    elif somme:
        intention = "somme"           # « combien d'occupants au total » → SUM(?occupants)
    elif re.search(r"\b(moyen|moyenne|en moyenne)\b", texte_reste):
        intention = "moyenne"

    attribut = next((ATTRIBUTS[w] for pair in zip(mots, lemmes) for w in pair if w in ATTRIBUTS), None)

    if intention in ("lister", "existe"):
        # « consomme le plus / le moins », « le plus gros consommateur »
        m = re.search(r"\bconsomm\w* (?:le )?(plus|moins)\b(?! de| que)", texte_reste)
        if m or (definies.get("gros") and re.search(r"\ble plus\b", texte_reste)):
            intention, attribut = ("min" if m and m.group(1) == "moins" else "max"), "consommation"
            definies.pop("gros", None)
        else:
            for i, mot in enumerate(mots[:-1]):
                if mot in ("plus", "moins"):
                    adj = next((r for r in _racines(mots[i + 1], lemmes[i + 1]) if r in SUPERLATIFS), None)
                    if adj:
                        sens, attr = SUPERLATIFS[adj]
                        if mot == "moins":
                            sens = "min" if sens == "max" else "max"
                        intention, attribut = sens, attr
                        break
        if intention == "lister" and re.search(r"\b(maximal|maximale|record)\b", texte_reste):
            intention = "max"
        elif intention == "lister" and re.search(r"\b(minimal|minimale)\b", texte_reste):
            intention = "min"
    if intention in ("max", "min", "somme", "moyenne") and attribut is None:
        attribut = "consommation"

    comparaisons = _quantites_dans(ndoc, spans, texte_reste)

    return {
        "question": texte,
        "tokens": [{"texte": t.text, "lemme": t.lemma_ or t.text, "pos": t.pos_} for t in doc],
        "ner": [{"texte": e.text, "label": e.label_} for e in doc.ents],
        "entites": entites,
        "classes": classes,
        "definies": definies,
        "dpe": {"lettre": dpe["lettre"], "op": dpe["op"]} if dpe else None,
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


def _condition(cle, valeur):
    if cle == "autonome":
        expr = f"({CONDITIONS['vert']}\n    && {CONDITIONS['stockage']})"
    else:
        expr = CONDITIONS[cle]
    return f"# {'¬ ' if not valeur else ''}{COMMENTAIRES[cle]}\n  FILTER({'' if valeur else '!'}{expr})"


def _lieu(lieu):
    """Lieu repéré : bâtiments desservis par un poste de cette ville (R3), ou adresse / libellé."""
    texte = Literal(lieu["texte"].lower()).n3()
    adresse = f"CONTAINS(LCASE(STR(?adresse)), {texte}) || CONTAINS(LCASE(STR(?label)), {texte})"
    if lieu["postes"]:
        alts = " ".join(store.iri(p).n3() for p in lieu["postes"])
        return (f"# lieu « {lieu['texte']} » ({lieu['source']}) : poste de la ville (R3) ou adresse\n"
                f"  FILTER(EXISTS {{ ?b sg:estRaccordeA ?ll . ?ll sg:relie ?pl . VALUES ?pl {{ {alts} }} }}\n"
                f"         || {adresse})")
    return f"# lieu « {lieu['texte']} » (NER spaCy) : adresse ou libellé\n  FILTER({adresse})"


def _entite_batiment(e):
    x = store.iri(e["id"]).n3()
    if e["type"] == "batiment":
        return f"FILTER(?b = {x})"
    if e["type"] == "source":
        return f"# estAlimentePar {e['id']} (direct, inverse, R1, R6 ou R7)\n  FILTER EXISTS {{ {Q.CHEMINS_SOURCES.strip()}\n    FILTER(?s = {x}) }}"
    if e["type"] == "ligne":
        return f"{{ ?b sg:estRaccordeA {x} }} UNION {{ {x} sg:transporteVers ?b }}"
    if e["type"] == "poste":
        return (f"# R3 : estRaccordeA ∘ relie → estDesserviPar\n"
                f"  FILTER EXISTS {{ {{ ?b sg:estRaccordeA ?lp . ?lp sg:relie {x} }} UNION {{ ?b sg:estDesserviPar {x} }} }}")
    return f"# R2 : le stockage alimente le bâtiment → possedeStockage\n  {{ {x} sg:alimente ?b }} UNION {{ ?b sg:possedeStockage {x} }}"


def _types(a):
    if not a["classes"]:
        return []
    alts = " ".join(f"sg:{c}" for c in a["classes"])
    return [f"?b a ?type . VALUES ?type {{ {alts} }}"]


def _corps_batiment(a):
    m = [Q.CLASSE_LA_PLUS_PRECISE.strip(),
         "OPTIONAL { ?b rdfs:label ?label }",
         "OPTIONAL { ?b sg:adresse ?adresse }",
         "OPTIONAL { ?b sg:consommationAnnuelle ?conso }",
         "OPTIONAL { ?b sg:surface ?surface }",
         "OPTIONAL { ?b sg:nombreOccupants ?occupants }",
         "OPTIONAL { ?b sg:anneeConstruction ?annee }",
         "OPTIONAL { ?b sg:classeEnergetique ?dpe }",
         "OPTIONAL { ?b sg:puissanceSouscrite ?puissance }",
         "BIND(IF(BOUND(?conso) && BOUND(?surface) && ?surface > 0, ?conso / ?surface, ?unbound) AS ?intensite)"]
    m += _types(a)
    for cle, valeur in a["definies"].items():
        m.append(_condition(cle, valeur))
    if a["dpe"]:
        m.append(f'FILTER(?dpe {a["dpe"]["op"]} "{a["dpe"]["lettre"]}")  # classeEnergetique only {{"A", …, "G"}}')
    for e in a["entites"]:
        m.append(_entite_batiment(e))
    for lieu in a["lieux"]:
        m.append(_lieu(lieu))
    colonnes = ["?b", "?label", "?classe", "?conso", "?surface", "?intensite", "?dpe"]
    attr = VARIABLES.get(a["attribut"] or "")
    if attr and attr not in colonnes:
        colonnes.append(attr)
    for c in a["comparaisons"]:
        if VARIABLES[c["attribut"]] not in colonnes:
            colonnes.append(VARIABLES[c["attribut"]])
    return m, "?b", colonnes


def _filtres_bat(a, m):
    """Contraintes sur le bâtiment quand la cible est une source ou un poste."""
    m += _types(a)
    for cle, valeur in a["definies"].items():
        if cle != "vert":
            m.append(_condition(cle, valeur))
    for e in a["entites"]:
        if e["type"] == "batiment":
            m.append(f"FILTER(?b = {store.iri(e['id']).n3()})")
    for lieu in a["lieux"]:
        m.append(_lieu(lieu))


def _corps_source(a):
    m = ["?b a/rdfs:subClassOf* sg:Batiment ; a owl:NamedIndividual .",
         "OPTIONAL { ?b sg:adresse ?adresse } OPTIONAL { ?b rdfs:label ?nomBat }",
         "BIND(?nomBat AS ?label)",
         f"# estAlimentePar par 5 chemins : direct, inverse, R1, R6, R7\n  {Q.CHEMINS_SOURCES.strip()}",
         "?s a ?classe . ?classe rdfs:subClassOf* sg:SourceEnergie .",
         "FILTER NOT EXISTS { ?s a ?autre . ?autre rdfs:subClassOf+ ?classe . FILTER(?autre != ?classe) }",
         "OPTIONAL { ?s rdfs:label ?source }"]
    if "vert" in a["definies"]:
        neg = "" if a["definies"]["vert"] else "!"
        m.append(f"FILTER({neg}EXISTS {{ ?s a/rdfs:subClassOf* sg:SourceRenouvelable }})")
    for e in a["entites"]:
        if e["type"] == "source":
            m.append(f"FILTER(?s = {store.iri(e['id']).n3()})")
    _filtres_bat(a, m)
    return m, "?s", ["?s", "?source", "?classe", "?via", "?b"]


def _corps_poste(a):
    m = ["?b a/rdfs:subClassOf* sg:Batiment ; a owl:NamedIndividual .",
         "OPTIONAL { ?b sg:adresse ?adresse } OPTIONAL { ?b rdfs:label ?label }",
         "# R3 : Batiment(?b) ∧ estRaccordeA(?b, ?l) ∧ relie(?l, ?p) → estDesserviPar(?b, ?p)",
         "{ ?b sg:estRaccordeA ?l . ?l sg:relie ?p } UNION { ?b sg:estDesserviPar ?p }",
         "OPTIONAL { ?p rdfs:label ?poste } OPTIONAL { ?p sg:ville ?ville }"]
    if a["definies"].get("vert") is not None:
        m.append(_condition("vert", a["definies"]["vert"]))
    for e in a["entites"]:
        if e["type"] == "poste":
            m.append(f"FILTER(?p = {store.iri(e['id']).n3()})")
    _filtres_bat(a, m)
    return m, "?p", ["?p", "?poste", "?ville", "?b", "?l"]


def generer(a):
    """Construit la requête SPARQL à partir de l'analyse. Renvoie (sparql, est_ask)."""
    corps_de = {"batiment": _corps_batiment, "source": _corps_source, "poste": _corps_poste}
    motifs, var, colonnes = corps_de[a["cible"]](a)
    if a["cible"] == "batiment":
        motifs += [_filtre(c) for c in a["comparaisons"]]

    corps = "\n  ".join(motifs)
    intention = a["intention"] if a["cible"] == "batiment" or a["intention"] in ("compter", "existe", "lister") else "lister"
    attr_var = VARIABLES.get(a["attribut"] or "")
    if attr_var not in colonnes:
        attr_var = None

    if intention == "existe":
        return f"ASK {{\n  {corps}\n}}", True
    if intention == "compter":
        return f"SELECT (COUNT(DISTINCT {var}) AS ?nombre) WHERE {{\n  {corps}\n}}", False
    if intention in ("somme", "moyenne") and attr_var:
        fn, alias = ("SUM", "?total") if intention == "somme" else ("AVG", "?moyenne")
        # sous-requête DISTINCT : chaque bâtiment n'est compté qu'une fois
        return (f"SELECT ({fn}({attr_var}) AS {alias}) (COUNT({var}) AS ?nombre) WHERE {{\n"
                f"  {{ SELECT DISTINCT {var} {attr_var} WHERE {{\n  {corps}\n  FILTER(BOUND({attr_var}))\n  }} }}\n}}"), False
    select = "SELECT DISTINCT " + " ".join(colonnes)
    if intention in ("max", "min") and attr_var:
        ordre = f"DESC({attr_var})" if intention == "max" else f"ASC({attr_var})"
        return f"{select} WHERE {{\n  {corps}\n  FILTER(BOUND({attr_var}))\n}}\nORDER BY {ordre}\nLIMIT 1", False
    ordre = "DESC(?conso)" if "?conso" in colonnes else colonnes[1]
    return f"{select} WHERE {{\n  {corps}\n}}\nORDER BY {ordre}", False


# ------------------------------------------------------------ restitution --

NOMS_CIBLES = {"batiment": "bâtiments", "source": "sources qui alimentent les bâtiments",
               "poste": "postes qui desservent les bâtiments (R3)"}
NOMS_INTENTIONS = {"lister": "Lister", "compter": "Compter", "max": "Maximum", "min": "Minimum",
                   "somme": "Somme", "moyenne": "Moyenne", "existe": "Existe-t-il"}
SYMBOLES = {">": ">", ">=": "≥", "<": "<", "<=": "≤", "=": "="}


def _fmt(x):
    return f"{int(x):,}".replace(",", " ") if float(x).is_integer() else str(x)


def interpretation(a):
    morceaux = [f"{NOMS_INTENTIONS[a['intention']]} · {NOMS_CIBLES[a['cible']]}"]
    if a["attribut"] and a["intention"] in ("max", "min", "somme", "moyenne"):
        morceaux.append(f"sur {a['attribut']}")
    for c in a["classes"]:
        morceaux.append(f"type {c}")
    for cle, v in a["definies"].items():
        nom = "SourceRenouvelable" if cle == "vert" and a["cible"] == "source" else NOMS_DEFINIES[cle]
        morceaux.append(f"{'' if v else 'non '}{nom}")
    if a["dpe"]:
        morceaux.append(f"classe DPE {SYMBOLES[a['dpe']['op']]} {a['dpe']['lettre']}")
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
    "Quels bâtiments sont autonomes ?",
    "Combien de gros consommateurs y a-t-il ?",
    "Quelle est la consommation totale des bâtiments publics ?",
    "Bâtiments de plus de 10000 m² raccordés en haute tension",
    "Quel bâtiment consomme le plus ?",
    "Quel est le bâtiment le plus ancien ?",
    "Quelles sources alimentent l'hôpital Charles Nicolle ?",
    "Quels postes desservent l'usine de Sfax ?",
    "Bâtiments desservis par le poste de Radès",
    "Bâtiments verts sans batterie",
    "Bâtiments de classe énergétique D ou pire",
    "Existe-t-il un bâtiment intelligent à Sfax ?",
    "Intensité moyenne des bâtiments industriels",
    "Bâtiments construits avant 1990 entre 100 et 5000 m²",
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
