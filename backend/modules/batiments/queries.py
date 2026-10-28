"""Requêtes SPARQL du module Bâtiments (Membre 3 · Abir Mosrati).

Classes : Batiment, BatimentResidentiel, BatimentIndustriel, BatimentPublic,
BatimentCommercial + 5 classes définies (≡).

RDFLib n'exécute ni HermiT ni SWRL : les connaissances déduites sont réécrites
en SPARQL, au plus près des axiomes de l'ontologie :
  - BatimentVert ≡ Batiment ⊓ estAlimentePar some SourceRenouvelable
  - BatimentAutonome ≡ Batiment ⊓ estAlimentePar some SourceRenouvelable
                                ⊓ possedeStockage some SystemeStockage
  - GrosConsommateur ≡ Batiment ⊓ consommationAnnuelle some float[≥ 1000000]
  - BatimentIntelligent ≡ Batiment ⊓ equipeDe some CompteurIntelligent   (equipeDe = installeDans⁻¹)
  - BatimentRaccordeHT ≡ Batiment ⊓ estRaccordeA some LigneHauteTension  (LigneHauteTension : tension ≥ 63 kV)
  - estAlimentePar par 5 chemins : direct, produitEnergiePour⁻¹, R1, R6, R7
      R1 : injecteDans(?s, ?l) ∧ transporteVers(?l, ?b) → estAlimentePar(?b, ?s)
      R6 : stockeEnergieDe(?x, ?s) ∧ alimente(?x, ?b)   → estAlimentePar(?b, ?s)
      R7 : estRaccordeA(?b, ?l) ∧ injecteDans(?s, ?l)   → estAlimentePar(?b, ?s)   (nouvelle règle)
  - R2 : SystemeStockage(?x) ∧ alimente(?x, ?b) → possedeStockage(?b, ?x)
  - R3 : estRaccordeA(?b, ?l) ∧ relie(?l, ?p)   → estDesserviPar(?b, ?p)
"""
from rdflib import Literal
from rdflib.namespace import XSD

from store import iri, n3_float, n3_label

TYPES = ("BatimentResidentiel", "BatimentIndustriel", "BatimentPublic", "BatimentCommercial")
DEFINIES = {
    "vert": "BatimentVert",
    "autonome": "BatimentAutonome",
    "gros": "GrosConsommateur",
    "intelligent": "BatimentIntelligent",
    "ht": "BatimentRaccordeHT",
}
SEUIL_GROS = 1_000_000   # kWh / an
SEUIL_HT = 63            # kV (LigneHauteTension)
SEUIL_MT = 1             # kV (au-dessus : moyenne ou haute tension)
CLASSES_ENERGETIQUES = ("A", "B", "C", "D", "E", "F", "G")
# Seuils DPE simplifiés (kWh/m²/an) : A ≤ 70 < B ≤ 110 < C ≤ 180 < D ≤ 250 < E ≤ 330 < F ≤ 420 < G
SEUILS_DPE = (("A", 70), ("B", 110), ("C", 180), ("D", 250), ("E", 330), ("F", 420))


# Les 5 chemins vers une source qui alimente ?b (variable de sortie ?s, chemin ?via)
CHEMINS_SOURCES = """
    { ?b sg:estAlimentePar ?s . BIND("direct" AS ?via) }
    UNION { ?s sg:produitEnergiePour ?b . BIND("inverse" AS ?via) }                  # owl:inverseOf
    UNION { ?s sg:injecteDans ?l1 . ?l1 sg:transporteVers ?b . BIND("R1" AS ?via) }  # règle R1
    UNION { ?xs sg:alimente ?b ; sg:stockeEnergieDe ?s . BIND("R6" AS ?via) }        # règle R6
    UNION { ?b sg:estRaccordeA ?l7 . ?s sg:injecteDans ?l7 . BIND("R7" AS ?via) }    # règle R7"""

# Classe énergétique recalculée à partir de l'intensité (kWh/m²/an)
_DPE = '"G"'
for _lettre, _seuil in reversed(SEUILS_DPE):
    _DPE = f'IF(?intensite <= {_seuil}, "{_lettre}", {_DPE})'

