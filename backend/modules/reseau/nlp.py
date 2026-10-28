"""Module NLP → SPARQL du Réseau (Membre 4 · Nourane Lammouchi).

Traduit une question en français en requête SPARQL, sans API de LLM.
Outils : spaCy 3 + modèle fr_core_news_sm (tokenisation, lemmatisation,
étiquetage morpho-syntaxique, entités nommées) et PhraseMatcher de spaCy
pour relier les mots de la question aux individus de l'ontologie.

Étapes :
  1. analyse spaCy de la question (lemmes, catégories grammaticales, NER) ;
  2. liaison d'entités : PhraseMatcher construit à partir des rdfs:label,
     des identifiants et des villes des individus (postes, lignes, bâtiments,
     opérateurs) ;
  3. détection de l'intention (lister, compter, max, min, somme, moyenne,
     existence) et de la classe cible (lignes, postes, bâtiments, opérateurs) ;
  4. extraction des contraintes : catégorie HT/MT/BT, comparaisons numériques
     (« plus de 100 kV », « entre 10 et 50 km », « après 2005 »), relations ;
  5. génération de la requête SPARQL, exécutée ensuite par RDFLib.
"""
import re
import unicodedata

import spacy
from spacy.matcher import PhraseMatcher
from spacy.util import filter_spans

import store

# ------------------------------------------------------------ vocabulaire --

CIBLES = {
    "ligne": {"ligne", "cable"},
    "poste": {"poste", "station", "sous-station"},
    "batiment": {"batiment", "immeuble", "edifice", "consommateur"},
    "operateur": {"operateur", "gestionnaire", "exploitant"},
}

ATTRIBUTS = {  # mot de la question → propriété
    "tension": "tension", "voltage": "tension",
    "longueur": "longueur", "distance": "longueur",
    "capacite": "capacite", "puissance": "capacite",
    "annee": "annee", "age": "annee", "date": "annee",
}

UNITES = {"kv": "tension", "kilovolt": "tension", "kilovolts": "tension",
          "km": "longueur", "kilometre": "longueur", "kilometres": "longueur",
          "mva": "capacite"}

# superlatifs « la plus longue », « le moins puissant »… : adjectif → (sens, attribut)
SUPERLATIFS = {
    "haut": ("max", "tension"), "eleve": ("max", None), "fort": ("max", None),
    "bas": ("min", "tension"), "faible": ("min", None),
    "long": ("max", "longueur"), "court": ("min", "longueur"),
    "grand": ("max", None), "gros": ("max", None), "puissant": ("max", "capacite"),
    "petit": ("min", None),
    "recent": ("max", "annee"), "nouveau": ("max", "annee"),
    "ancien": ("min", "annee"), "vieux": ("min", "annee"),
}

COMPARATEURS = [  # (expression avant le nombre, opérateur SPARQL)
    ("au moins", ">="), ("a partir de", ">="), ("depuis", ">="), ("minimum", ">="),
    ("au plus", "<="), ("jusqu a", "<="), ("maximum", "<="),
    ("plus de", ">"), ("plus que", ">"), ("superieur", ">"), ("superieure", ">"),
    ("au dessus de", ">"), ("depasse", ">"), ("depassant", ">"), ("apres", ">"), (">", ">"),
    ("moins de", "<"), ("moins que", "<"), ("inferieur", "<"), ("inferieure", "<"),
    ("en dessous de", "<"), ("avant", "<"), ("<", "<"),
]

VARIABLES = {"tension": "?tension", "longueur": "?longueur", "capacite": "?capacite", "annee": "?annee"}
UNITE_AFFICHEE = {"tension": " kV", "longueur": " km", "capacite": " MVA", "annee": ""}


def normaliser(texte):
    """minuscules, sans accents, ponctuation de liaison → espace (même longueur que l'entrée)."""
    sans_accents = "".join(
        unicodedata.normalize("NFD", c)[0] for c in texte.lower())
    return re.sub(r"[-–—_'’]", " ", sans_accents)


# ------------------------------------------------------------ pipeline spaCy --

_nlp = None
_matcher = None
_matcher_version = None
_individus = {}  # id → (type, label)


