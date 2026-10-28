"""Requêtes SPARQL du module Stockage (Membre 2 · Takoua Naceur).

Classes : SystemeStockage, Batterie, BatterieLithiumIon, BatteriePlomb,
StockageHydrogene, STEP, VolantInertie + 4 classes définies (≡).

RDFLib n'exécute ni HermiT ni SWRL : les connaissances déduites sont réécrites
en SPARQL, au plus près des axiomes de l'ontologie :
  - StockageVert ≡ SystemeStockage ⊓ stockeEnergieDe some SourceRenouvelable
  - StockageCritique ≡ SystemeStockage ⊓ niveauCharge some float[< 20]
  - StockageGrandeCapacite ≡ SystemeStockage ⊓ capaciteStockage some float[≥ 10000]
  - StockageSecours ≡ SystemeStockage ⊓ alimente some BatimentPublic
  - R2 : SystemeStockage(?x) ∧ alimente(?x, ?b) → possedeStockage(?b, ?x)
  - R6 : stockeEnergieDe(?x, ?s) ∧ alimente(?x, ?b) → estAlimentePar(?b, ?s)
  - BatimentAutonome ≡ Batiment ⊓ estAlimentePar some SourceRenouvelable
                                ⊓ possedeStockage some SystemeStockage
"""
from rdflib import Literal
from rdflib.namespace import XSD

from store import iri, n3_float, n3_label

FAMILLES = ("Batterie", "StockageHydrogene", "STEP", "VolantInertie")
CLASSES = ("Batterie", "BatterieLithiumIon", "BatteriePlomb", "StockageHydrogene", "STEP", "VolantInertie")
DEFINIES = {
    "vert": "StockageVert",
    "critique": "StockageCritique",
    "grande": "StockageGrandeCapacite",
    "secours": "StockageSecours",
}
SEUIL_CRITIQUE = 20      # %
SEUIL_GRANDE = 10000     # kWh


def ids(var, alias):
    """Concatène les identifiants locaux d'une variable OPTIONAL (contourne un bug RDFLib)."""
    return (f'(GROUP_CONCAT(DISTINCT COALESCE(STRAFTER(STR(?{var}), "#"), ""); '
            f'separator="|") AS ?{alias})')


# Les 4 classes définies, réécrites en expressions SPARQL (une variable booléenne chacune)
INFERENCES = f"""
  # StockageVert ≡ SystemeStockage ⊓ stockeEnergieDe some SourceRenouvelable
  BIND(EXISTS {{ ?x sg:stockeEnergieDe ?sv . ?sv a/rdfs:subClassOf* sg:SourceRenouvelable }} AS ?vert)
  # StockageCritique ≡ SystemeStockage ⊓ niveauCharge some float[< {SEUIL_CRITIQUE}]
  BIND(BOUND(?niveau) && ?niveau < {SEUIL_CRITIQUE} AS ?critique)
  # StockageGrandeCapacite ≡ SystemeStockage ⊓ capaciteStockage some float[≥ {SEUIL_GRANDE}]
  BIND(BOUND(?capacite) && ?capacite >= {SEUIL_GRANDE} AS ?grande)
  # StockageSecours ≡ SystemeStockage ⊓ alimente some BatimentPublic
  BIND(EXISTS {{ ?x sg:alimente ?bp . ?bp a/rdfs:subClassOf* sg:BatimentPublic }} AS ?secours)
  # énergie disponible (kWh) et autonomie à pleine puissance (h)
  BIND(IF(BOUND(?capacite) && BOUND(?niveau), ?capacite * ?niveau / 100, ?unbound) AS ?energie)
  BIND(IF(BOUND(?energie) && BOUND(?puissance) && ?puissance > 0, ?energie / ?puissance, ?unbound) AS ?autonomie)"""

CLASSE_LA_PLUS_PRECISE = """
  ?x a ?classe . ?classe rdfs:subClassOf* sg:SystemeStockage .
  FILTER NOT EXISTS { ?x a ?autre . ?autre rdfs:subClassOf+ ?classe . FILTER(?autre != ?classe) }
  OPTIONAL { ?classe rdfs:subClassOf* ?famille . VALUES ?famille { sg:Batterie sg:StockageHydrogene sg:STEP sg:VolantInertie } }"""


