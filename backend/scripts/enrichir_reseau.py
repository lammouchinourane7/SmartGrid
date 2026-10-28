"""Enrichit le module Réseau de l'ontologie SmartGrid-1.owl (Membre 4 · Nourane Lammouchi).

Ajoute des classes, propriétés, axiomes et individus du domaine Réseau,
puis réécrit SmartGrid-1.owl (RDF/XML, ouvrable dans Protégé).
Une sauvegarde est faite dans backups/ avant toute écriture.

    python backend/scripts/enrichir_reseau.py

Le script ne fait rien si l'ontologie est déjà enrichie.
Après l'avoir lancé : POST /api/reset pour recharger la copie de travail du backend.
"""
import shutil
from datetime import datetime
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

ROOT = Path(__file__).resolve().parents[2]
OWL_FILE = ROOT / "SmartGrid-1.owl"
SG = Namespace("http://www.esprit.tn/ontologies/smartgrid#")

g = Graph()


def fr(text):
    return Literal(text, lang="fr")


def f(value):
    return Literal(float(value), datatype=XSD.float)


def liste(*items):
    head = BNode()
    Collection(g, head, list(items))
    return head


def intervalle_tension(**facettes):
    """Datatype float restreint, ex. intervalle_tension(minExclusive=1, maxExclusive=63)."""
    dt = BNode()
    g.add((dt, RDF.type, RDFS.Datatype))
    g.add((dt, OWL.onDatatype, XSD.float))
    restrictions = []
    for facette, valeur in facettes.items():
        r = BNode()
        g.add((r, XSD[facette], f(valeur)))
        restrictions.append(r)
    g.add((dt, OWL.withRestrictions, liste(*restrictions)))
    return dt


def restriction(prop, **kw):
    r = BNode()
    g.add((r, RDF.type, OWL.Restriction))
    g.add((r, OWL.onProperty, prop))
    for k, v in kw.items():
        g.add((r, OWL[k], v))
    return r


# ---------------------------------------------------------------- schéma

def classes_et_axiomes():
    # LigneMoyenneTension ≡ LigneElectrique ⊓ tension some float[> 1, < 63]
    mt = SG.LigneMoyenneTension
    g.add((mt, RDF.type, OWL.Class))
    g.add((mt, RDFS.subClassOf, SG.LigneElectrique))
    g.add((mt, RDFS.label, fr("Ligne moyenne tension")))
    g.add((mt, RDFS.comment, fr("Classe définie : tension strictement entre 1 kV et 63 kV.")))
    definition = BNode()
    g.add((definition, RDF.type, OWL.Class))
    g.add((definition, OWL.intersectionOf, liste(
        SG.LigneElectrique,
        restriction(SG.tension, someValuesFrom=intervalle_tension(minExclusive=1, maxExclusive=63)),
    )))
    g.add((mt, OWL.equivalentClass, definition))

    # HT, MT et BT sont deux à deux disjointes
    disjointes = BNode()
    g.add((disjointes, RDF.type, OWL.AllDisjointClasses))
    g.add((disjointes, OWL.members, liste(SG.LigneHauteTension, SG.LigneMoyenneTension, SG.LigneBasseTension)))

    # LigneHauteTension ⊑ relie min 2 PosteElectrique (une ligne de transport relie deux postes)
    g.add((SG.LigneHauteTension, RDFS.subClassOf, restriction(
        SG.relie, minQualifiedCardinality=Literal(2, datatype=XSD.nonNegativeInteger), onClass=SG.PosteElectrique)))

    # PosteElectrique ⊑ estReliePar some LigneElectrique (un poste est raccordé à au moins une ligne)
    g.add((SG.PosteElectrique, RDFS.subClassOf, restriction(SG.estReliePar, someValuesFrom=SG.LigneElectrique)))


def proprietes():
    # ObjectProperty : inverse de relie
    p = SG.estReliePar
    g.add((p, RDF.type, OWL.ObjectProperty))
    g.add((p, OWL.inverseOf, SG.relie))
    g.add((p, RDFS.domain, SG.PosteElectrique))
    g.add((p, RDFS.range, SG.LigneElectrique))
    g.add((p, RDFS.label, fr("est relié par")))

    # ObjectProperty : poste de secours (asymétrique, irréflexive)
    p = SG.secourt
    g.add((p, RDF.type, OWL.ObjectProperty))
    g.add((p, RDF.type, OWL.AsymmetricProperty))
    g.add((p, RDF.type, OWL.IrreflexiveProperty))
    g.add((p, RDFS.domain, SG.PosteElectrique))
    g.add((p, RDFS.range, SG.PosteElectrique))
    g.add((p, RDFS.label, fr("sert de secours à")))

    # DataProperties
    for nom, domaine, rng, label, fonctionnelle in [
        ("capaciteTransformation", SG.PosteElectrique, XSD.float, "capacité de transformation (MVA)", True),
        ("ville", SG.PosteElectrique, XSD.string, "ville", True),
        ("anneeMiseEnService", SG.InfrastructureReseau, XSD.integer, "année de mise en service", True),
    ]:
        p = SG[nom]
        g.add((p, RDF.type, OWL.DatatypeProperty))
        if fonctionnelle:
            g.add((p, RDF.type, OWL.FunctionalProperty))
        g.add((p, RDFS.domain, domaine))
        g.add((p, RDFS.range, rng))
        g.add((p, RDFS.label, fr(label)))


