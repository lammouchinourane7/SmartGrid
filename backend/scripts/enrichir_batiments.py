"""Enrichit le module Bâtiments de l'ontologie SmartGrid-1.owl (Membre 3 · Abir Mosrati).

Ajoute une classe, 4 classes définies, des propriétés, des axiomes, une règle SWRL
et des individus du domaine Bâtiments, puis réécrit SmartGrid-1.owl (RDF/XML,
ouvrable dans Protégé). Une sauvegarde est faite dans backups/ avant toute écriture.

    python backend/scripts/enrichir_batiments.py

Le script ne fait rien si l'ontologie est déjà enrichie.
Après l'avoir lancé : POST /api/reset pour recharger la copie de travail du backend.
"""
import shutil
from datetime import datetime
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS, XSD

ROOT = Path(__file__).resolve().parents[2]
OWL_FILE = ROOT / "SmartGrid-1.owl"
SG = Namespace("http://www.esprit.tn/ontologies/smartgrid#")
SWRL = Namespace("http://www.w3.org/2003/11/swrl#")

SEUIL_GROS_CONSOMMATEUR = 1_000_000   # kWh / an (1 GWh)
CLASSES_ENERGETIQUES = ["A", "B", "C", "D", "E", "F", "G"]

g = Graph()


def fr(text):
    return Literal(text, lang="fr")


def f(value):
    return Literal(float(value), datatype=XSD.float)


def i(value):
    return Literal(int(value), datatype=XSD.integer)


def s(value):
    return Literal(value, datatype=XSD.string)


def liste(*items):
    head = BNode()
    Collection(g, head, list(items))
    return head


def plage(type_xsd, **facettes):
    """Datatype restreint, ex. plage(XSD.float, minInclusive=0)."""
    dt = BNode()
    g.add((dt, RDF.type, RDFS.Datatype))
    g.add((dt, OWL.onDatatype, type_xsd))
    restrictions = []
    for facette, valeur in facettes.items():
        r = BNode()
        g.add((r, XSD[facette], f(valeur) if type_xsd == XSD.float else i(valeur)))
        restrictions.append(r)
    g.add((dt, OWL.withRestrictions, liste(*restrictions)))
    return dt


def enumeration(*valeurs):
    """Datatype énuméré (DataOneOf), ex. {"A", "B", …}."""
    dt = BNode()
    g.add((dt, RDF.type, RDFS.Datatype))
    g.add((dt, OWL.oneOf, liste(*[s(v) for v in valeurs])))
    return dt


def restriction(prop, **kw):
    r = BNode()
    g.add((r, RDF.type, OWL.Restriction))
    g.add((r, OWL.onProperty, prop))
    for k, v in kw.items():
        g.add((r, OWL[k], v))
    return r


def union(*classes):
    u = BNode()
    g.add((u, RDF.type, OWL.Class))
    g.add((u, OWL.unionOf, liste(*classes)))
    return u


def classe(uri, parent, label, comment):
    g.add((uri, RDF.type, OWL.Class))
    g.add((uri, RDFS.subClassOf, parent))
    g.add((uri, RDFS.label, fr(label)))
    g.add((uri, RDFS.comment, fr(comment)))


def definie(uri, label, comment, *conditions):
    """Classe définie : uri ≡ Batiment ⊓ conditions…"""
    classe(uri, SG.Batiment, label, comment)
    definition = BNode()
    g.add((definition, RDF.type, OWL.Class))
    g.add((definition, OWL.intersectionOf, liste(SG.Batiment, *conditions)))
    g.add((uri, OWL.equivalentClass, definition))


# ---------------------------------------------------------------- schéma

