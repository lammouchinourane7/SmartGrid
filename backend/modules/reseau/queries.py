"""Requêtes SPARQL du module Réseau (Membre 4 · Nourane Lammouchi).

Classes : InfrastructureReseau, LigneElectrique, LigneHauteTension (≡),
LigneMoyenneTension (≡), LigneBasseTension (≡), PosteElectrique.

RDFLib n'exécute ni HermiT ni SWRL : les connaissances déduites sont donc
réécrites directement en SPARQL, au plus près des axiomes de l'ontologie :
  - LigneHauteTension ≡ LigneElectrique ⊓ tension some float[≥ 63]
  - LigneMoyenneTension ≡ LigneElectrique ⊓ tension some float[> 1, < 63]
  - LigneBasseTension ≡ LigneElectrique ⊓ tension some float[≤ 1]
  - relie / estReliePar sont inverses        → on lit ?ligne sg:relie ?poste
  - estConnecteA est symétrique            → UNION dans les deux sens
  - R3 : estRaccordeA ∘ relie → estDesserviPar
  - R4 : gere(o, p) ∧ relie(l, p) → gere(o, l)
"""
from rdflib import Literal
from rdflib.namespace import XSD

from store import iri, n3_float, n3_label

# ---------------------------------------------------------------- lecture --


def ids(var, alias):
    """Concatène les identifiants locaux d'une variable OPTIONAL.

    COALESCE contourne un bug de RDFLib : GROUP_CONCAT(DISTINCT ...) plante
    quand la variable n'est pas liée.
    """
    return (f'(GROUP_CONCAT(DISTINCT COALESCE(STRAFTER(STR(?{var}), "#"), ""); '
            f'separator="|") AS ?{alias})')


CATEGORIE = """BIND(IF(BOUND(?tension) && ?tension >= 63, "HT",
               IF(BOUND(?tension) && ?tension <= 1, "BT", "MT")) AS ?categorie)"""


def lister_lignes(q=None, categorie=None, tension_min=None, tension_max=None, poste=None):
    """SELECT + filtres : recherche texte, catégorie déduite, plage de tension, poste."""
    filters = []
    if q:
        needle = Literal(q.lower()).n3()
        filters.append(f"FILTER(CONTAINS(LCASE(STR(?label)), {needle}) "
                       f"|| CONTAINS(LCASE(STRAFTER(STR(?ligne), \"#\")), {needle}))")
    if categorie in ("HT", "MT", "BT"):
        filters.append(f'FILTER(?categorie = "{categorie}")')
    if tension_min is not None:
        filters.append(f"FILTER(?tension >= {float(tension_min)})")
    if tension_max is not None:
        filters.append(f"FILTER(?tension <= {float(tension_max)})")
    if poste:
        filters.append(f"FILTER EXISTS {{ ?ligne sg:relie {iri(poste).n3()} }}")

    return f"""
SELECT ?ligne ?label ?tension ?longueur ?annee ?categorie
       {ids("poste", "postes")}
       {ids("bat", "batiments")}
       {ids("op", "gestionnaires")}
WHERE {{
  ?ligne a/rdfs:subClassOf* sg:LigneElectrique .
  OPTIONAL {{ ?ligne rdfs:label ?label }}
  OPTIONAL {{ ?ligne sg:tension ?tension }}
  OPTIONAL {{ ?ligne sg:longueur ?longueur }}
  OPTIONAL {{ ?ligne sg:anneeMiseEnService ?annee }}
  OPTIONAL {{ ?ligne sg:relie ?poste }}
  OPTIONAL {{ ?ligne sg:transporteVers ?bat }}
  # R4 : un opérateur qui gère un poste gère aussi les lignes reliées à ce poste
  OPTIONAL {{ {{ ?op sg:gere ?ligne }} UNION {{ ?op sg:gere ?pg . ?ligne sg:relie ?pg }} }}
  {CATEGORIE}
  {chr(10).join("  " + f for f in filters)}
}}
GROUP BY ?ligne ?label ?tension ?longueur ?annee ?categorie
ORDER BY DESC(?tension)"""


def detail_ligne(ligne_id):
    """Ce qui gravite autour d'une ligne : sources qui y injectent, bâtiments raccordés."""
    return f"""
SELECT ?relation ?cible WHERE {{
  {{ ?cible sg:injecteDans {iri(ligne_id).n3()} . BIND("injecteDans" AS ?relation) }}
  UNION
  {{ ?cible sg:estRaccordeA {iri(ligne_id).n3()} . BIND("estRaccordeA" AS ?relation) }}
}}"""


