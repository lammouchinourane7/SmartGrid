"""Requêtes SPARQL du module Gestion et mesure (Membre 5 · Ibtihel Mechergui).

Classes : CompteurIntelligent, Mesure, MesureConsommation, MesureProduction,
OperateurReseau.

Axiomes de l'ontologie pris en compte :
  - CompteurIntelligent ⊑ installeDans exactly 1 Batiment   (installeDans fonctionnelle)
  - equipeDe ≡ installeDans⁻¹ (ajoutée par le module Bâtiments) → on lit les deux sens
  - MesureConsommation ⊑ concerne only Batiment ⊓ concerne max 1 Batiment
  - MesureProduction ⊑ concerne only SourceEnergie
  - MesureConsommation ⊓ MesureProduction ⊑ ⊥ (disjointes)

RDFLib n'exécute pas SWRL : la règle R5 est réécrite en SPARQL (motif R5 ci-dessous)
  R5 : CompteurIntelligent(?c) ^ installeDans(?c, ?b) ^ enregistre(?c, ?m)
       ^ MesureConsommation(?m) → concerne(?m, ?b)
Elle est évaluée à chaque requête : aucune déduction n'est stockée dans le graphe,
donc elle reste juste après chaque modification CRUD.
R4 (module Réseau) est relue pour les lignes gérées indirectement par un opérateur.

Toutes les valeurs saisies passent par iri() (identifiants déjà validés) ou
Literal(...).n3() (échappement RDFLib) : aucune chaîne brute dans les requêtes.
"""
from rdflib import Literal
from rdflib.namespace import XSD

from store import iri, n3_float, n3_label

TYPES = {"consommation": "MesureConsommation", "production": "MesureProduction"}


def ids(var, alias):
    """Concatène les identifiants locaux d'une variable OPTIONAL.

    COALESCE contourne un bug de RDFLib : GROUP_CONCAT(DISTINCT ...) plante
    quand la variable n'est pas liée.
    """
    return (f'(GROUP_CONCAT(DISTINCT COALESCE(STRAFTER(STR(?{var}), "#"), ""); '
            f'separator="|") AS ?{alias})')


def n3_date(value):
    """'2025-01-31T23:59:59' → littéral xsd:dateTime échappé."""
    return Literal(value, datatype=XSD.dateTime).n3()


def _str(value):
    return Literal(value, datatype=XSD.string).n3()


def _texte(q, *variables):
    needle = Literal(q.lower()).n3()
    tests = [f"CONTAINS(LCASE(STR(?{v})), {needle})" for v in variables]
    return f"FILTER({' || '.join(tests)})"


# ---------------------------------------------------------------- motifs --

def installation(c, b):
    """Bâtiment d'un compteur : installeDans ou son inverse equipeDe."""
    return f"{{ {c} sg:installeDans {b} }} UNION {{ {b} sg:equipeDe {c} }}"


def r5(m, b, c="?c5"):
    """Règle R5 réécrite : bâtiment déduit pour une mesure de consommation."""
    return (f"{m} a sg:MesureConsommation . {c} a sg:CompteurIntelligent ; sg:enregistre {m} .\n"
            f"    {installation(c, b)}")


def cible(m, x, suffixe="", via=None):
    """Cible d'une mesure : concerne asserté, ou bâtiment déduit par R5."""
    bind_a = f' BIND("assertion" AS {via})' if via else ""
    bind_r5 = f' BIND("R5" AS {via})' if via else ""
    return (f"{{ {m} sg:concerne {x} .{bind_a} }}\n"
            f"    UNION {{ # R5\n    {r5(m, x, '?c5' + suffixe)}{bind_r5} }}")


TYPE_BIND = """BIND(IF(EXISTS { ?m a sg:MesureConsommation }, "consommation",
               IF(EXISTS { ?m a sg:MesureProduction }, "production", "indeterminee")) AS ?type)"""


def _conditions(debut, fin, mode, d="?debut", f="?fin"):
    """Sélection temporelle explicite.

    chevauchement : la période de la mesure touche l'intervalle demandé ;
    inclusion     : la mesure est entièrement comprise dans l'intervalle.
    """
    out = []
    if debut:
        out.append(f"{d if mode == 'inclusion' else f} >= {n3_date(debut)}")
    if fin:
        out.append(f"{f if mode == 'inclusion' else d} <= {n3_date(fin)}")
    return out