INFERENCES = f"""
  # BatimentVert ≡ Batiment ⊓ estAlimentePar some SourceRenouvelable (direct, inverse, R1, R6, R7)
  BIND(EXISTS {{ {CHEMINS_SOURCES.strip()}
    ?s a/rdfs:subClassOf* sg:SourceRenouvelable }} AS ?vert)
  # R2 : possedeStockage some SystemeStockage
  BIND(EXISTS {{ {{ ?xa sg:alimente ?b }} UNION {{ ?b sg:possedeStockage ?xa }} }} AS ?stockage)
  # BatimentAutonome ≡ BatimentVert ⊓ possedeStockage some SystemeStockage
  BIND(?vert && ?stockage AS ?autonome)
  # GrosConsommateur ≡ Batiment ⊓ consommationAnnuelle some float[≥ {SEUIL_GROS}]
  BIND(BOUND(?conso) && ?conso >= {SEUIL_GROS} AS ?gros)
  # BatimentIntelligent ≡ Batiment ⊓ equipeDe some CompteurIntelligent (equipeDe ≡ installeDans⁻¹)
  BIND(EXISTS {{ {{ ?b sg:equipeDe ?ci }} UNION {{ ?ci sg:installeDans ?b }} }} AS ?intelligent)
  # BatimentRaccordeHT ≡ Batiment ⊓ estRaccordeA some LigneHauteTension (tension ≥ {SEUIL_HT} kV)
  BIND(EXISTS {{ ?b sg:estRaccordeA ?lh . ?lh sg:tension ?th . FILTER(?th >= {SEUIL_HT}) }} AS ?ht)
  # intensité énergétique (kWh/m²/an) et classe DPE recalculée
  BIND(IF(BOUND(?conso) && BOUND(?surface) && ?surface > 0, ?conso / ?surface, ?unbound) AS ?intensite)
  BIND(IF(BOUND(?intensite), {_DPE}, ?unbound) AS ?dpeCalcule)"""

CLASSE_LA_PLUS_PRECISE = """
  ?b a ?classe ; a owl:NamedIndividual . ?classe rdfs:subClassOf* sg:Batiment .
  FILTER NOT EXISTS { ?b a ?autre . ?autre rdfs:subClassOf+ ?classe . FILTER(?autre != ?classe) }"""

ATTRIBUTS = """
  OPTIONAL { ?b rdfs:label ?label }
  OPTIONAL { ?b sg:adresse ?adresse }
  OPTIONAL { ?b sg:consommationAnnuelle ?conso }
  OPTIONAL { ?b sg:surface ?surface }
  OPTIONAL { ?b sg:nombreOccupants ?occupants }
  OPTIONAL { ?b sg:anneeConstruction ?annee }
  OPTIONAL { ?b sg:classeEnergetique ?dpe }
  OPTIONAL { ?b sg:puissanceSouscrite ?puissance }"""

COLONNES = ("?b ?label ?classe ?adresse ?conso ?surface ?occupants ?annee ?dpe ?puissance "
            "?vert ?stockage ?autonome ?gros ?intelligent ?ht ?intensite ?dpeCalcule")