def lister(q=None, famille=None, definie=None, niveau_min=None, niveau_max=None,
           capacite_min=None, source=None, batiment=None, poste=None, renouvelable=None):
    """SELECT + filtres : texte, famille, classe définie, plages numériques, relations."""
    filters = []
    if q:
        needle = Literal(q.lower()).n3()
        filters.append(f"FILTER(CONTAINS(LCASE(STR(?label)), {needle}) "
                       f"|| CONTAINS(LCASE(STRAFTER(STR(?x), \"#\")), {needle}) "
                       f"|| CONTAINS(LCASE(STR(?techno)), {needle}))")
    if famille in FAMILLES:
        filters.append(f"FILTER(?famille = sg:{famille})")
    if definie in DEFINIES:
        filters.append(f"FILTER(?{definie})  # individu de sg:{DEFINIES[definie]}")
    if niveau_min is not None:
        filters.append(f"FILTER(?niveau >= {float(niveau_min)})")
    if niveau_max is not None:
        filters.append(f"FILTER(?niveau <= {float(niveau_max)})")
    if capacite_min is not None:
        filters.append(f"FILTER(?capacite >= {float(capacite_min)})")
    if source:
        filters.append(f"FILTER EXISTS {{ ?x sg:stockeEnergieDe {iri(source).n3()} }}")
    if batiment:
        filters.append(f"FILTER EXISTS {{ ?x sg:alimente {iri(batiment).n3()} }}")
    if poste:
        filters.append(f"FILTER EXISTS {{ ?x sg:raccordeAuPoste {iri(poste).n3()} }}")
    if renouvelable is False:
        filters.append("FILTER(!?vert)")

    return f"""
SELECT ?x ?label ?classe ?famille ?capacite ?niveau ?rendement ?puissance ?techno ?annee ?poste
       ?vert ?critique ?grande ?secours ?energie ?autonomie
       {ids("src", "sources")}
       {ids("bat", "batiments")}
WHERE {{
  ?x a/rdfs:subClassOf* sg:SystemeStockage .
  {CLASSE_LA_PLUS_PRECISE}
  OPTIONAL {{ ?x rdfs:label ?label }}
  OPTIONAL {{ ?x sg:capaciteStockage ?capacite }}
  OPTIONAL {{ ?x sg:niveauCharge ?niveau }}
  OPTIONAL {{ ?x sg:rendement ?rendement }}
  OPTIONAL {{ ?x sg:puissanceDecharge ?puissance }}
  OPTIONAL {{ ?x sg:technologie ?techno }}
  OPTIONAL {{ ?x sg:anneeInstallation ?annee }}
  OPTIONAL {{ ?x sg:raccordeAuPoste ?poste }}
  OPTIONAL {{ ?x sg:stockeEnergieDe ?src }}
  OPTIONAL {{ ?x sg:alimente ?bat }}
  {INFERENCES}
  {chr(10).join("  " + f for f in filters)}
}}
GROUP BY ?x ?label ?classe ?famille ?capacite ?niveau ?rendement ?puissance ?techno ?annee ?poste
         ?vert ?critique ?grande ?secours ?energie ?autonomie
ORDER BY DESC(?capacite)"""


STATISTIQUES = f"""
SELECT (COUNT(DISTINCT ?x) AS ?nb)
       (SUM(?capacite) AS ?capaciteTotale)
       (SUM(?energie) AS ?energieDisponible)
       (AVG(?niveau) AS ?chargeMoyenne)
       (SUM(IF(?critique, 1, 0)) AS ?nbCritiques)
       (SUM(IF(?vert, 1, 0)) AS ?nbVerts)
       (SUM(IF(?grande, 1, 0)) AS ?nbGrands)
       (SUM(IF(?secours, 1, 0)) AS ?nbSecours)
WHERE {{
  ?x a/rdfs:subClassOf* sg:SystemeStockage .
  FILTER EXISTS {{ ?x a owl:NamedIndividual }}
  OPTIONAL {{ ?x sg:capaciteStockage ?capacite }}
  OPTIONAL {{ ?x sg:niveauCharge ?niveau }}
  OPTIONAL {{ ?x sg:puissanceDecharge ?puissance }}
  {INFERENCES}
}}"""