def _periode(debut, fin, mode, d="?debut", f="?fin"):
    return [f"FILTER({c})" for c in _conditions(debut, fin, mode, d, f)]


# ------------------------------------------------------------- compteurs --

def lister_compteurs(q=None, batiment=None, compteur=None):
    filtres = []
    if q:
        filtres.append(_texte(q, "label", "identifiant", "c"))
    if batiment:
        filtres.append(f"FILTER EXISTS {{ {installation('?c', iri(batiment).n3())} }}")
    if compteur:
        filtres.append(f"FILTER(?c = {iri(compteur).n3()})")
    return f"""
SELECT ?c ?label ?identifiant
       (COUNT(DISTINCT ?b) AS ?nbBatiments) {ids("b", "batiments")}
       (COUNT(DISTINCT ?m) AS ?nbMesures) {ids("m", "mesures")}
WHERE {{
  ?c a sg:CompteurIntelligent .
  OPTIONAL {{ ?c rdfs:label ?label }}
  OPTIONAL {{ ?c sg:identifiant ?identifiant }}
  # CompteurIntelligent ⊑ installeDans exactly 1 Batiment (equipeDe ≡ installeDans⁻¹)
  OPTIONAL {{ {installation("?c", "?b")} }}
  OPTIONAL {{ ?c sg:enregistre ?m }}
  {chr(10).join("  " + f for f in filtres)}
}}
GROUP BY ?c ?label ?identifiant
ORDER BY ?identifiant ?label"""


def batiments_du_compteur(compteur_id):
    return f"SELECT DISTINCT ?b WHERE {{ {installation(iri(compteur_id).n3(), '?b')} }}"


def mesures_impactees(compteur_id):
    """Mesures de consommation dont le bâtiment dépend du compteur (R5), avec leur concerne asserté vers un bâtiment."""
    c = iri(compteur_id).n3()
    return f"""
SELECT ?m ?label ?direct WHERE {{
  {c} sg:enregistre ?m .
  ?m a sg:MesureConsommation .
  OPTIONAL {{ ?m rdfs:label ?label }}
  OPTIONAL {{ ?m sg:concerne ?direct . ?direct a/rdfs:subClassOf* sg:Batiment }}
}}"""


def concerne_batiment_asserte(mesure_id):
    m = iri(mesure_id).n3()
    return f"SELECT DISTINCT ?b WHERE {{ {m} sg:concerne ?b . ?b a/rdfs:subClassOf* sg:Batiment }}"


def historique(mesure_id):
    return f"SELECT ?note WHERE {{ {iri(mesure_id).n3()} rdfs:comment ?note }}"


def note_conserver(compteur_id, ancien, jour):
    """Trace (annotation rdfs:comment) du lien enregistre retiré par la politique « conserver »."""
    return (f"Enregistrée par sg:{compteur_id} lorsqu'il était installé dans sg:{ancien} ; lien enregistre "
            f"retiré le {jour} lors du déplacement du compteur (politique conserver).")


def compteur_identifiant_pris(identifiant, sauf_id=None):
    sauf = f"FILTER(?c != {iri(sauf_id).n3()})" if sauf_id else ""
    return f"""ASK {{
  ?c a sg:CompteurIntelligent ; sg:identifiant ?i .
  FILTER(LCASE(STR(?i)) = {Literal(identifiant.lower()).n3()})
  {sauf}
}}"""


def _triplets_compteur(d):
    s = iri(d["id"]).n3()
    t = [f"{s} a owl:NamedIndividual, sg:CompteurIntelligent",
         f"{s} rdfs:label {n3_label(d['label'])}",
         f"{s} sg:identifiant {_str(d['identifiant'])}",
         f"{s} sg:installeDans {iri(d['batiment']).n3()}"]
    return " .\n  ".join(t) + " ."


def creer_compteur(d):
    return f"INSERT DATA {{\n  {_triplets_compteur(d)}\n}}"