def lister(q=None, type_=None, definie=None, conso_min=None, conso_max=None,
           ligne=None, poste=None, source=None, dpe=None, ids=None):
    """SELECT + filtres : texte, type, classe définie, plage de consommation, relations."""
    filters = []
    if q:
        needle = Literal(q.lower()).n3()
        filters.append(f"FILTER(CONTAINS(LCASE(STR(?label)), {needle}) "
                       f"|| CONTAINS(LCASE(STRAFTER(STR(?b), \"#\")), {needle}) "
                       f"|| CONTAINS(LCASE(STR(?adresse)), {needle}))")
    if type_ in TYPES:
        filters.append(f"FILTER(?classe = sg:{type_})")
    if definie in DEFINIES:
        filters.append(f"FILTER(?{definie})  # individu de sg:{DEFINIES[definie]}")
    if conso_min is not None:
        filters.append(f"FILTER(?conso >= {float(conso_min)})")
    if conso_max is not None:
        filters.append(f"FILTER(?conso <= {float(conso_max)})")
    if dpe in CLASSES_ENERGETIQUES:
        filters.append(f'FILTER(?dpe = "{dpe}")')
    if ligne:
        filters.append(f"FILTER EXISTS {{ {{ ?b sg:estRaccordeA {iri(ligne).n3()} }} "
                       f"UNION {{ {iri(ligne).n3()} sg:transporteVers ?b }} }}")
    if poste:
        filters.append(f"# R3 : estRaccordeA ∘ relie → estDesserviPar\n"
                       f"  FILTER EXISTS {{ {{ ?b sg:estDesserviPar {iri(poste).n3()} }} "
                       f"UNION {{ ?b sg:estRaccordeA ?lp . ?lp sg:relie {iri(poste).n3()} }} }}")
    if source:
        filters.append(f"FILTER EXISTS {{ {CHEMINS_SOURCES.strip()}\n    FILTER(?s = {iri(source).n3()}) }}")
    if ids:
        filters.append(f"VALUES ?b {{ {' '.join(iri(x).n3() for x in ids)} }}")

    return f"""
SELECT {COLONNES}
WHERE {{
  {CLASSE_LA_PLUS_PRECISE.strip()}
  {ATTRIBUTS.strip()}
  {INFERENCES.strip()}
  {chr(10).join("  " + f for f in filters).strip()}
}}
ORDER BY DESC(?conso)"""


def relations(batiment_id=None):
    """Toutes les relations d'un (ou de tous les) bâtiment(s), avec le chemin qui les justifie."""
    filtre = f"VALUES ?b {{ {iri(batiment_id).n3()} }}" if batiment_id else ""
    return f"""
SELECT DISTINCT ?b ?rel ?cible ?via ?renouvelable WHERE {{
  ?b a/rdfs:subClassOf* sg:Batiment . {filtre}
  {{
    # lignes de raccordement
    {{ ?b sg:estRaccordeA ?cible . BIND("estRaccordeA" AS ?via) }}
    UNION {{ ?cible sg:transporteVers ?b . BIND("transporteVers" AS ?via) }}
    BIND("ligne" AS ?rel)
  }} UNION {{
    # sources d'énergie (5 chemins)
    {CHEMINS_SOURCES.strip()}
    BIND(?s AS ?cible) BIND("source" AS ?rel)
    BIND(EXISTS {{ ?s a/rdfs:subClassOf* sg:SourceRenouvelable }} AS ?renouvelable)
  }} UNION {{
    # stockages possédés (R2)
    {{ ?cible sg:alimente ?b . BIND("R2" AS ?via) }}
    UNION {{ ?b sg:possedeStockage ?cible . BIND("direct" AS ?via) }}
    BIND("stockage" AS ?rel)
  }} UNION {{
    # postes qui desservent le bâtiment (R3)
    {{ ?b sg:estDesserviPar ?cible . BIND("direct" AS ?via) }}
    UNION {{ ?b sg:estRaccordeA ?l3 . ?l3 sg:relie ?cible . BIND("R3" AS ?via) }}
    BIND("poste" AS ?rel)
  }} UNION {{
    # compteurs intelligents (equipeDe ≡ installeDans⁻¹)
    {{ ?cible sg:installeDans ?b . BIND("installeDans⁻¹" AS ?via) }}
    UNION {{ ?b sg:equipeDe ?cible . BIND("equipeDe" AS ?via) }}
    BIND("compteur" AS ?rel)
  }}
}}"""


STATISTIQUES = f"""
SELECT (COUNT(DISTINCT ?b) AS ?nb)
       (SUM(?conso) AS ?consoTotale)
       (AVG(?intensite) AS ?intensiteMoyenne)
       (SUM(?occupants) AS ?occupantsTotal)
       (SUM(IF(?vert, 1, 0)) AS ?nbVerts)
       (SUM(IF(?autonome, 1, 0)) AS ?nbAutonomes)
       (SUM(IF(?gros, 1, 0)) AS ?nbGros)
       (SUM(IF(?intelligent, 1, 0)) AS ?nbIntelligents)
       (SUM(IF(?ht, 1, 0)) AS ?nbHT)
       (SUM(IF(?vert, ?conso, 0)) AS ?consoVerte)
WHERE {{
  {CLASSE_LA_PLUS_PRECISE.strip()}
  {ATTRIBUTS.strip()}
  {INFERENCES.strip()}
}}"""

