"""Requêtes SPARQL du module Production d'énergie (Membre 1 · Wala Rezgui).

Classes : SourceEnergie, SourceRenouvelable ⊑ SourceEnergie, Solaire ⊑ SourceRenouvelable,
Eolien ⊑ SourceRenouvelable, SourceNonRenouvelable ⊑ SourceEnergie.

Hiérarchie : seuls les types les plus précis sont assertés (Solaire, Eolien…) ; les requêtes
utilisent rdfs:subClassOf* pour qu'une « source renouvelable » inclue Solaire et Eolien.

Alimentation d'un bâtiment par une source : mêmes 5 chemins que le module Bâtiments.
  - estAlimentePar (asserté côté Bâtiments) et son inverse produitEnergiePour (asserté ici) ;
  - R1 : SourceEnergie(?s) ^ injecteDans(?s, ?l) ^ transporteVers(?l, ?b) → estAlimentePar(?b, ?s)
  - R7 : Batiment(?b) ^ estRaccordeA(?b, ?l) ^ injecteDans(?s, ?l) → estAlimentePar(?b, ?s)
  - R6 : SystemeStockage(?x) ^ stockeEnergieDe(?x, ?s) ^ alimente(?x, ?b) → estAlimentePar(?b, ?s)
RDFLib n'exécute pas SWRL : ces règles sont réécrites en SPARQL et évaluées à chaque lecture,
sur le graphe courant (aucune déduction n'est stockée, donc rien ne devient obsolète).

Toutes les valeurs saisies passent par iri() (identifiants validés) ou Literal(...).n3().
"""
import unicodedata

from rdflib import Literal
from rdflib.namespace import XSD

from store import iri, n3_float, n3_label

TYPES = ("Solaire", "Eolien", "SourceRenouvelable", "SourceNonRenouvelable", "SourceEnergie")
CATEGORIES = {  # filtre → motif SPARQL (sous-classes comprises)
    "renouvelable": "?s a/rdfs:subClassOf* sg:SourceRenouvelable .",
    "non_renouvelable": "?s a/rdfs:subClassOf* sg:SourceNonRenouvelable .",
    "solaire": "?s a/rdfs:subClassOf* sg:Solaire .",
    "eolien": "?s a/rdfs:subClassOf* sg:Eolien .",
    "non_classee": ("FILTER NOT EXISTS { ?s a/rdfs:subClassOf* sg:SourceRenouvelable } "
                    "FILTER NOT EXISTS { ?s a/rdfs:subClassOf* sg:SourceNonRenouvelable }"),
}
# propriétés sortantes que le module Production possède (supprimées avec la source)
PROPRIETES_PROPRES = ("type", "label", "comment", "puissanceInstallee", "dateMiseEnService",
                      "injecteDans", "produitEnergiePour")


def ids(var, alias):
    """GROUP_CONCAT des identifiants locaux (COALESCE : bug RDFLib sur variable non liée)."""
    return (f'(GROUP_CONCAT(DISTINCT COALESCE(STRAFTER(STR(?{var}), "#"), ""); '
            f'separator="|") AS ?{alias})')


def n3_date(value):
    return Literal(value, datatype=XSD.dateTime).n3()


def sans_accents(texte):
    return "".join(c for c in unicodedata.normalize("NFD", texte.lower()) if unicodedata.category(c) != "Mn")


def _norm(expr):
    """LCASE + suppression des accents courants, côté SPARQL (recherche insensible aux accents)."""
    for motif, lettre in (("[éèêë]", "e"), ("[àâä]", "a"), ("[îï]", "i"), ("[ôö]", "o"), ("[ùûü]", "u"), ("ç", "c")):
        expr = f'REPLACE({expr}, "{motif}", "{lettre}")'
    return expr


def _recherche(q, *variables):
    needle = Literal(sans_accents(q)).n3()
    tests = [f"CONTAINS({_norm(f'LCASE(STR(?{v}))')}, {needle})" for v in variables]
    return f"FILTER({' || '.join(tests)})"


# Type le plus précis parmi les classes de la hiérarchie (une source peut ne porter que Solaire)
TYPE_PRECIS = """?s a ?type . ?type rdfs:subClassOf* sg:SourceEnergie .
    FILTER NOT EXISTS { ?s a ?autre . ?autre rdfs:subClassOf+ ?type . FILTER(?autre != ?type) }"""