def nlp():
    global _nlp
    if _nlp is None:
        try:
            _nlp = spacy.load("fr_core_news_sm")
        except OSError:  # modèle absent : tokeniseur seul (python -m spacy download fr_core_news_sm)
            _nlp = spacy.blank("fr")
    return _nlp


INDIVIDUS = """
SELECT ?x ?type ?label ?ville WHERE {
  { ?x a sg:PosteElectrique . BIND("poste" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:LigneElectrique . BIND("ligne" AS ?type) }
  UNION { ?x a/rdfs:subClassOf* sg:Batiment . BIND("batiment" AS ?type) }
  UNION { ?x a sg:OperateurReseau . BIND("operateur" AS ?type) }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  OPTIONAL { ?x sg:ville ?ville }
}"""


def _alias(type_, ident, label, ville):
    """Toutes les façons d'écrire un individu dans une question."""
    noms = {label or ident, ident.replace("_", " ")}
    if type_ == "poste":
        lieu = ville or ident.removeprefix("Poste_").replace("_", " ")
        noms |= {lieu, f"poste {lieu}", f"poste de {lieu}", f"poste d {lieu}"}
    if type_ == "ligne":
        reste = re.sub(r"^Ligne_((BT|MT|HT)_)?", "", ident).replace("_", " ")
        noms |= {f"ligne {reste}", f"ligne de {reste}", f"ligne d {reste}", f"ligne du {reste}"}
    if type_ == "batiment":
        if label:
            noms.add(label.split(" ", 1)[-1])  # « Hôpital Charles Nicolle » → « Charles Nicolle »
        parties = ident.split("_")
        if len(parties) == 2:  # Ecole_Ariana → « école d'Ariana », « école de Ariana »…
            a, b = parties
            noms |= {f"{a} {b}", f"{a} d {b}", f"{a} de {b}", f"{a} du {b}"}
    return {normaliser(n).strip() for n in noms if n and len(n) > 2}


def _matcher_a_jour():
    """(Re)construit le PhraseMatcher quand le graphe a changé (CRUD)."""
    global _matcher, _matcher_version, _individus
    version = len(store.graph)
    if _matcher is not None and version == _matcher_version:
        return _matcher
    _matcher = PhraseMatcher(nlp().vocab, attr="LOWER")
    _individus = {}
    for r in store.select(INDIVIDUS):
        _individus[r["x"]] = (r["type"], r["label"] or r["x"])
        motifs = [nlp().make_doc(a) for a in _alias(r["type"], r["x"], r["label"], r["ville"])]
        _matcher.add(f"{r['type']}|{r['x']}", motifs)
    _matcher_version = version
    return _matcher


# ---------------------------------------------------------------- analyse --

def _entites(texte_norm):
    doc = nlp().make_doc(texte_norm)
    spans = []
    for match_id, start, end in _matcher_a_jour()(doc):
        type_, ident = nlp().vocab.strings[match_id].split("|", 1)
        span = doc[start:end]
        span.label_ = type_
        span.kb_id_ = ident
        spans.append(span)
    garder = filter_spans(spans)  # le plus long gagne : « usine de sfax » plutôt que « sfax »
    return [{"texte": s.text, "type": s.label_, "id": s.kb_id_, "label": _individus[s.kb_id_][1],
             "debut": s.start_char, "fin": s.end_char} for s in garder]


def _hors_entites(doc, entites):
    pris = [(e["debut"], e["fin"]) for e in entites]
    return [t for t in doc if not any(a <= t.idx < b for a, b in pris)]


def _lemme(t):
    return normaliser(t.lemma_ or t.text).strip()


def _nombre(t):
    try:
        return float(t.text.replace(",", "."))
    except ValueError:
        return None