def classes_et_axiomes():
    # Nouvelle classe primitive
    classe(SG.BatimentCommercial, SG.Batiment, "Bâtiment commercial",
           "Commerce, centre commercial, bureaux ou hôtel.")

    # Disjonction : les 4 usages de bâtiment deux à deux
    usages = BNode()
    g.add((usages, RDF.type, OWL.AllDisjointClasses))
    g.add((usages, OWL.members, liste(SG.BatimentResidentiel, SG.BatimentIndustriel,
                                      SG.BatimentPublic, SG.BatimentCommercial)))

    # Classes définies (déduites par HermiT, réécrites en SPARQL côté backend)
    definie(SG.BatimentVert, "Bâtiment vert",
            "Classe définie : bâtiment alimenté par au moins une source renouvelable "
            "(BatimentAutonome en est une sous-classe déduite).",
            restriction(SG.estAlimentePar, someValuesFrom=SG.SourceRenouvelable))
    definie(SG.GrosConsommateur, "Gros consommateur",
            "Classe définie : consommation annuelle d'au moins 1 000 000 kWh (1 GWh).",
            restriction(SG.consommationAnnuelle,
                        someValuesFrom=plage(XSD.float, minInclusive=SEUIL_GROS_CONSOMMATEUR)))
    definie(SG.BatimentIntelligent, "Bâtiment intelligent",
            "Classe définie : bâtiment équipé d'au moins un compteur intelligent "
            "(equipeDe, inverse de installeDans).",
            restriction(SG.equipeDe, someValuesFrom=SG.CompteurIntelligent))
    definie(SG.BatimentRaccordeHT, "Bâtiment raccordé en haute tension",
            "Classe définie : bâtiment raccordé à une ligne haute tension "
            "(chaîne d'inférences : tension ≥ 63 kV → LigneHauteTension → BatimentRaccordeHT).",
            restriction(SG.estRaccordeA, someValuesFrom=SG.LigneHauteTension))

    # Plages de valeurs (restrictions universelles sur des DataProperties)
    g.add((SG.Batiment, RDFS.subClassOf, restriction(
        SG.consommationAnnuelle, allValuesFrom=plage(XSD.float, minInclusive=0))))
    g.add((SG.Batiment, RDFS.subClassOf, restriction(
        SG.surface, allValuesFrom=plage(XSD.float, minExclusive=0))))
    g.add((SG.Batiment, RDFS.subClassOf, restriction(
        SG.nombreOccupants, allValuesFrom=plage(XSD.integer, minInclusive=0))))
    # Énumération : la classe énergétique (DPE) est une lettre de A à G
    g.add((SG.Batiment, RDFS.subClassOf, restriction(
        SG.classeEnergetique, allValuesFrom=enumeration(*CLASSES_ENERGETIQUES))))

    # Union : un site industriel est raccordé en moyenne ou en haute tension
    g.add((SG.BatimentIndustriel, RDFS.subClassOf, restriction(
        SG.estRaccordeA, someValuesFrom=union(SG.LigneMoyenneTension, SG.LigneHauteTension))))


def proprietes():
    # consommationAnnuelle devient fonctionnelle : une seule consommation de référence
    g.add((SG.consommationAnnuelle, RDF.type, OWL.FunctionalProperty))

    # ObjectProperty : inverse de installeDans (Membre 5)
    p = SG.equipeDe
    g.add((p, RDF.type, OWL.ObjectProperty))
    g.add((p, OWL.inverseOf, SG.installeDans))
    g.add((p, RDFS.domain, SG.Batiment))
    g.add((p, RDFS.range, SG.CompteurIntelligent))
    g.add((p, RDFS.label, fr("est équipé de")))

    # DataProperties fonctionnelles
    for nom, rng, label in [
        ("surface", XSD.float, "surface (m²)"),
        ("nombreOccupants", XSD.integer, "nombre d'occupants"),
        ("anneeConstruction", XSD.integer, "année de construction"),
        ("classeEnergetique", XSD.string, "classe énergétique (DPE)"),
        ("puissanceSouscrite", XSD.float, "puissance souscrite (kW)"),
    ]:
        p = SG[nom]
        g.add((p, RDF.type, OWL.DatatypeProperty))
        g.add((p, RDF.type, OWL.FunctionalProperty))
        g.add((p, RDFS.domain, SG.Batiment))
        g.add((p, RDFS.range, rng))
        g.add((p, RDFS.label, fr(label)))


def var(nom):
    v = URIRef(f"urn:swrl:var#{nom}")
    g.add((v, RDF.type, SWRL.Variable))
    return v


def atome_classe(cls, x):
    a = BNode()
    g.add((a, RDF.type, SWRL.ClassAtom))
    g.add((a, SWRL.classPredicate, cls))
    g.add((a, SWRL.argument1, x))
    return a


def atome_prop(prop, x, y):
    a = BNode()
    g.add((a, RDF.type, SWRL.IndividualPropertyAtom))
    g.add((a, SWRL.propertyPredicate, prop))
    g.add((a, SWRL.argument1, x))
    g.add((a, SWRL.argument2, y))
    return a


def atomes(*items):
    """swrl:AtomList typée, comme Protégé l'écrit."""
    head = liste(*items)
    node = head
    while node != RDF.nil:
        g.add((node, RDF.type, SWRL.AtomList))
        node = g.value(node, RDF.rest)
    return head


def regle_swrl():
    """R7 : Batiment(?b) ^ estRaccordeA(?b, ?l) ^ injecteDans(?s, ?l) → estAlimentePar(?b, ?s)"""
    b, l, src = var("b"), var("l"), var("s")
    r = BNode()
    g.add((r, RDF.type, SWRL.Imp))
    g.add((r, RDFS.label, Literal("R7_Raccordement")))
    g.add((r, RDFS.comment, fr("Un bâtiment raccordé à une ligne est alimenté par les sources "
                                "qui injectent dans cette ligne (complète R1, vu côté bâtiment).")))
    g.add((r, SWRL.body, atomes(atome_classe(SG.Batiment, b),
                                atome_prop(SG.estRaccordeA, b, l),
                                atome_prop(SG.injecteDans, src, l))))
    g.add((r, SWRL.head, atomes(atome_prop(SG.estAlimentePar, b, src))))


