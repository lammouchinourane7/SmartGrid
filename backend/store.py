"""Graphe RDF partagé par tous les modules (RDFLib).

Au premier lancement, l'ontologie Protégé (SmartGrid-1.owl) est copiée dans
backend/data/smartgrid.owl : toutes les modifications CRUD sont écrites dans
cette copie, le fichier Protégé d'origine n'est jamais modifié.
"""
import re
import shutil
import threading
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

BASE_DIR = Path(__file__).resolve().parent
SOURCE_OWL = BASE_DIR.parent / "SmartGrid-1.owl"
DATA_OWL = BASE_DIR / "data" / "smartgrid.owl"

SG = Namespace("http://www.esprit.tn/ontologies/smartgrid#")

PREFIXES = """PREFIX sg:   <http://www.esprit.tn/ontologies/smartgrid#>
PREFIX rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX owl:  <http://www.w3.org/2002/07/owl#>
PREFIX xsd:  <http://www.w3.org/2001/XMLSchema#>
"""

_ID_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{1,63}$")
_lock = threading.RLock()
graph = Graph()


def load(reset: bool = False) -> None:
    """Charge la copie de travail (ou la recrée depuis l'ontologie Protégé)."""
    with _lock:
        if reset or not DATA_OWL.exists():
            DATA_OWL.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE_OWL, DATA_OWL)
        graph.remove((None, None, None))
        graph.parse(DATA_OWL, format="xml")
        graph.bind("sg", SG)


def save() -> None:
    with _lock:
        graph.serialize(destination=DATA_OWL, format="xml")


def select(query: str) -> list[dict]:
    """Exécute un SELECT et renvoie une liste de dicts {variable: valeur python}."""
    with _lock:
        result = graph.query(PREFIXES + query)
        rows = []
        for row in result:
            rows.append({str(var): _to_python(row[var]) for var in result.vars})
        return rows


def ask(query: str) -> bool:
    with _lock:
        return bool(graph.query(PREFIXES + query).askAnswer)


def update(query: str) -> None:
    """Exécute un INSERT/DELETE SPARQL puis persiste le graphe."""
    with _lock:
        graph.update(PREFIXES + query)
        save()


def _distinct_members_owner():
    return next(graph.subjects(RDF.type, OWL.AllDifferent), None)


def _set_distinct_members(owner, members) -> None:
    head = graph.value(owner, OWL.distinctMembers)
    while head is not None and head != RDF.nil:  # supprime l'ancienne liste RDF
        nxt = graph.value(head, RDF.rest)
        graph.remove((head, None, None))
        head = nxt
    new_head = BNode()
    Collection(graph, new_head, list(members))
    graph.set((owner, OWL.distinctMembers, new_head))


def declare_distinct(uri: URIRef) -> None:
    """Ajoute un nouvel individu à l'owl:AllDifferent (hypothèse du nom unique pour HermiT)."""
    with _lock:
        owner = _distinct_members_owner()
        if owner is None:
            return
        members = list(Collection(graph, graph.value(owner, OWL.distinctMembers)))
        if uri not in members:
            _set_distinct_members(owner, members + [uri])
            save()


def forget_distinct(uri: URIRef) -> None:
    """Retire un individu supprimé de l'owl:AllDifferent sans casser la liste RDF."""
    with _lock:
        owner = _distinct_members_owner()
        if owner is None:
            return
        members = list(Collection(graph, graph.value(owner, OWL.distinctMembers)))
        if uri in members:
            _set_distinct_members(owner, [m for m in members if m != uri])
            save()


def exists(uri: URIRef, rdf_type: URIRef) -> bool:
    with _lock:
        return (uri, RDF.type, rdf_type) in graph


def valid_id(value: str) -> bool:
    return bool(value and _ID_RE.match(value))


def iri(local_id: str) -> URIRef:
    return SG[local_id]


def local(uri) -> str:
    return str(uri).replace(str(SG), "")


def n3_label(text: str) -> str:
    return Literal(text, lang="fr").n3()


def n3_float(value: float) -> str:
    return Literal(float(value), datatype=XSD.float).n3()


def _to_python(value):
    if value is None:
        return None
    if isinstance(value, Literal):
        py = value.toPython()
        return py if isinstance(py, (int, float, bool)) else str(py)
    return local(value)