def _comparaisons(tokens, cible):
    """« plus de 100 kV », « entre 10 et 50 km », « après 2005 », « de 225 kV »."""
    out = []
    for i, t in enumerate(tokens):
        valeur = _nombre(t)
        if valeur is None or not (t.like_num or t.pos_ == "NUM" or re.fullmatch(r"[\d.,]+", t.text)):
            continue
        suivant = normaliser(tokens[i + 1].text).strip() if i + 1 < len(tokens) else ""
        avant = " ".join(normaliser(x.text).strip() for x in tokens[max(0, i - 4):i])

        attribut = UNITES.get(suivant)
        if attribut is None and re.fullmatch(r"(19|20)\d\d", t.text):
            attribut = "annee"
        if attribut is None:
            attribut = "capacite" if cible == "poste" else "tension"

        # « entre X et Y » : on traite la paire sur le premier nombre
        if re.search(r"\bet$", avant) and out and out[-1].get("entre"):
            out[-1].update(op="entre", max=valeur, attribut=attribut)
            out[-1].pop("entre")
            continue
        op = "="
        for expr, symbole in COMPARATEURS:
            if re.search(rf"(^|\s){re.escape(expr)}(\s|$)", avant):
                op = symbole
                break
        if re.search(r"(^|\s)entre(\s|$)", avant):
            out.append({"attribut": attribut, "op": "entre", "min": valeur, "entre": True})
            continue
        out.append({"attribut": attribut, "op": op, "valeur": valeur})
    for c in out:
        c.pop("entre", None)
    return out


def analyser(question):
    texte = unicodedata.normalize("NFC", re.sub(r"\s+", " ", question)).strip()
    doc = nlp()(texte)
    norm = normaliser(texte)
    entites = _entites(norm)
    reste = _hors_entites(doc, entites)
    lemmes = [_lemme(t) for t in reste]
    mots = [normaliser(t.text).strip() for t in reste]
    texte_reste = " ".join(mots)

    # classe cible : premier nom (hors entités) qui désigne une classe du module
    cible = None
    for l in lemmes:
        cible = next((c for c, syn in CIBLES.items() if l in syn or l.rstrip("s") in syn), None)
        if cible:
            break
    if cible is None and "qui" in mots and any(l.startswith("ger") for l in lemmes):
        cible = "operateur"
    if cible is None and entites:
        cible = entites[0]["type"]  # « Quelle est la tension de la ligne Tunis Sousse ? »
    if cible is None and re.search(r"\b(tension|kv)\b", texte_reste):
        cible = "ligne"

    # catégorie déduite (classes définies)
    categorie = None
    for cat, motif in (("HT", r"\bhaute?s? tensions?\b|\bht\b"),
                       ("MT", r"\bmoyennes? tensions?\b|\bmt\b"),
                       ("BT", r"\bbasses? tensions?\b|\bbt\b")):
        if re.search(motif, texte_reste):
            categorie = cat
            break

    # attribut cité explicitement
    attribut = next((ATTRIBUTS[l] for l in lemmes if l in ATTRIBUTS), None)
    if attribut == "capacite" and cible == "ligne":
        attribut = "tension"

    # intention
    intention = "lister"
    if mots and (texte_reste.startswith(("est ce qu", "existe", "y a t il")) or "existe t il" in texte_reste) \
            and "combien" not in mots:
        intention = "existe"
    if "combien" in mots or "nombre" in lemmes:
        intention = "compter"
    elif re.search(r"\b(total|totale|somme|cumul|cumulee)\b", texte_reste):
        intention = "somme"
    elif re.search(r"\b(en moyenne|(tension|longueur|capacite|puissance|annee) moyenne)\b", texte_reste):
        intention = "moyenne"
    else:
        for i, m in enumerate(mots[:-1]):
            if m in ("plus", "moins"):
                adj = lemmes[i + 1]
                if adj in SUPERLATIFS:
                    sens, attr = SUPERLATIFS[adj]
                    if m == "moins":
                        sens = "min" if sens == "max" else "max"
                    intention, attribut = sens, attribut or attr
                    break
        if re.search(r"\b(maximale?|maximum|max)\b", texte_reste) and not re.search(r"\bau maximum\b", texte_reste):
            intention = "max"
        elif re.search(r"\b(minimale?|minimum|min)\b", texte_reste) and not re.search(r"\bau minimum\b", texte_reste):
            intention = "min"
    if intention in ("max", "min", "somme", "moyenne") and attribut is None:
        attribut = "capacite" if cible == "poste" else "longueur" if intention == "somme" else "tension"

    comparaisons = _comparaisons(reste, cible)

    relation = None
    if any(l.startswith(("secour", "secours")) for l in lemmes):
        relation = "secours"
    elif any(l.startswith(("connect", "interconnect")) for l in lemmes):
        relation = "connexion"

    return {
        "question": texte,
        "tokens": [{"texte": t.text, "lemme": t.lemma_ or t.text, "pos": t.pos_} for t in doc],
        "ner": [{"texte": e.text, "label": e.label_} for e in doc.ents],
        "entites": entites,
        "intention": intention,
        "cible": cible,
        "categorie": categorie,
        "attribut": attribut,
        "comparaisons": comparaisons,
        "relation": relation,
    }