PAR_TYPE = """
SELECT ?classe (COUNT(DISTINCT ?b) AS ?nb) (SUM(?conso) AS ?conso) WHERE {
  ?b a ?classe ; a owl:NamedIndividual .
  VALUES ?classe { sg:BatimentResidentiel sg:BatimentIndustriel sg:BatimentPublic sg:BatimentCommercial }
  OPTIONAL { ?b sg:consommationAnnuelle ?conso }
}
GROUP BY ?classe"""

OPTIONS = """
SELECT ?id ?label ?groupe ?tension ?renouvelable ?lie WHERE {
  {
    ?x a/rdfs:subClassOf* sg:LigneElectrique . BIND("lignes" AS ?groupe)
    OPTIONAL { ?x sg:tension ?tension }
    OPTIONAL { ?s0 sg:injecteDans ?x . BIND(STRAFTER(STR(?s0), "#") AS ?lie) }   # pour R7
  } UNION {
    ?x a/rdfs:subClassOf* sg:SourceEnergie . BIND("sources" AS ?groupe)
    BIND(EXISTS { ?x a/rdfs:subClassOf* sg:SourceRenouvelable } AS ?renouvelable)
  } UNION {
    ?x a/rdfs:subClassOf* sg:SystemeStockage . BIND("stockages" AS ?groupe)
    OPTIONAL { ?x sg:stockeEnergieDe ?s1 . BIND(STRAFTER(STR(?s1), "#") AS ?lie) } # pour R6
  } UNION {
    ?x a sg:PosteElectrique . BIND("postes" AS ?groupe)
  }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  BIND(STRAFTER(STR(?x), "#") AS ?id)
}
ORDER BY ?groupe ?label"""


# ----------------------------------------------------------- vérifications --

def ask_type(individu_id, classe):
    return f"ASK {{ {iri(individu_id).n3()} a/rdfs:subClassOf* sg:{classe} }}"


def ask_existe(individu_id):
    return f"ASK {{ {{ {iri(individu_id).n3()} ?p ?o }} UNION {{ ?s ?p {iri(individu_id).n3()} }} }}"


def ask_label_pris(label, sauf_id=None):
    sauf = f"FILTER(?x != {iri(sauf_id).n3()})" if sauf_id else ""
    return f"""ASK {{
  ?x a/rdfs:subClassOf* sg:Batiment ; rdfs:label ?l .
  FILTER(LCASE(STR(?l)) = {Literal(label.strip().lower()).n3()})
  {sauf}
}}"""


def tensions(lignes):
    """Tension de chaque ligne choisie (pour BatimentIndustriel ⊑ estRaccordeA some (MT ⊔ HT))."""
    return f"""
SELECT ?l ?tension WHERE {{
  VALUES ?l {{ {' '.join(iri(x).n3() for x in lignes)} }}
  OPTIONAL {{ ?l sg:tension ?tension }}
}}"""


def sources_deduites(batiment_id, lignes, stockages):
    """Sources qui alimenteraient le bâtiment après enregistrement (R7, R6, et liens existants)."""
    parts = []
    if lignes:
        parts.append(f"{{ VALUES ?l {{ {' '.join(iri(x).n3() for x in lignes)} }} ?s sg:injecteDans ?l }}  # R7")
    if stockages:
        parts.append(f"{{ VALUES ?x {{ {' '.join(iri(x).n3() for x in stockages)} }} ?x sg:stockeEnergieDe ?s }}  # R6")
    if batiment_id:
        b = iri(batiment_id).n3()
        parts.append(f"{{ ?s sg:produitEnergiePour {b} }}  # inverse")
        parts.append(f"{{ ?s sg:injecteDans ?l1 . ?l1 sg:transporteVers {b} }}  # R1")
    if not parts:
        return None
    return "SELECT DISTINCT ?s WHERE {\n  " + "\n  UNION ".join(parts) + "\n}"