FAMILLES = """BIND(EXISTS { ?s a/rdfs:subClassOf* sg:SourceRenouvelable } AS ?renouvelable)
  BIND(EXISTS { ?s a/rdfs:subClassOf* sg:SourceNonRenouvelable } AS ?nonRenouvelable)"""


def chemins(s="?s", b="?b", par="?par", via="?via"):
    """Les 5 chemins d'alimentation d'un bâtiment par une source, avec leur justification."""
    return f"""{{ {b} sg:estAlimentePar {s} . BIND("estAlimentePar" AS {via}) }}
    UNION {{ {s} sg:produitEnergiePour {b} . BIND("produitEnergiePour" AS {via}) }}
    UNION {{ {s} sg:injecteDans {par} . {par} sg:transporteVers {b} . BIND("R1" AS {via}) }}
    UNION {{ {b} sg:estRaccordeA {par} . {s} sg:injecteDans {par} . BIND("R7" AS {via}) }}
    UNION {{ {par} a/rdfs:subClassOf* sg:SystemeStockage ; sg:alimente {b} .
             {{ {par} sg:stockeEnergieDe {s} }} UNION {{ {s} sg:estStockePar {par} }} BIND("R6" AS {via}) }}
    {b} a/rdfs:subClassOf* sg:Batiment ."""


# ---------------------------------------------------------------- lecture --

def lister(q=None, categorie=None, puissance_min=None, puissance_max=None, sans_puissance=False,
           date_min=None, date_max=None, source=None):
    filtres = []
    if q:
        filtres.append(_recherche(q, "label", "s"))
    if categorie in CATEGORIES:
        filtres.append(CATEGORIES[categorie])
    if puissance_min is not None:
        filtres.append(f"FILTER(BOUND(?puissance) && ?puissance >= {float(puissance_min)})")
    if puissance_max is not None:
        filtres.append(f"FILTER(BOUND(?puissance) && ?puissance <= {float(puissance_max)})")
    if sans_puissance:
        filtres.append("FILTER(!BOUND(?puissance))")
    if date_min:
        filtres.append(f"FILTER(BOUND(?date) && ?date >= {n3_date(date_min)})")
    if date_max:
        filtres.append(f"FILTER(BOUND(?date) && ?date <= {n3_date(date_max)})")
    if source:
        filtres.append(f"FILTER(?s = {iri(source).n3()})")
    return f"""
SELECT ?s ?label ?puissance ?date ?renouvelable ?nonRenouvelable
       {ids("type", "types")} {ids("l", "lignes")}
WHERE {{
  ?s a/rdfs:subClassOf* sg:SourceEnergie .
  OPTIONAL {{ ?s rdfs:label ?label }}
  OPTIONAL {{ ?s sg:puissanceInstallee ?puissance }}
  OPTIONAL {{ ?s sg:dateMiseEnService ?date }}
  OPTIONAL {{ {TYPE_PRECIS} }}
  {FAMILLES}
  OPTIONAL {{ ?s sg:injecteDans ?l }}
  {chr(10).join("  " + f for f in filtres)}
}}
GROUP BY ?s ?label ?puissance ?date ?renouvelable ?nonRenouvelable
ORDER BY DESC(?puissance) ?label"""


def alimentation(source=None, batiment=None):
    """Bâtiments alimentés par la (les) source(s), une ligne par chemin justificatif."""
    valeurs = []
    if source:
        valeurs.append(f"VALUES ?s {{ {iri(source).n3()} }}")
    if batiment:
        valeurs.append(f"VALUES ?b {{ {iri(batiment).n3()} }}")
    return f"""
SELECT DISTINCT ?s ?b ?via ?par WHERE {{
  {" ".join(valeurs)}
  ?s a/rdfs:subClassOf* sg:SourceEnergie .
  {chemins()}
}}"""