def lister_postes(q=None):
    filtre = ""
    if q:
        needle = Literal(q.lower()).n3()
        filtre = (f"FILTER(CONTAINS(LCASE(STR(?label)), {needle}) "
                  f"|| CONTAINS(LCASE(STR(?ville)), {needle}) "
                  f"|| CONTAINS(LCASE(STRAFTER(STR(?poste), \"#\")), {needle}))")
    return f"""
SELECT ?poste ?label ?ville ?capacite ?annee (COUNT(DISTINCT ?ligne) AS ?nbLignes)
       {ids("ligne", "lignes")}
       {ids("voisin", "connexions")}
       {ids("secouru", "secours")}
       {ids("secouriste", "secourusPar")}
       {ids("op", "gestionnaires")}
       {ids("bat", "batimentsDesservis")}
WHERE {{
  ?poste a sg:PosteElectrique .
  OPTIONAL {{ ?poste rdfs:label ?label }}
  OPTIONAL {{ ?poste sg:ville ?ville }}
  OPTIONAL {{ ?poste sg:capaciteTransformation ?capacite }}
  OPTIONAL {{ ?poste sg:anneeMiseEnService ?annee }}
  OPTIONAL {{ ?ligne sg:relie ?poste }}
  OPTIONAL {{ ?poste sg:secourt ?secouru }}
  OPTIONAL {{ ?secouriste sg:secourt ?poste }}
  # estConnecteA est symétrique : on lit la relation dans les deux sens
  OPTIONAL {{ {{ ?poste sg:estConnecteA ?voisin }} UNION {{ ?voisin sg:estConnecteA ?poste }} }}
  OPTIONAL {{ ?op sg:gere ?poste }}
  # R3 : un bâtiment raccordé à une ligne est desservi par le poste de cette ligne
  OPTIONAL {{ ?bat sg:estRaccordeA ?lr . ?lr sg:relie ?poste }}
  {filtre}
}}
GROUP BY ?poste ?label ?ville ?capacite ?annee
ORDER BY DESC(?nbLignes) ?label"""


STATISTIQUES = f"""
SELECT (COUNT(DISTINCT ?ligne) AS ?nbLignes)
       (SUM(?longueur) AS ?longueurTotale)
       (MAX(?tension) AS ?tensionMax)
       (SUM(IF(?categorie = "HT", 1, 0)) AS ?nbHT)
       (SUM(IF(?categorie = "MT", 1, 0)) AS ?nbMT)
       (SUM(IF(?categorie = "BT", 1, 0)) AS ?nbBT)
WHERE {{
  ?ligne a/rdfs:subClassOf* sg:LigneElectrique .
  OPTIONAL {{ ?ligne sg:tension ?tension }}
  OPTIONAL {{ ?ligne sg:longueur ?longueur }}
  {CATEGORIE}
}}"""

NB_POSTES = "SELECT (COUNT(DISTINCT ?p) AS ?n) WHERE { ?p a sg:PosteElectrique }"

OPTIONS = """
SELECT ?id ?label ?groupe WHERE {
  {
    ?x a sg:PosteElectrique . BIND("postes" AS ?groupe)
  } UNION {
    ?x a/rdfs:subClassOf* sg:Batiment . BIND("batiments" AS ?groupe)
  } UNION {
    ?x a sg:OperateurReseau . BIND("operateurs" AS ?groupe)
  } UNION {
    ?x a/rdfs:subClassOf* sg:SourceEnergie . BIND("sources" AS ?groupe)
  }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  BIND(STRAFTER(STR(?x), "#") AS ?id)
}
ORDER BY ?groupe ?label"""

GRAPHE = """
SELECT DISTINCT ?s ?relation ?o WHERE {
  {
    ?s sg:relie ?o . BIND("relie" AS ?relation)
  } UNION {
    ?s sg:estConnecteA ?o . BIND("estConnecteA" AS ?relation)
  } UNION {
    ?s sg:transporteVers ?o . BIND("transporteVers" AS ?relation)
  } UNION {
    ?o sg:estRaccordeA ?s . BIND("estRaccordeA" AS ?relation)
  } UNION {
    ?s sg:injecteDans ?o . BIND("injecteDans" AS ?relation)
  }
}"""


def ask_type(individu_id, classe):
    return f"ASK {{ {iri(individu_id).n3()} a/rdfs:subClassOf* sg:{classe} }}"


def ask_existe(individu_id):
    return f"ASK {{ {{ {iri(individu_id).n3()} ?p ?o }} UNION {{ ?s ?p {iri(individu_id).n3()} }} }}"


def dependances(individu_id):
    """Qui pointe vers cet individu ? (utilisé avant une suppression)"""
    return f"""
SELECT ?s ?relation WHERE {{
  ?s ?p {iri(individu_id).n3()} .
  FILTER(isIRI(?s) && ?p != rdf:type)
  BIND(STRAFTER(STR(?p), "#") AS ?relation)
}}"""


def lignes_orphelines(poste_id):
    """Lignes dont ce poste est l'unique poste : LigneElectrique ⊑ relie min 1 PosteElectrique."""
    return f"""
SELECT ?ligne WHERE {{
  ?ligne sg:relie {iri(poste_id).n3()} .
  FILTER NOT EXISTS {{ ?ligne sg:relie ?autre . FILTER(?autre != {iri(poste_id).n3()}) }}
}}"""