# ------------------------------------------------------- génération SPARQL --

CATEGORIE_BIND = """BIND(IF(?tension >= 63, "HT", IF(?tension <= 1, "BT", "MT")) AS ?categorie)"""


def _filtre_nombre(c):
    var = VARIABLES[c["attribut"]]
    if c["op"] == "entre":
        return f"FILTER({var} >= {c['min']} && {var} <= {c['max']})"
    return f"FILTER({var} {c['op']} {c['valeur']})"


def generer(a):
    """Construit la requête SPARQL à partir de l'analyse. Renvoie (sparql, est_ask)."""
    cible = a["cible"]
    ents = a["entites"]
    par_type = lambda t: [e for e in ents if e["type"] == t]  # noqa: E731
    sg = lambda i: store.iri(i).n3()  # noqa: E731
    motifs, colonnes = [], []

    if cible == "ligne":
        var = "?ligne"
        motifs += ["?ligne a/rdfs:subClassOf* sg:LigneElectrique .",
                   "OPTIONAL { ?ligne rdfs:label ?label }",
                   "OPTIONAL { ?ligne sg:tension ?tension }",
                   "OPTIONAL { ?ligne sg:longueur ?longueur }",
                   "OPTIONAL { ?ligne sg:anneeMiseEnService ?annee }",
                   CATEGORIE_BIND]
        colonnes = ["?ligne", "?label", "?tension", "?longueur", "?annee", "?categorie"]
        if a["categorie"]:
            classe = {"HT": "LigneHauteTension", "MT": "LigneMoyenneTension", "BT": "LigneBasseTension"}[a["categorie"]]
            motifs.append(f'FILTER(?categorie = "{a["categorie"]}")  # classe définie {classe}')
        for e in par_type("ligne"):
            motifs.append(f"FILTER({var} = {sg(e['id'])})")
        for e in par_type("poste"):
            motifs.append(f"?ligne sg:relie {sg(e['id'])} .")
        for e in par_type("batiment"):
            motifs.append(f"{{ ?ligne sg:transporteVers {sg(e['id'])} }} UNION {{ {sg(e['id'])} sg:estRaccordeA ?ligne }}")
        for e in par_type("operateur"):
            motifs.append(f"# R4 : l'opérateur gère la ligne ou un poste qu'elle relie\n"
                          f"  {{ {sg(e['id'])} sg:gere ?ligne }} UNION {{ {sg(e['id'])} sg:gere ?pg . ?ligne sg:relie ?pg }}")

    elif cible == "poste":
        var = "?poste"
        motifs += ["?poste a sg:PosteElectrique .",
                   "OPTIONAL { ?poste rdfs:label ?label }",
                   "OPTIONAL { ?poste sg:ville ?ville }",
                   "OPTIONAL { ?poste sg:capaciteTransformation ?capacite }",
                   "OPTIONAL { ?poste sg:anneeMiseEnService ?annee }"]
        colonnes = ["?poste", "?label", "?ville", "?capacite", "?annee"]
        postes = par_type("poste")
        if postes and a["relation"] == "secours":
            for e in postes:
                motifs.append(f"?poste sg:secourt {sg(e['id'])} .")
        elif postes and (a["relation"] == "connexion" or len(postes) == 1 and par_type("ligne") == []
                         and not a["comparaisons"]):
            for e in postes:
                motifs.append(f"# estConnecteA est symétrique\n"
                              f"  {{ ?poste sg:estConnecteA {sg(e['id'])} }} UNION {{ {sg(e['id'])} sg:estConnecteA ?poste }}")
        else:
            for e in postes:
                motifs.append(f"FILTER({var} = {sg(e['id'])})")
        for e in par_type("ligne"):
            motifs.append(f"{sg(e['id'])} sg:relie ?poste .")
        for e in par_type("operateur"):
            motifs.append(f"{sg(e['id'])} sg:gere ?poste .")
        for e in par_type("batiment"):
            motifs.append(f"# R3 : estRaccordeA ∘ relie → estDesserviPar\n"
                          f"  {sg(e['id'])} sg:estRaccordeA ?lb . ?lb sg:relie ?poste .")
        if a["categorie"]:
            motifs.append(f"FILTER EXISTS {{ ?l sg:relie ?poste ; sg:tension ?t . "
                          f"FILTER({_condition_categorie(a['categorie'], '?t')}) }}")

    elif cible == "batiment":
        var = "?batiment"
        motifs += ["?batiment a/rdfs:subClassOf* sg:Batiment ; a ?classe .",
                   "?classe rdfs:subClassOf* sg:Batiment .",
                   "OPTIONAL { ?batiment rdfs:label ?label }"]
        colonnes = ["?batiment", "?label", "?classe"]
        for e in par_type("poste"):
            motifs.append(f"# R3 : un bâtiment raccordé à une ligne est desservi par le poste de cette ligne\n"
                          f"  {{ ?batiment sg:estRaccordeA ?l . ?l sg:relie {sg(e['id'])} }}\n"
                          f"  UNION {{ ?l sg:transporteVers ?batiment . ?l sg:relie {sg(e['id'])} }}\n"
                          f"  UNION {{ ?batiment sg:estDesserviPar {sg(e['id'])} }}")
        for e in par_type("ligne"):
            motifs.append(f"{{ {sg(e['id'])} sg:transporteVers ?batiment }} UNION {{ ?batiment sg:estRaccordeA {sg(e['id'])} }}")
        if a["categorie"]:
            motifs.append(f"{{ ?lc sg:transporteVers ?batiment }} UNION {{ ?batiment sg:estRaccordeA ?lc }}\n"
                          f"  ?lc sg:tension ?tc . FILTER({_condition_categorie(a['categorie'], '?tc')})")
        if not ents and not a["categorie"]:
            motifs.append("{ ?l sg:transporteVers ?batiment } UNION { ?batiment sg:estRaccordeA ?l }  # reliés au réseau")

    elif cible == "operateur":
        var = "?operateur"
        motifs += ["?operateur a sg:OperateurReseau .", "OPTIONAL { ?operateur rdfs:label ?label }"]
        colonnes = ["?operateur", "?label"]
        for e in par_type("poste"):
            motifs.append(f"?operateur sg:gere {sg(e['id'])} .")
        for e in par_type("ligne"):
            motifs.append(f"# R4 : gere(o, p) ∧ relie(l, p) → gere(o, l)\n"
                          f"  {{ ?operateur sg:gere {sg(e['id'])} }} UNION {{ ?operateur sg:gere ?p . {sg(e['id'])} sg:relie ?p }}")
        for e in par_type("operateur"):
            motifs.append(f"FILTER(?operateur = {sg(e['id'])})")
    else:
        return None, False

    for c in a["comparaisons"]:
        if c["attribut"] in ("tension", "longueur") and cible != "ligne":
            continue
        if c["attribut"] == "capacite" and cible != "poste":
            continue
        motifs.append(_filtre_nombre(c))

    corps = "\n  ".join(motifs)
    intention = a["intention"]
    attr_var = VARIABLES.get(a["attribut"] or "", None)
    if attr_var and attr_var not in colonnes:
        attr_var = None

    if intention == "existe":
        return f"ASK {{\n  {corps}\n}}", True
    if intention == "compter":
        return f"SELECT (COUNT(DISTINCT {var}) AS ?nombre) WHERE {{\n  {corps}\n}}", False
    if intention in ("somme", "moyenne") and attr_var:
        fn = "SUM" if intention == "somme" else "AVG"
        alias = "?total" if intention == "somme" else "?moyenne"
        return (f"SELECT ({fn}({attr_var}) AS {alias}) (COUNT(DISTINCT {var}) AS ?nombre) WHERE {{\n"
                f"  {corps}\n  FILTER(BOUND({attr_var}))\n}}"), False
    select = "SELECT DISTINCT " + " ".join(colonnes)
    if intention in ("max", "min") and attr_var:
        ordre = f"DESC({attr_var})" if intention == "max" else f"ASC({attr_var})"
        return (f"{select} WHERE {{\n  {corps}\n  FILTER(BOUND({attr_var}))\n}}\n"
                f"ORDER BY {ordre}\nLIMIT 1"), False
    ordre = "DESC(?tension)" if cible == "ligne" else "DESC(?capacite)" if cible == "poste" else "?label"
    return f"{select} WHERE {{\n  {corps}\n}}\nORDER BY {ordre}", False