def modifier_compteur(d, politique=None, ancien=None, impactees=(), jour=None):
    """DELETE/INSERT du compteur, puis politique explicite pour ses mesures de consommation.

    reaffecter : les mesures suivent le compteur (R5 donne le nouveau bâtiment) ;
                 un concerne asserté vers un bâtiment est retiré pour ne pas contredire
                 concerne max 1 Batiment.
    conserver  : les mesures restent sur l'ancien bâtiment : concerne est asserté
                 explicitement et le lien enregistre est retiré (sinon R5 déduirait
                 un second bâtiment) ; une annotation rdfs:comment garde la trace du compteur.
    """
    s = iri(d["id"]).n3()
    parties = [f"""
DELETE {{ {s} rdfs:label ?l ; sg:identifiant ?i ; sg:installeDans ?b . ?b2 sg:equipeDe {s} }}
WHERE  {{ OPTIONAL {{ {s} rdfs:label ?l }} OPTIONAL {{ {s} sg:identifiant ?i }}
          OPTIONAL {{ {s} sg:installeDans ?b }} OPTIONAL {{ ?b2 sg:equipeDe {s} }} }}""",
               f"INSERT DATA {{\n  {_triplets_compteur(d)}\n}}"]
    for m in impactees:
        mm = iri(m).n3()
        retirer_concerne = (f"DELETE {{ {mm} sg:concerne ?x }} WHERE {{ {mm} sg:concerne ?x . "
                            f"?x a/rdfs:subClassOf* sg:Batiment }}")
        if politique == "reaffecter":
            parties.append(retirer_concerne)
        elif politique == "conserver":
            parties.append(retirer_concerne)
            parties.append(f"DELETE DATA {{ {s} sg:enregistre {mm} }}")
            parties.append(f"INSERT DATA {{ {mm} sg:concerne {iri(ancien).n3()} ; "
                           f"rdfs:comment {n3_label(note_conserver(d['id'], ancien, jour))} }}")
    return " ;\n".join(parties)


def figer_r5(compteur_id):
    """Avant suppression d'un compteur : R5 devient une assertion explicite (rien n'est perdu)."""
    c = iri(compteur_id).n3()
    return f"""
INSERT {{ ?m sg:concerne ?b }}
WHERE  {{ {c} sg:enregistre ?m . ?m a sg:MesureConsommation .
          {installation(c, "?b")}
          FILTER NOT EXISTS {{ ?m sg:concerne ?autre }} }}"""


# --------------------------------------------------------------- mesures --

def lister_mesures(q=None, type_=None, compteur=None, cible_id=None, valeur_min=None,
                   valeur_max=None, debut=None, fin=None, mode="chevauchement", mesure=None):
    filtres = []
    if q:
        filtres.append(_texte(q, "label", "m"))
    if type_ in TYPES:
        filtres.append(f"?m a sg:{TYPES[type_]} .")
    if compteur:
        filtres.append(f"{iri(compteur).n3()} sg:enregistre ?m .")
    if cible_id:
        filtres.append(f"FILTER EXISTS {{\n    {cible('?m', iri(cible_id).n3(), 'f')}\n  }}")
    if valeur_min is not None:
        filtres.append(f"FILTER(?valeur >= {float(valeur_min)})")
    if valeur_max is not None:
        filtres.append(f"FILTER(?valeur <= {float(valeur_max)})")
    if mesure:
        filtres.append(f"FILTER(?m = {iri(mesure).n3()})")
    filtres += _periode(debut, fin, mode)
    return f"""
SELECT ?m ?label ?type ?valeur ?debut ?fin
       {ids("c", "compteurs")}
       {ids("cd", "ciblesAssertees")}
       {ids("b5", "ciblesR5")}
WHERE {{
  ?m a/rdfs:subClassOf* sg:Mesure .
  OPTIONAL {{ ?m rdfs:label ?label }}
  OPTIONAL {{ ?m sg:valeurKWh ?valeur }}
  OPTIONAL {{ ?m sg:dateDebut ?debut }}
  OPTIONAL {{ ?m sg:dateFin ?fin }}
  {TYPE_BIND}
  OPTIONAL {{ ?c sg:enregistre ?m }}
  OPTIONAL {{ ?m sg:concerne ?cd }}
  # R5 : CompteurIntelligent(?c) ^ installeDans(?c, ?b) ^ enregistre(?c, ?m) ^ MesureConsommation(?m) → concerne(?m, ?b)
  OPTIONAL {{ {r5("?m", "?b5")} }}
  {chr(10).join("  " + f for f in filtres)}
}}
GROUP BY ?m ?label ?type ?valeur ?debut ?fin
ORDER BY DESC(?debut) ?label"""