PAR_FAMILLE = """
SELECT ?famille (COUNT(DISTINCT ?x) AS ?nb) (SUM(?capacite) AS ?capacite) WHERE {
  ?x a ?classe . ?classe rdfs:subClassOf* ?famille .
  VALUES ?famille { sg:Batterie sg:StockageHydrogene sg:STEP sg:VolantInertie }
  OPTIONAL { ?x sg:capaciteStockage ?capacite }
}
GROUP BY ?famille"""

OPTIONS = """
SELECT ?id ?label ?groupe ?renouvelable WHERE {
  {
    ?x a/rdfs:subClassOf* sg:SourceEnergie . BIND("sources" AS ?groupe)
    BIND(EXISTS { ?x a/rdfs:subClassOf* sg:SourceRenouvelable } AS ?renouvelable)
  } UNION {
    ?x a/rdfs:subClassOf* sg:Batiment . BIND("batiments" AS ?groupe)
  } UNION {
    ?x a sg:PosteElectrique . BIND("postes" AS ?groupe)
  }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  BIND(STRAFTER(STR(?x), "#") AS ?id)
}
ORDER BY ?groupe ?label"""


# ------------------------------------------------- bâtiments et inférences --

BATIMENTS_AUTONOMES = """
SELECT ?b ?label ?classe ?conso ?stockages ?energie
       (GROUP_CONCAT(DISTINCT CONCAT(STRAFTER(STR(?s), "#"), "@", ?via); separator="|") AS ?sourcesRenouvelables)
WHERE {
  {
    # sous-requête : stockages possédés et énergie disponible, agrégés par bâtiment
    SELECT ?b ?classe
           (GROUP_CONCAT(DISTINCT COALESCE(STRAFTER(STR(?x), "#"), ""); separator="|") AS ?stockages)
           (SUM(?energieX) AS ?energie)
    WHERE {
      ?b a ?classe ; a owl:NamedIndividual . ?classe rdfs:subClassOf* sg:Batiment .
      FILTER NOT EXISTS { ?b a ?autre . ?autre rdfs:subClassOf+ ?classe . FILTER(?autre != ?classe) }
      # R2 : SystemeStockage(?x) ∧ alimente(?x, ?b) → possedeStockage(?b, ?x)
      OPTIONAL {
        { SELECT DISTINCT ?b ?x WHERE { { ?x sg:alimente ?b } UNION { ?b sg:possedeStockage ?x } } }
        OPTIONAL { ?x sg:capaciteStockage ?c . ?x sg:niveauCharge ?n . BIND(?c * ?n / 100 AS ?energieX) }
      }
    }
    GROUP BY ?b ?classe
  }
  OPTIONAL { ?b rdfs:label ?label }
  OPTIONAL { ?b sg:consommationAnnuelle ?conso }
  # estAlimentePar some SourceRenouvelable, par quatre chemins
  OPTIONAL {
    { ?b sg:estAlimentePar ?s . BIND("direct" AS ?via) }
    UNION { ?s sg:produitEnergiePour ?b . BIND("inverse" AS ?via) }                 # owl:inverseOf
    UNION { ?s sg:injecteDans ?l . ?l sg:transporteVers ?b . BIND("R1" AS ?via) }  # règle R1
    UNION { ?xs sg:alimente ?b ; sg:stockeEnergieDe ?s . BIND("R6" AS ?via) }      # règle R6
    ?s a/rdfs:subClassOf* sg:SourceRenouvelable .
  }
}
GROUP BY ?b ?label ?classe ?conso ?stockages ?energie
ORDER BY ?label"""


# ------------------------------------------------------ scénario coupure --