def _condition_categorie(cat, var):
    return {"HT": f"{var} >= 63", "BT": f"{var} <= 1", "MT": f"{var} > 1 && {var} < 63"}[cat]


# ------------------------------------------------------------ restitution --

NOMS_CIBLES = {"ligne": "lignes", "poste": "postes", "batiment": "bâtiments", "operateur": "opérateurs"}
NOMS_INTENTIONS = {"lister": "Lister", "compter": "Compter", "max": "Maximum", "min": "Minimum",
                   "somme": "Somme", "moyenne": "Moyenne", "existe": "Existe-t-il"}
SYMBOLES = {">": ">", ">=": "≥", "<": "<", "<=": "≤", "=": "="}


def interpretation(a):
    morceaux = [f"{NOMS_INTENTIONS[a['intention']]} · {NOMS_CIBLES.get(a['cible'], '?')}"]
    if a["attribut"] and a["intention"] in ("max", "min", "somme", "moyenne"):
        morceaux.append(f"sur {a['attribut']}")
    if a["categorie"]:
        morceaux.append(f"catégorie {a['categorie']}")
    for e in a["entites"]:
        morceaux.append(f"{e['type']} = sg:{e['id']}")
    if a["relation"]:
        morceaux.append(f"relation {a['relation']}")
    for c in a["comparaisons"]:
        u = UNITE_AFFICHEE[c["attribut"]]
        if c["op"] == "entre":
            morceaux.append(f"{c['attribut']} entre {_fmt(c['min'])} et {_fmt(c['max'])}{u}")
        else:
            morceaux.append(f"{c['attribut']} {SYMBOLES[c['op']]} {_fmt(c['valeur'])}{u}")
    return " · ".join(morceaux)