def liens(source_id):
    """Ce qui gravite autour d'une source dans les autres modules (lecture seule)."""
    s = iri(source_id).n3()
    return f"""
SELECT DISTINCT ?relation ?x ?label ?valeur ?debut ?fin ?tension WHERE {{
  {{ {s} sg:injecteDans ?x . BIND("ligne" AS ?relation) OPTIONAL {{ ?x sg:tension ?tension }} }}
  UNION {{ {{ ?x sg:stockeEnergieDe {s} }} UNION {{ {s} sg:estStockePar ?x }} BIND("stockage" AS ?relation) }}
  UNION {{ ?x sg:concerne {s} ; a/rdfs:subClassOf* sg:Mesure . BIND("mesure" AS ?relation)
           OPTIONAL {{ ?x sg:valeurKWh ?valeur }} OPTIONAL {{ ?x sg:dateDebut ?debut }} OPTIONAL {{ ?x sg:dateFin ?fin }} }}
  OPTIONAL {{ ?x rdfs:label ?label }}
}}"""


def references(source_id):
    """Toutes les relations entrantes (IRI) et sortantes de la source, pour décider d'une suppression."""
    s = iri(source_id).n3()
    return f"""
SELECT ?sens ?relation ?x WHERE {{
  {{ ?x ?p {s} . FILTER(isIRI(?x) && ?p != rdf:type) BIND("entrante" AS ?sens) }}
  UNION {{ {s} ?p ?x . BIND("sortante" AS ?sens) }}
  BIND(STRAFTER(STR(?p), "#") AS ?relation)
}}"""


def stockages_contraignants(source_id):
    """Stockages dont la classe impose « stockeEnergieDe only C » (ex. STEP ⊑ … only SourceRenouvelable)."""
    s = iri(source_id).n3()
    return f"""
SELECT DISTINCT ?x ?classeStockage ?c WHERE {{
  {{ ?x sg:stockeEnergieDe {s} }} UNION {{ {s} sg:estStockePar ?x }}
  ?x a/rdfs:subClassOf* ?classeStockage .
  ?classeStockage rdfs:subClassOf ?r .
  ?r owl:onProperty sg:stockeEnergieDe ; owl:allValuesFrom ?c .
}}"""


def ask_sous_classe(classe, parent):
    return f"ASK {{ sg:{classe} rdfs:subClassOf* sg:{parent} }}"


def ask_type(individu_id, classe):
    return f"ASK {{ {iri(individu_id).n3()} a/rdfs:subClassOf* sg:{classe} }}"


def ask_existe(individu_id):
    return f"ASK {{ {{ {iri(individu_id).n3()} ?p ?o }} UNION {{ ?s ?p {iri(individu_id).n3()} }} }}"


def ask_label_pris(label, sauf_id=None):
    sauf = f"FILTER(?x != {iri(sauf_id).n3()})" if sauf_id else ""
    return f"""ASK {{
  ?x a/rdfs:subClassOf* sg:SourceEnergie ; rdfs:label ?l .
  FILTER(LCASE(STR(?l)) = {Literal(label.strip().lower()).n3()})
  {sauf}
}}"""


# ------------------------------------------------------- vue d'ensemble ----

STATISTIQUES = f"""
SELECT (COUNT(?s) AS ?nb) (SUM(IF(?renouvelable, 1, 0)) AS ?nbRenouvelables)
       (SUM(IF(?nonRenouvelable, 1, 0)) AS ?nbNonRenouvelables)
       (COUNT(?puissance) AS ?nbAvecPuissance) (SUM(?puissance) AS ?puissanceTotale)
WHERE {{
  {{ SELECT DISTINCT ?s ?puissance ?renouvelable ?nonRenouvelable WHERE {{
    ?s a/rdfs:subClassOf* sg:SourceEnergie .
    OPTIONAL {{ ?s sg:puissanceInstallee ?puissance }}
    {FAMILLES}
  }} }}
}}"""

PAR_TYPE = f"""
SELECT ?type (COUNT(?s) AS ?nb) (COUNT(?puissance) AS ?nbAvecPuissance) (SUM(?puissance) AS ?puissance)
WHERE {{
  {{ SELECT DISTINCT ?s ?type ?puissance WHERE {{
    {TYPE_PRECIS}
    OPTIONAL {{ ?s sg:puissanceInstallee ?puissance }}
  }} }}
}}
GROUP BY ?type
ORDER BY DESC(?puissance)"""