# ------------------------------------------------------------- individus

# id, classe (None = existant), label, adresse, conso kWh/an, surface m², occupants,
# année, classe DPE, puissance souscrite kW, lignes (estRaccordeA), sources (estAlimentePar)
BATIMENTS = [
    ("Maison1", None, None, None, None, 120, 4, 2008, "B", 9, [], []),
    ("Immeuble_Lac", None, None, "Rue du Lac Léman, Les Berges du Lac, Tunis", None, 2400, 80, 2015, "A", 120, [], []),
    ("Usine_Sfax", None, None, "Zone industrielle Poudrière, Sfax", None, 25000, 350, 1998, "E", 2500, [], []),
    ("Hopital_CharlesNicolle", None, None, None, None, 18000, 1200, 1897, "C", 1200, [], []),
    ("Ecole_Ariana", None, None, "Avenue de l'Indépendance, Ariana", None, 1500, 450, 1985, "A", 36, [],
     ["CentraleGaz_Rades"]),   # 2e source : BatimentPublic ⊑ estAlimentePar min 2 SourceEnergie
    ("Mairie_Nabeul", "BatimentPublic", "Mairie de Nabeul", "Avenue Habib Bourguiba, Nabeul",
     210000, 2600, 120, 1972, "B", 150, ["Ligne_MT_Nabeul"], ["ParcEolien_SidiDaoud", "CentraleGaz_Rades"]),
    ("Villa_Hammamet", "BatimentResidentiel", "Villa de Hammamet", "Route touristique, Hammamet",
     16500, 150, 5, 1994, "D", 12, ["Ligne_MT_Nabeul"], []),
    ("Cimenterie_Gabes", "BatimentIndustriel", "Cimenterie de Gabès", "Zone industrielle de Ghannouch, Gabès",
     45000000, 60000, 600, 1979, "G", 9000, ["Ligne_Gabes_Sfax"], []),
    ("Centre_Commercial_Lac", "BatimentCommercial", "Centre commercial des Berges du Lac",
     "Les Berges du Lac 2, Tunis", 2400000, 12000, 3000, 2010, "D", 900, ["Ligne_MT_Lac"], []),
]


def individus():
    nouveaux = []
    for (bid, cls, label, adresse, conso, surface, occupants, annee, dpe, puissance,
         lignes, sources) in BATIMENTS:
        b = SG[bid]
        if cls:
            g.add((b, RDF.type, OWL.NamedIndividual))
            g.add((b, RDF.type, SG[cls]))
            g.add((b, RDFS.label, fr(label)))
            nouveaux.append(b)
        if adresse and not g.value(b, SG.adresse):
            g.add((b, SG.adresse, s(adresse)))
        if conso is not None:
            g.set((b, SG.consommationAnnuelle, f(conso)))
        g.add((b, SG.surface, f(surface)))
        g.add((b, SG.nombreOccupants, i(occupants)))
        g.add((b, SG.anneeConstruction, i(annee)))
        g.add((b, SG.classeEnergetique, s(dpe)))
        g.add((b, SG.puissanceSouscrite, f(puissance)))
        for l in lignes:
            g.add((b, SG.estRaccordeA, SG[l]))
        for src in sources:
            g.add((b, SG.estAlimentePar, SG[src]))

    # les nouveaux individus rejoignent owl:AllDifferent
    owner = next(g.subjects(RDF.type, OWL.AllDifferent))
    membres = Collection(g, g.value(owner, OWL.distinctMembers))
    for b in nouveaux:
        if b not in membres:
            membres.append(b)
    return nouveaux


def main():
    g.parse(OWL_FILE, format="xml")
    if (SG.BatimentVert, RDF.type, OWL.Class) in g:
        print("Ontologie déjà enrichie (bâtiments) : rien à faire.")
        return
    backups = ROOT / "backups"
    backups.mkdir(exist_ok=True)
    backup = backups / f"SmartGrid-1.{datetime.now():%Y%m%d-%H%M%S}.owl"
    shutil.copyfile(OWL_FILE, backup)

    avant = len(g)
    proprietes()
    classes_et_axiomes()
    regle_swrl()
    nouveaux = individus()
    g.bind("sg", SG)
    g.bind("swrl", SWRL)
    g.serialize(destination=OWL_FILE, format="xml")
    print(f"{len(g) - avant} triplets ajoutés, {len(nouveaux)} nouveaux individus.")
    print(f"Sauvegarde : {backup}")


if __name__ == "__main__":
    main()