def _triplets_mesure(d):
    s = iri(d["id"]).n3()
    t = [f"{s} a owl:NamedIndividual, sg:{TYPES[d['type']]}",
         f"{s} rdfs:label {n3_label(d['label'])}",
         f"{s} sg:valeurKWh {n3_float(d['valeur'])}",
         f"{s} sg:dateDebut {n3_date(d['debut'])}",
         f"{s} sg:dateFin {n3_date(d['fin'])}"]
    if d.get("compteur"):
        t.append(f"{iri(d['compteur']).n3()} sg:enregistre {s}")
    if d.get("concerne"):  # vide pour une consommation dont le bâtiment est déduit par R5
        t.append(f"{s} sg:concerne {iri(d['concerne']).n3()}")
    return " .\n  ".join(t) + " ."


def creer_mesure(d):
    return f"INSERT DATA {{\n  {_triplets_mesure(d)}\n}}"


def modifier_mesure(d):
    s = iri(d["id"]).n3()
    return f"""
DELETE {{ {s} a ?t ; rdfs:label ?l ; sg:valeurKWh ?v ; sg:dateDebut ?d ; sg:dateFin ?f ;
             sg:concerne ?x . ?c sg:enregistre {s} }}
WHERE  {{ OPTIONAL {{ {s} a ?t . FILTER(?t IN (sg:MesureConsommation, sg:MesureProduction, sg:Mesure)) }}
          OPTIONAL {{ {s} rdfs:label ?l }} OPTIONAL {{ {s} sg:valeurKWh ?v }}
          OPTIONAL {{ {s} sg:dateDebut ?d }} OPTIONAL {{ {s} sg:dateFin ?f }}
          OPTIONAL {{ {s} sg:concerne ?x }} OPTIONAL {{ ?c sg:enregistre {s} }} }} ;
INSERT DATA {{\n  {_triplets_mesure(d)}\n}}"""


# ------------------------------------------------------------ opérateurs --

def lister_operateurs(q=None, infrastructure=None):
    filtres = []
    if q:
        filtres.append(_texte(q, "label", "o"))
    if infrastructure:
        x = iri(infrastructure).n3()
        filtres.append(f"FILTER EXISTS {{ {{ ?o sg:gere {x} }} UNION {{ ?o sg:gere ?pf . {x} sg:relie ?pf }} }}")
    return f"""
SELECT ?o ?label {ids("g", "gere")} {ids("l4", "lignesR4")}
WHERE {{
  ?o a sg:OperateurReseau .
  OPTIONAL {{ ?o rdfs:label ?label }}
  OPTIONAL {{ ?o sg:gere ?g }}
  # R4 : gere(o, p) ∧ relie(l, p) → gere(o, l)
  OPTIONAL {{ ?o sg:gere ?p4 . ?l4 sg:relie ?p4 . FILTER NOT EXISTS {{ ?o sg:gere ?l4 }} }}
  {chr(10).join("  " + f for f in filtres)}
}}
GROUP BY ?o ?label
ORDER BY ?label"""


def _triplets_operateur(d):
    s = iri(d["id"]).n3()
    t = [f"{s} a owl:NamedIndividual, sg:OperateurReseau",
         f"{s} rdfs:label {n3_label(d['label'])}"]
    t += [f"{s} sg:gere {iri(x).n3()}" for x in d["gere"]]
    return " .\n  ".join(t) + " ."


def creer_operateur(d):
    return f"INSERT DATA {{\n  {_triplets_operateur(d)}\n}}"


def modifier_operateur(d):
    """Seuls le libellé et les gere de l'opérateur sont réécrits ; les infrastructures restent intactes."""
    s = iri(d["id"]).n3()
    return f"""
DELETE {{ {s} rdfs:label ?l ; sg:gere ?x }}
WHERE  {{ OPTIONAL {{ {s} rdfs:label ?l }} OPTIONAL {{ {s} sg:gere ?x }} }} ;
INSERT DATA {{\n  {_triplets_operateur(d)}\n}}"""