def ask_label_pris(label, classe, sauf_id=None):
    """Un autre individu de la même classe porte-t-il déjà ce libellé ?"""
    sauf = f"FILTER(?x != {iri(sauf_id).n3()})" if sauf_id else ""
    return f"""ASK {{
  ?x a sg:{classe} ; rdfs:label ?l .
  FILTER(LCASE(STR(?l)) = {Literal(label.strip().lower()).n3()})
  {sauf}
}}"""


def ask_secourt(de_id, vers_id):
    return f"ASK {{ {iri(de_id).n3()} sg:secourt {iri(vers_id).n3()} }}"

# ------------------------------------------------------------- écriture --


def _int(value):
    return Literal(int(value), datatype=XSD.integer).n3()


def _str(value):
    return Literal(value, datatype=XSD.string).n3()


def _triplets_ligne(d):
    s = iri(d["id"]).n3()
    t = [f"{s} a owl:NamedIndividual, sg:LigneElectrique",
         f"{s} rdfs:label {n3_label(d['label'])}",
         f"{s} sg:tension {n3_float(d['tension'])}"]
    if d.get("longueur") is not None:
        t.append(f"{s} sg:longueur {n3_float(d['longueur'])}")
    if d.get("annee") is not None:
        t.append(f"{s} sg:anneeMiseEnService {_int(d['annee'])}")
    t += [f"{s} sg:relie {iri(p).n3()}" for p in d["postes"]]
    t += [f"{s} sg:transporteVers {iri(b).n3()}" for b in d.get("batiments", [])]
    return " .\n  ".join(t) + " ."


def creer_ligne(d):
    return f"INSERT DATA {{\n  {_triplets_ligne(d)}\n}}"


def modifier_ligne(d):
    s = iri(d["id"]).n3()
    return f"""
DELETE {{ {s} rdfs:label ?a ; sg:tension ?t ; sg:longueur ?lo ; sg:anneeMiseEnService ?an ;
             sg:relie ?p ; sg:transporteVers ?b }}
WHERE  {{ OPTIONAL {{ {s} rdfs:label ?a }} OPTIONAL {{ {s} sg:tension ?t }}
          OPTIONAL {{ {s} sg:longueur ?lo }} OPTIONAL {{ {s} sg:anneeMiseEnService ?an }}
          OPTIONAL {{ {s} sg:relie ?p }} OPTIONAL {{ {s} sg:transporteVers ?b }} }} ;
INSERT DATA {{\n  {_triplets_ligne(d)}\n}}"""


def _triplets_poste(d):
    s = iri(d["id"]).n3()
    t = [f"{s} a owl:NamedIndividual, sg:PosteElectrique",
         f"{s} rdfs:label {n3_label(d['label'])}"]
    if d.get("ville"):
        t.append(f"{s} sg:ville {_str(d['ville'])}")
    if d.get("capacite") is not None:
        t.append(f"{s} sg:capaciteTransformation {n3_float(d['capacite'])}")
    if d.get("annee") is not None:
        t.append(f"{s} sg:anneeMiseEnService {_int(d['annee'])}")
    t += [f"{s} sg:estConnecteA {iri(p).n3()}" for p in d.get("connexions", [])]
    t += [f"{s} sg:secourt {iri(p).n3()}" for p in d.get("secours", [])]
    t += [f"{iri(o).n3()} sg:gere {s}" for o in d.get("gestionnaires", [])]
    return " .\n  ".join(t) + " ."


def creer_poste(d):
    return f"INSERT DATA {{\n  {_triplets_poste(d)}\n}}"


def modifier_poste(d):
    s = iri(d["id"]).n3()
    return f"""
DELETE {{ {s} rdfs:label ?a ; sg:ville ?vi ; sg:capaciteTransformation ?c ; sg:anneeMiseEnService ?an ;
             sg:estConnecteA ?v1 ; sg:secourt ?se .
         ?v2 sg:estConnecteA {s} . ?o sg:gere {s} }}
WHERE  {{ OPTIONAL {{ {s} rdfs:label ?a }} OPTIONAL {{ {s} sg:ville ?vi }}
          OPTIONAL {{ {s} sg:capaciteTransformation ?c }} OPTIONAL {{ {s} sg:anneeMiseEnService ?an }}
          OPTIONAL {{ {s} sg:estConnecteA ?v1 }} OPTIONAL {{ ?v2 sg:estConnecteA {s} }}
          OPTIONAL {{ {s} sg:secourt ?se }} OPTIONAL {{ ?o sg:gere {s} }} }} ;
INSERT DATA {{\n  {_triplets_poste(d)}\n}}"""


def supprimer(individu_id):
    s = iri(individu_id).n3()
    return f"DELETE WHERE {{ {s} ?p ?o }} ;\nDELETE WHERE {{ ?x ?p {s} }}"