def _fmt(x):
    return str(int(x)) if float(x).is_integer() else str(x)


EXEMPLES = [
    "Quelles sont les lignes haute tension ?",
    "Combien de postes y a-t-il ?",
    "Lignes reliées au poste de Sfax de plus de 200 kV",
    "Quelle est la ligne la plus longue ?",
    "Longueur totale des lignes moyenne tension",
    "Quels postes sont connectés au poste de Sfax ?",
    "Quels bâtiments sont desservis par le poste d'Ariana ?",
    "Qui gère la ligne Bizerte-Ariana ?",
    "Postes de plus de 200 MVA mis en service après 2000",
    "Lignes entre 10 et 100 km",
    "Existe-t-il une ligne de plus de 300 kV ?",
    "Quel poste a la plus grande capacité ?",
]


def repondre(question):
    a = analyser(question)
    sparql, est_ask = generer(a)
    reponse = {"analyse": a, "interpretation": interpretation(a) if a["cible"] else None, "sparql": sparql}
    if sparql is None:
        reponse["erreur"] = ("Je n'ai pas reconnu de quoi parle la question : mentionnez des lignes, "
                             "des postes, des bâtiments ou un opérateur.")
        return reponse
    if est_ask:
        reponse["booleen"] = store.ask(sparql)
        reponse["colonnes"], reponse["lignes"] = [], []
    else:
        lignes = store.select(sparql)
        reponse["colonnes"] = re.findall(r"\?(\w+)", sparql.split("WHERE")[0])
        if " AS ?" in sparql.split("WHERE")[0]:
            reponse["colonnes"] = re.findall(r"AS \?(\w+)", sparql.split("WHERE")[0])
        reponse["lignes"] = lignes
    return reponse