def scenario_coupure(poste=None):
    """Bâtiments touchés par une coupure (R3), leur stockage (R2) et leur énergie disponible."""
    if poste:
        p = iri(poste).n3()
        perimetre = (f"# R3 : estRaccordeA ∘ relie → estDesserviPar\n"
                     f"      {{ ?b sg:estRaccordeA ?l . ?l sg:relie {p} }}\n"
                     f"      UNION {{ ?l sg:transporteVers ?b . ?l sg:relie {p} }}")
    else:
        perimetre = "?b a/rdfs:subClassOf* sg:Batiment .   # coupure générale"
    return f"""
SELECT ?b ?label ?conso
       (SUM(?energieX) AS ?energie)
       (SUM(?puissanceX) AS ?puissance)
       (GROUP_CONCAT(DISTINCT COALESCE(STRAFTER(STR(?x), "#"), ""); separator="|") AS ?stockages)
WHERE {{
  {{
    SELECT DISTINCT ?b ?x ?energieX ?puissanceX WHERE {{
      ?b a owl:NamedIndividual .
      {perimetre}
      # R2 : le bâtiment possède les stockages qui l'alimentent
      OPTIONAL {{
        {{ ?x sg:alimente ?b }} UNION {{ ?b sg:possedeStockage ?x }}
        OPTIONAL {{ ?x sg:capaciteStockage ?c . ?x sg:niveauCharge ?n . BIND(?c * ?n / 100 AS ?energieX) }}
        OPTIONAL {{ ?x sg:puissanceDecharge ?puissanceX }}
      }}
    }}
  }}
  OPTIONAL {{ ?b rdfs:label ?label }}
  OPTIONAL {{ ?b sg:consommationAnnuelle ?conso }}
}}
GROUP BY ?b ?label ?conso
ORDER BY ?label"""


def stockages_du_poste(poste):
    return f"""
SELECT ?x ?label ?capacite ?niveau ?puissance WHERE {{
  ?x sg:raccordeAuPoste {iri(poste).n3()} .
  FILTER NOT EXISTS {{ ?x sg:alimente ?b }}   # stockage réseau, pas dédié à un bâtiment
  OPTIONAL {{ ?x rdfs:label ?label }}
  OPTIONAL {{ ?x sg:capaciteStockage ?capacite }}
  OPTIONAL {{ ?x sg:niveauCharge ?niveau }}
  OPTIONAL {{ ?x sg:puissanceDecharge ?puissance }}
}}"""


# ----------------------------------------------------------- vérifications --

def ask_type(individu_id, classe):
    return f"ASK {{ {iri(individu_id).n3()} a/rdfs:subClassOf* sg:{classe} }}"


def ask_existe(individu_id):
    return f"ASK {{ {{ {iri(individu_id).n3()} ?p ?o }} UNION {{ ?s ?p {iri(individu_id).n3()} }} }}"


def ask_label_pris(label, sauf_id=None):
    sauf = f"FILTER(?x != {iri(sauf_id).n3()})" if sauf_id else ""
    return f"""ASK {{
  ?x a/rdfs:subClassOf* sg:SystemeStockage ; rdfs:label ?l .
  FILTER(LCASE(STR(?l)) = {Literal(label.strip().lower()).n3()})
  {sauf}
}}"""


def dependances(individu_id):
    """Qui pointe vers ce stockage ? (utilisé avant une suppression)"""
    return f"""
SELECT ?s ?relation WHERE {{
  ?s ?p {iri(individu_id).n3()} .
  FILTER(isIRI(?s) && ?p != rdf:type)
  BIND(STRAFTER(STR(?p), "#") AS ?relation)
}}"""