# ------------------------------------------------------- vue d'ensemble ----

COMPTES = """
SELECT (COUNT(DISTINCT ?c) AS ?compteurs) (COUNT(DISTINCT ?mc) AS ?consommations)
       (COUNT(DISTINCT ?mp) AS ?productions) (COUNT(DISTINCT ?o) AS ?operateurs)
WHERE {
  { ?c a sg:CompteurIntelligent } UNION { ?mc a sg:MesureConsommation }
  UNION { ?mp a sg:MesureProduction } UNION { ?o a sg:OperateurReseau }
}"""


def _mesures_datees(debut, fin, mode):
    return "\n    ".join([
        "?m a/rdfs:subClassOf* sg:Mesure ; sg:valeurKWh ?valeur ; sg:dateDebut ?debut ; sg:dateFin ?fin .",
        TYPE_BIND, *_periode(debut, fin, mode)])


def bilan_types(debut, fin):
    """SUM / COUNT par type, mesures entièrement incluses dans la période (pas de proratisation)."""
    return f"""
SELECT ?type (COUNT(?m) AS ?nombre) (SUM(?valeur) AS ?totalKWh) WHERE {{
  {{ SELECT DISTINCT ?m ?type ?valeur WHERE {{
    {_mesures_datees(debut, fin, "inclusion")}
  }} }}
}}
GROUP BY ?type"""


def bilan_cibles(debut, fin):
    return f"""
SELECT ?type ?cible ?via (COUNT(?m) AS ?nombre) (SUM(?valeur) AS ?totalKWh) WHERE {{
  {{ SELECT DISTINCT ?m ?type ?valeur ?cible ?via WHERE {{
    {_mesures_datees(debut, fin, "inclusion")}
    {cible("?m", "?cible", via="?via")}
  }} }}
}}
GROUP BY ?type ?cible ?via
ORDER BY ?type DESC(?totalKWh)"""


def bilan_exclues(debut, fin):
    """Mesures qui chevauchent la période sans y être incluses : non comptées dans les totaux."""
    return f"""
SELECT DISTINCT ?m ?type ?debut ?fin WHERE {{
  {_mesures_datees(debut, fin, "chevauchement")}
  FILTER(!({" && ".join(["true"] + _conditions(debut, fin, "inclusion"))}))
}}"""


def chevauchements(debut=None, fin=None):
    """Paires de mesures de même type et même cible dont les périodes se recouvrent."""
    f1 = _periode(debut, fin, "inclusion", "?d1", "?f1")
    f2 = _periode(debut, fin, "inclusion", "?d2", "?f2")
    return f"""
SELECT DISTINCT ?m1 ?m2 ?cible WHERE {{
  ?m1 sg:dateDebut ?d1 ; sg:dateFin ?f1 . ?m2 sg:dateDebut ?d2 ; sg:dateFin ?f2 .
  {{ ?m1 a sg:MesureConsommation . ?m2 a sg:MesureConsommation }}
  UNION {{ ?m1 a sg:MesureProduction . ?m2 a sg:MesureProduction }}
  FILTER(STR(?m1) < STR(?m2) && ?d1 <= ?f2 && ?d2 <= ?f1)
  {cible("?m1", "?cible", "a")}
  {cible("?m2", "?cible", "b")}
  {chr(10).join("  " + f for f in f1 + f2)}
}}"""