# Énergie MESURÉE (kWh) : uniquement les mesures de production existantes, jamais déduite de la puissance
ENERGIE_MESUREE = """
SELECT (COUNT(?m) AS ?nbMesures) (SUM(?v) AS ?totalKWh) (MIN(?d) AS ?debut) (MAX(?f) AS ?fin)
       (COUNT(DISTINCT ?s) AS ?nbSources)
WHERE {
  { SELECT DISTINCT ?m ?s ?v ?d ?f WHERE {
    ?m a sg:MesureProduction ; sg:concerne ?s ; sg:valeurKWh ?v ; sg:dateDebut ?d ; sg:dateFin ?f .
    ?s a/rdfs:subClassOf* sg:SourceEnergie .
  } }
}"""

CHEVAUCHEMENTS = """
SELECT DISTINCT ?m1 ?m2 ?s WHERE {
  ?m1 a sg:MesureProduction ; sg:concerne ?s ; sg:dateDebut ?d1 ; sg:dateFin ?f1 .
  ?m2 a sg:MesureProduction ; sg:concerne ?s ; sg:dateDebut ?d2 ; sg:dateFin ?f2 .
  FILTER(STR(?m1) < STR(?m2) && ?d1 <= ?f2 && ?d2 <= ?f1)
}"""

OPTIONS = """
SELECT ?id ?label ?groupe ?classe ?tension WHERE {
  {
    ?x a ?classe . ?classe rdfs:subClassOf* sg:LigneElectrique . BIND("lignes" AS ?groupe)
    OPTIONAL { ?x sg:tension ?tension }
  } UNION {
    ?x a ?classe . ?classe rdfs:subClassOf* sg:Batiment . BIND("batiments" AS ?groupe)
  } UNION {
    ?x a ?classe . ?classe rdfs:subClassOf* sg:SourceEnergie . BIND("sources" AS ?groupe)
  }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  BIND(STRAFTER(STR(?x), "#") AS ?id)
}
ORDER BY ?groupe ?label"""


# ------------------------------------------------------------- écriture --

def _triplets(d):
    s = iri(d["id"]).n3()
    t = [f"{s} a owl:NamedIndividual, sg:{d['type']}",
         f"{s} rdfs:label {n3_label(d['label'])}"]
    if d.get("puissance") is not None:
        t.append(f"{s} sg:puissanceInstallee {n3_float(d['puissance'])}")
    if d.get("date"):
        t.append(f"{s} sg:dateMiseEnService {n3_date(d['date'])}")
    t += [f"{s} sg:injecteDans {iri(l).n3()}" for l in d["lignes"]]
    t += [f"{s} sg:produitEnergiePour {iri(b).n3()}" for b in d["batiments"]]
    return " .\n  ".join(t) + " ."


def creer(d):
    return f"INSERT DATA {{\n  {_triplets(d)}\n}}"


def modifier(d):
    """Réécrit uniquement les triplets possédés par Production (type de la hiérarchie, libellé,
    puissance, date, injecteDans, produitEnergiePour). Les estAlimentePar du module Bâtiments,
    les stockeEnergieDe du Stockage et les concerne des mesures ne sont pas touchés."""
    s = iri(d["id"]).n3()
    types = ", ".join(f"sg:{t}" for t in TYPES)
    return f"""
DELETE {{ {s} a ?t ; rdfs:label ?l ; sg:puissanceInstallee ?p ; sg:dateMiseEnService ?d ;
             sg:injecteDans ?li ; sg:produitEnergiePour ?b }}
WHERE  {{ OPTIONAL {{ {s} a ?t . FILTER(?t IN ({types})) }}
          OPTIONAL {{ {s} rdfs:label ?l }} OPTIONAL {{ {s} sg:puissanceInstallee ?p }}
          OPTIONAL {{ {s} sg:dateMiseEnService ?d }} OPTIONAL {{ {s} sg:injecteDans ?li }}
          OPTIONAL {{ {s} sg:produitEnergiePour ?b }} }} ;
INSERT DATA {{\n  {_triplets(d)}\n}}"""


def supprimer(source_id):
    """Appelé seulement si aucune référence d'un autre module n'existe (vérifié dans routes.py)."""
    s = iri(source_id).n3()
    return f"DELETE WHERE {{ {s} ?p ?o }}"