def detail(individu_id):
    """Les triplets d'un individu, dans les deux sens (vue « fiche RDF »)."""
    s = iri(individu_id).n3()
    return f"""
SELECT ?sens ?propriete ?valeur WHERE {{
  {{ {s} ?p ?v . BIND("sortant" AS ?sens) }}
  UNION
  {{ ?v ?p {s} . FILTER(isIRI(?v)) BIND("entrant" AS ?sens) }}
  FILTER(?p != rdf:type || isIRI(?v) && STRSTARTS(STR(?v), STR(sg:)))
  BIND(STRAFTER(STR(?p), "#") AS ?propriete)
  BIND(IF(isIRI(?v), STRAFTER(STR(?v), "#"), STR(?v)) AS ?valeur)
}}
ORDER BY ?sens ?propriete"""


# --------------------------------------------------------------- écriture --

def _int(value):
    return Literal(int(value), datatype=XSD.integer).n3()


def _str(value):
    return Literal(value, datatype=XSD.string).n3()


def _triplets(d):
    s = iri(d["id"]).n3()
    t = [f"{s} a owl:NamedIndividual, sg:{d['classe']}",
         f"{s} rdfs:label {n3_label(d['label'])}",
         f"{s} sg:capaciteStockage {n3_float(d['capacite'])}"]
    for champ, prop in (("niveau", "niveauCharge"), ("rendement", "rendement"),
                        ("puissance", "puissanceDecharge")):
        if d.get(champ) is not None:
            t.append(f"{s} sg:{prop} {n3_float(d[champ])}")
    if d.get("technologie"):
        t.append(f"{s} sg:technologie {_str(d['technologie'])}")
    if d.get("annee") is not None:
        t.append(f"{s} sg:anneeInstallation {_int(d['annee'])}")
    if d.get("poste"):
        t.append(f"{s} sg:raccordeAuPoste {iri(d['poste']).n3()}")
    t += [f"{s} sg:stockeEnergieDe {iri(x).n3()}" for x in d["sources"]]
    t += [f"{s} sg:alimente {iri(b).n3()}" for b in d.get("batiments", [])]
    return " .\n  ".join(t) + " ."


def creer(d):
    return f"INSERT DATA {{\n  {_triplets(d)}\n}}"


def modifier(d):
    """DELETE/INSERT : on retire toutes les valeurs gérées par le formulaire, puis on réécrit."""
    s = iri(d["id"]).n3()
    return f"""
DELETE {{ {s} a ?t ; rdfs:label ?a ; sg:capaciteStockage ?c ; sg:niveauCharge ?n ; sg:rendement ?r ;
             sg:puissanceDecharge ?pu ; sg:technologie ?te ; sg:anneeInstallation ?an ;
             sg:raccordeAuPoste ?po ; sg:stockeEnergieDe ?so ; sg:alimente ?b }}
WHERE  {{ OPTIONAL {{ {s} a ?t . ?t rdfs:subClassOf* sg:SystemeStockage }}
          OPTIONAL {{ {s} rdfs:label ?a }} OPTIONAL {{ {s} sg:capaciteStockage ?c }}
          OPTIONAL {{ {s} sg:niveauCharge ?n }} OPTIONAL {{ {s} sg:rendement ?r }}
          OPTIONAL {{ {s} sg:puissanceDecharge ?pu }} OPTIONAL {{ {s} sg:technologie ?te }}
          OPTIONAL {{ {s} sg:anneeInstallation ?an }} OPTIONAL {{ {s} sg:raccordeAuPoste ?po }}
          OPTIONAL {{ {s} sg:stockeEnergieDe ?so }} OPTIONAL {{ {s} sg:alimente ?b }} }} ;
INSERT DATA {{\n  {_triplets(d)}\n}}"""


def changer_niveau(individu_id, niveau):
    """Mise à jour d'une seule valeur (niveauCharge est fonctionnelle : on remplace)."""
    s = iri(individu_id).n3()
    return f"""
DELETE {{ {s} sg:niveauCharge ?ancien }}
INSERT {{ {s} sg:niveauCharge {n3_float(niveau)} }}
WHERE  {{ OPTIONAL {{ {s} sg:niveauCharge ?ancien }} }}"""


def supprimer(individu_id):
    s = iri(individu_id).n3()
    return f"DELETE WHERE {{ {s} ?p ?o }} ;\nDELETE WHERE {{ ?x ?p {s} }}"