def dependances(individu_id):
    """Qui pointe vers ce bâtiment ? (utilisé avant une suppression)"""
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
    b = iri(d["id"]).n3()
    t = [f"{b} a owl:NamedIndividual, sg:{d['classe']}",
         f"{b} rdfs:label {n3_label(d['label'])}",
         f"{b} sg:consommationAnnuelle {n3_float(d['consommation'])}"]
    if d.get("adresse"):
        t.append(f"{b} sg:adresse {_str(d['adresse'])}")
    for champ, prop in (("surface", "surface"), ("puissance", "puissanceSouscrite")):
        if d.get(champ) is not None:
            t.append(f"{b} sg:{prop} {n3_float(d[champ])}")
    for champ, prop in (("occupants", "nombreOccupants"), ("annee", "anneeConstruction")):
        if d.get(champ) is not None:
            t.append(f"{b} sg:{prop} {_int(d[champ])}")
    if d.get("dpe"):
        t.append(f"{b} sg:classeEnergetique {_str(d['dpe'])}")
    t += [f"{b} sg:estRaccordeA {iri(x).n3()}" for x in d["lignes"]]
    t += [f"{b} sg:estAlimentePar {iri(x).n3()}" for x in d.get("sources", [])]
    t += [f"{iri(x).n3()} sg:alimente {b}" for x in d.get("stockages", [])]   # R2 → possedeStockage
    return " .\n  ".join(t) + " ."


def creer(d):
    return f"INSERT DATA {{\n  {_triplets(d)}\n}}"


def modifier(d):
    """DELETE/INSERT : on retire toutes les valeurs gérées par le formulaire, puis on réécrit."""
    b = iri(d["id"]).n3()
    return f"""
DELETE {{ {b} a ?t ; rdfs:label ?a ; sg:adresse ?ad ; sg:consommationAnnuelle ?c ; sg:surface ?su ;
             sg:nombreOccupants ?o ; sg:anneeConstruction ?an ; sg:classeEnergetique ?dpe ;
             sg:puissanceSouscrite ?pu ; sg:estRaccordeA ?l ; sg:estAlimentePar ?s .
          ?x sg:alimente {b} . {b} sg:possedeStockage ?xp }}
WHERE  {{ OPTIONAL {{ {b} a ?t . ?t rdfs:subClassOf* sg:Batiment }}
          OPTIONAL {{ {b} rdfs:label ?a }} OPTIONAL {{ {b} sg:adresse ?ad }}
          OPTIONAL {{ {b} sg:consommationAnnuelle ?c }} OPTIONAL {{ {b} sg:surface ?su }}
          OPTIONAL {{ {b} sg:nombreOccupants ?o }} OPTIONAL {{ {b} sg:anneeConstruction ?an }}
          OPTIONAL {{ {b} sg:classeEnergetique ?dpe }} OPTIONAL {{ {b} sg:puissanceSouscrite ?pu }}
          OPTIONAL {{ {b} sg:estRaccordeA ?l }} OPTIONAL {{ {b} sg:estAlimentePar ?s }}
          OPTIONAL {{ ?x sg:alimente {b} }} OPTIONAL {{ {b} sg:possedeStockage ?xp }} }} ;
INSERT DATA {{\n  {_triplets(d)}\n}}"""


def changer_valeur(individu_id, propriete, valeur_n3):
    """Mise à jour d'une seule valeur d'une propriété fonctionnelle : on remplace."""
    b = iri(individu_id).n3()
    return f"""
DELETE {{ {b} sg:{propriete} ?ancien }}
INSERT {{ {b} sg:{propriete} {valeur_n3} }}
WHERE  {{ OPTIONAL {{ {b} sg:{propriete} ?ancien }} }}"""


def changer_consommation(individu_id, consommation):
    return changer_valeur(individu_id, "consommationAnnuelle", n3_float(consommation))


def changer_dpe(individu_id, lettre):
    return changer_valeur(individu_id, "classeEnergetique", _str(lettre))


def supprimer(individu_id):
    b = iri(individu_id).n3()
    return f"DELETE WHERE {{ {b} ?p ?o }} ;\nDELETE WHERE {{ ?x ?p {b} }}"


def dpe_calcule(intensite):
    """Même barème qu'en SPARQL, pour le contrôle de saisie et l'aperçu."""
    if intensite is None:
        return None
    for lettre, seuil in SEUILS_DPE:
        if intensite <= seuil:
            return lettre
    return "G"