# Anomalies : ce que l'hypothèse du monde ouvert ne signale pas d'elle-même.
COHERENCE = f"""
SELECT ?x ?probleme ?detail WHERE {{
  {{
    {{ SELECT ?x (COUNT(DISTINCT ?b) AS ?n) WHERE {{
        ?x a sg:CompteurIntelligent . OPTIONAL {{ {installation("?x", "?b")} }} }} GROUP BY ?x }}
    FILTER(?n != 1)
    BIND("installeDans exactly 1 Batiment" AS ?probleme) BIND(STR(?n) AS ?detail)
  }} UNION {{
    {{ SELECT ?x (COUNT(DISTINCT ?b) AS ?n) WHERE {{
        ?x a sg:MesureConsommation . {cible("?x", "?b")} }} GROUP BY ?x }}
    FILTER(?n > 1)
    BIND("concerne max 1 Batiment (assertion + R5)" AS ?probleme) BIND(STR(?n) AS ?detail)
  }} UNION {{
    ?x a sg:MesureConsommation ; sg:concerne ?y .
    FILTER NOT EXISTS {{ ?y a/rdfs:subClassOf* sg:Batiment }}
    BIND("concerne only Batiment" AS ?probleme) BIND(STRAFTER(STR(?y), "#") AS ?detail)
  }} UNION {{
    ?x a sg:MesureProduction ; sg:concerne ?y .
    FILTER NOT EXISTS {{ ?y a/rdfs:subClassOf* sg:SourceEnergie }}
    BIND("concerne only SourceEnergie" AS ?probleme) BIND(STRAFTER(STR(?y), "#") AS ?detail)
  }} UNION {{
    ?x sg:dateDebut ?d ; sg:dateFin ?f . FILTER(?f < ?d)
    BIND("dateFin antérieure à dateDebut" AS ?probleme) BIND(CONCAT(STR(?d), " > ", STR(?f)) AS ?detail)
  }} UNION {{
    ?x a/rdfs:subClassOf* sg:Mesure . FILTER NOT EXISTS {{ ?x sg:valeurKWh ?v }}
    BIND("valeurKWh absente" AS ?probleme) BIND("" AS ?detail)
  }}
}}"""


OPTIONS = """
SELECT ?id ?label ?groupe ?classe WHERE {
  {
    ?x a ?classe . ?classe rdfs:subClassOf* sg:Batiment . BIND("batiments" AS ?groupe)
  } UNION {
    ?x a ?classe . ?classe rdfs:subClassOf* sg:SourceEnergie . BIND("sources" AS ?groupe)
  } UNION {
    ?x a ?classe . ?classe rdfs:subClassOf* sg:InfrastructureReseau . BIND("infrastructures" AS ?groupe)
  } UNION {
    ?x a sg:CompteurIntelligent . BIND(sg:CompteurIntelligent AS ?classe) BIND("compteurs" AS ?groupe)
  } UNION {
    ?x a sg:OperateurReseau . BIND(sg:OperateurReseau AS ?classe) BIND("operateurs" AS ?groupe)
  }
  ?x a owl:NamedIndividual .
  OPTIONAL { ?x rdfs:label ?label }
  BIND(STRAFTER(STR(?x), "#") AS ?id)
}
ORDER BY ?groupe ?label"""


# ------------------------------------------------------------- contrôles --

def ask_type(individu_id, classe):
    return f"ASK {{ {iri(individu_id).n3()} a/rdfs:subClassOf* sg:{classe} }}"


def ask_existe(individu_id):
    return f"ASK {{ {{ {iri(individu_id).n3()} ?p ?o }} UNION {{ ?s ?p {iri(individu_id).n3()} }} }}"


def ask_label_pris(label, classe, sauf_id=None):
    sauf = f"FILTER(?x != {iri(sauf_id).n3()})" if sauf_id else ""
    return f"""ASK {{
  ?x a/rdfs:subClassOf* sg:{classe} ; rdfs:label ?l .
  FILTER(LCASE(STR(?l)) = {Literal(label.strip().lower()).n3()})
  {sauf}
}}"""


def references_entrantes(individu_id):
    """Qui pointe vers cet individu ? (avant une suppression)"""
    return f"""
SELECT ?s ?relation WHERE {{
  ?s ?p {iri(individu_id).n3()} .
  FILTER(isIRI(?s) && ?p != rdf:type)
  BIND(STRAFTER(STR(?p), "#") AS ?relation)
}}"""


def supprimer(individu_id):
    """Retire les triplets de l'individu (sujet et objet). Appelé seulement pour les
    individus du module, après contrôle des références entrantes."""
    s = iri(individu_id).n3()
    return f"DELETE WHERE {{ {s} ?p ?o }} ;\nDELETE WHERE {{ ?x ?p {s} }}"