# ------------------------------------------------------------- individus

POSTES = [
    # id, label, ville, capacité MVA, année, connecté à, secourt
    ("Poste_Ariana", None, "Ariana", 120, 1998, [], []),
    ("Poste_Rades", None, "Radès", 400, 1985, [], []),
    ("Poste_Sfax", None, "Sfax", 300, 1990, [], []),
    ("Poste_Bizerte", "Poste de Bizerte", "Bizerte", 200, 2004, ["Poste_Ariana"], []),
    ("Poste_Sousse", "Poste de Sousse", "Sousse", 250, 1995, ["Poste_Rades", "Poste_Sfax"], []),
    ("Poste_Gabes", "Poste de Gabès", "Gabès", 220, 2001, ["Poste_Sfax"], []),
    ("Poste_Tozeur", "Poste de Tozeur", "Tozeur", 90, 2018, [], []),
    ("Poste_Nabeul", "Poste de Nabeul", "Nabeul", 110, 2009, [], ["Poste_Rades"]),
]

LIGNES = [
    # id, label, tension kV, longueur km, année, postes, bâtiments
    ("Ligne_Tunis_Sousse", None, None, None, 1992, [], []),
    ("Ligne_Ariana", None, None, None, 2005, [], []),
    ("Ligne_BT_Quartier1", None, None, None, 2012, [], []),
    ("Ligne_Sousse_Sfax", "Ligne Sousse–Sfax", 225, 130, 1996, ["Poste_Sousse", "Poste_Sfax"], []),
    ("Ligne_Bizerte_Ariana", "Ligne Bizerte–Ariana", 150, 65, 2004, ["Poste_Bizerte", "Poste_Ariana"], []),
    ("Ligne_Gabes_Sfax", "Ligne Gabès–Sfax", 225, 140, 2001, ["Poste_Gabes", "Poste_Sfax"], []),
    ("Ligne_Tozeur_Gabes", "Ligne Tozeur–Gabès", 150, 210, 2018, ["Poste_Tozeur", "Poste_Gabes"], []),
    ("Ligne_Rades_Nabeul", "Ligne Radès–Nabeul", 90, 60, 2009, ["Poste_Rades", "Poste_Nabeul"], []),
    ("Ligne_MT_Lac", "Ligne moyenne tension du Lac", 10, 4, 2015, ["Poste_Rades"], ["Immeuble_Lac"]),
    ("Ligne_MT_Nabeul", "Ligne moyenne tension de Nabeul", 30, 18, 2010, ["Poste_Nabeul"], []),
    ("Ligne_BT_Ecole_Ariana", "Ligne basse tension de l'école d'Ariana", 0.4, 0.8, 2016, ["Poste_Ariana"], ["Ecole_Ariana"]),
]


def individus():
    nouveaux = []
    for pid, label, ville, capacite, annee, connexions, secours in POSTES:
        s = SG[pid]
        if label:
            g.add((s, RDF.type, OWL.NamedIndividual))
            g.add((s, RDF.type, SG.PosteElectrique))
            g.add((s, RDFS.label, fr(label)))
            g.add((SG.STEG, SG.gere, s))
            nouveaux.append(s)
        g.add((s, SG.ville, Literal(ville, datatype=XSD.string)))
        g.add((s, SG.capaciteTransformation, f(capacite)))
        g.add((s, SG.anneeMiseEnService, Literal(annee, datatype=XSD.integer)))
        for c in connexions:
            g.add((s, SG.estConnecteA, SG[c]))
        for c in secours:
            g.add((s, SG.secourt, SG[c]))

    for lid, label, tension, longueur, annee, postes, batiments in LIGNES:
        s = SG[lid]
        if label:
            g.add((s, RDF.type, OWL.NamedIndividual))
            g.add((s, RDF.type, SG.LigneElectrique))
            g.add((s, RDFS.label, fr(label)))
            g.add((s, SG.tension, f(tension)))
            g.add((s, SG.longueur, f(longueur)))
            nouveaux.append(s)
        g.add((s, SG.anneeMiseEnService, Literal(annee, datatype=XSD.integer)))
        for p in postes:
            g.add((s, SG.relie, SG[p]))
        for b in batiments:
            g.add((s, SG.transporteVers, SG[b]))

    # les nouveaux individus rejoignent owl:AllDifferent
    owner = next(g.subjects(RDF.type, OWL.AllDifferent))
    membres = Collection(g, g.value(owner, OWL.distinctMembers))
    for s in nouveaux:
        if s not in membres:
            membres.append(s)
    return nouveaux


def main():
    g.parse(OWL_FILE, format="xml")
    if (SG.LigneMoyenneTension, RDF.type, OWL.Class) in g:
        print("Ontologie déjà enrichie : rien à faire.")
        return
    backups = ROOT / "backups"
    backups.mkdir(exist_ok=True)
    backup = backups / f"SmartGrid-1.{datetime.now():%Y%m%d-%H%M%S}.owl"
    shutil.copyfile(OWL_FILE, backup)

    avant = len(g)
    classes_et_axiomes()
    proprietes()
    nouveaux = individus()
    g.bind("sg", SG)
    g.serialize(destination=OWL_FILE, format="xml")
    print(f"{len(g) - avant} triplets ajoutés, {len(nouveaux)} nouveaux individus.")
    print(f"Sauvegarde : {backup}")


if __name__ == "__main__":
    main()
