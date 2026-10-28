"""Enrichit le module Stockage de l'ontologie SmartGrid-1.owl (Membre 2 · Takoua Naceur).

Ajoute des classes (dont 4 classes définies), propriétés, axiomes, une règle SWRL
et des individus du domaine Stockage, puis réécrit SmartGrid-1.owl (RDF/XML,
ouvrable dans Protégé). Une sauvegarde est faite dans backups/ avant toute écriture.

    python backend/scripts/enrichir_stockage.py

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

g = Graph()


def fr(text):
    return Literal(text, lang="fr")


def f(value):
    return Literal(float(value), datatype=XSD.float)


def liste(*items):
    head = BNode()
    Collection(g, head, list(items))
    return head


def plage_float(**facettes):
    """Datatype float restreint, ex. plage_float(minInclusive=0, maxInclusive=100)."""
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


def classe(uri, parent, label, comment):
    g.add((uri, RDF.type, OWL.Class))
    g.add((uri, RDFS.subClassOf, parent))
    g.add((uri, RDFS.label, fr(label)))
    g.add((uri, RDFS.comment, fr(comment)))


def definie(uri, label, comment, *conditions):
    """Classe définie : uri ≡ SystemeStockage ⊓ conditions…"""
    classe(uri, SG.SystemeStockage, label, comment)
    definition = BNode()
    g.add((definition, RDF.type, OWL.Class))
    g.add((definition, OWL.intersectionOf, liste(SG.SystemeStockage, *conditions)))
    g.add((uri, OWL.equivalentClass, definition))


# ---------------------------------------------------------------- schéma

def classes_et_axiomes():
    # Nouvelles classes primitives
    classe(SG.BatteriePlomb, SG.Batterie, "Batterie plomb-acide",
           "Batterie électrochimique classique, peu chère mais au rendement plus faible.")
    classe(SG.VolantInertie, SG.SystemeStockage, "Volant d'inertie",
           "Stockage mécanique : un rotor lancé à grande vitesse restitue l'énergie en quelques secondes.")

    # Disjonctions : lithium-ion / plomb, et les 4 familles de stockage deux à deux
    g.add((SG.BatteriePlomb, OWL.disjointWith, SG.BatterieLithiumIon))
    familles = BNode()
    g.add((familles, RDF.type, OWL.AllDisjointClasses))
    g.add((familles, OWL.members, liste(SG.Batterie, SG.StockageHydrogene, SG.STEP, SG.VolantInertie)))

    # Classes définies (déduites par HermiT, réécrites en SPARQL côté backend)
    definie(SG.StockageVert, "Stockage vert",
            "Classe définie : stockage qui stocke l'énergie d'au moins une source renouvelable.",
            restriction(SG.stockeEnergieDe, someValuesFrom=SG.SourceRenouvelable))
    definie(SG.StockageCritique, "Stockage critique",
            "Classe définie : niveau de charge strictement inférieur à 20 % (à recharger).",
            restriction(SG.niveauCharge, someValuesFrom=plage_float(maxExclusive=20)))
    definie(SG.StockageGrandeCapacite, "Stockage de grande capacité",
            "Classe définie : capacité d'au moins 10 000 kWh (10 MWh), échelle du réseau.",
            restriction(SG.capaciteStockage, someValuesFrom=plage_float(minInclusive=10000)))
    definie(SG.StockageSecours, "Stockage de secours",
            "Classe définie : stockage qui alimente au moins un bâtiment public (hôpital, école…).",
            restriction(SG.alimente, someValuesFrom=SG.BatimentPublic))

    # Plages de valeurs (restrictions universelles sur des DataProperties)
    g.add((SG.SystemeStockage, RDFS.subClassOf, restriction(
        SG.niveauCharge, allValuesFrom=plage_float(minInclusive=0, maxInclusive=100))))
    g.add((SG.SystemeStockage, RDFS.subClassOf, restriction(
        SG.rendement, allValuesFrom=plage_float(minExclusive=0, maxInclusive=100))))

    # Hydrogène vert : produit par électrolyse à partir d'une source renouvelable
    g.add((SG.StockageHydrogene, RDFS.subClassOf, restriction(
        SG.stockeEnergieDe, someValuesFrom=SG.SourceRenouvelable)))

    # Un volant d'inertie est raccordé à exactement un poste (régulation de fréquence)
    g.add((SG.VolantInertie, RDFS.subClassOf, restriction(
        SG.raccordeAuPoste, qualifiedCardinality=Literal(1, datatype=XSD.nonNegativeInteger),
        onClass=SG.PosteElectrique)))


def proprietes():
    # niveauCharge devient fonctionnelle : un seul niveau de charge à un instant donné
    g.add((SG.niveauCharge, RDF.type, OWL.FunctionalProperty))

    # ObjectProperty : inverse de stockeEnergieDe
    p = SG.estStockePar
    g.add((p, RDF.type, OWL.ObjectProperty))
    g.add((p, OWL.inverseOf, SG.stockeEnergieDe))
    g.add((p, RDFS.domain, SG.SourceEnergie))
    g.add((p, RDFS.range, SG.SystemeStockage))
    g.add((p, RDFS.label, fr("est stocké par")))

    # ObjectProperty : raccordement d'un stockage à un poste (fonctionnelle)
    p = SG.raccordeAuPoste
    g.add((p, RDF.type, OWL.ObjectProperty))
    g.add((p, RDF.type, OWL.FunctionalProperty))
    g.add((p, RDFS.domain, SG.SystemeStockage))
    g.add((p, RDFS.range, SG.PosteElectrique))
    g.add((p, RDFS.label, fr("raccordé au poste")))

    # DataProperties
    for nom, rng, label, fonctionnelle in [
        ("rendement", XSD.float, "rendement aller-retour (%)", True),
        ("puissanceDecharge", XSD.float, "puissance de décharge (kW)", True),
        ("technologie", XSD.string, "technologie", True),
        ("anneeInstallation", XSD.integer, "année d'installation", True),
    ]:
        p = SG[nom]
        g.add((p, RDF.type, OWL.DatatypeProperty))
        if fonctionnelle:
            g.add((p, RDF.type, OWL.FunctionalProperty))
        g.add((p, RDFS.domain, SG.SystemeStockage))
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
    """R6 : SystemeStockage(?x) ^ stockeEnergieDe(?x, ?s) ^ alimente(?x, ?b) → estAlimentePar(?b, ?s)"""
    x, s, b = var("x"), var("s"), var("b")
    r = BNode()
    g.add((r, RDF.type, SWRL.Imp))
    g.add((r, RDFS.label, Literal("R6_StockageIndirect")))
    g.add((r, RDFS.comment, fr("Un bâtiment alimenté par un stockage est indirectement "
                                "alimenté par la source dont ce stockage garde l'énergie.")))
    g.add((r, SWRL.body, atomes(atome_classe(SG.SystemeStockage, x),
                                atome_prop(SG.stockeEnergieDe, x, s),
                                atome_prop(SG.alimente, x, b))))
    g.add((r, SWRL.head, atomes(atome_prop(SG.estAlimentePar, b, s))))


# ------------------------------------------------------------- individus

# id, classe, label, capacité kWh, charge %, rendement %, puissance kW, technologie, année,
# sources stockées, bâtiments alimentés, poste
STOCKAGES = [
    ("Batterie_Maison1", None, None, None, None, 92, 5, "Lithium-ion NMC", 2022,
     [], [], "Poste_Ariana"),
    ("Batterie_Hopital", None, None, None, None, 90, 250, "Lithium fer phosphate (LFP)", 2020,
     [], [], "Poste_Ariana"),
    ("Batterie_Usine_Sfax", None, None, None, 45, 85, 1000, "Sodium-soufre (NaS)", 2019,
     [], [], "Poste_Sfax"),
    ("Stockage_H2_Gabes", None, None, None, 60, 40, 5000, "Électrolyse PEM + réservoirs", 2023,
     [], [], "Poste_Gabes"),
    ("STEP_Sejnane", None, None, None, 55, 78, 100000, "Pompage-turbinage", 2025,
     [], [], "Poste_Bizerte"),
    ("Batterie_Ecole_Ariana", "BatteriePlomb", "Batterie de l'école d'Ariana", 40, 15, 75, 10,
     "Plomb-acide AGM", 2015, ["Eolienne_Bizerte"], ["Ecole_Ariana"], "Poste_Ariana"),
    ("Batterie_Immeuble_Lac", "BatterieLithiumIon", "Batterie de l'immeuble du Lac", 120, 65, 93, 50,
     "Lithium-ion NMC", 2023, ["CentraleSolaire_Tozeur"], ["Immeuble_Lac"], "Poste_Rades"),
    ("Volant_Rades", "VolantInertie", "Volant d'inertie de Radès", 50, 90, 88, 2000,
     "Rotor acier sous vide", 2021, ["CentraleGaz_Rades"], [], "Poste_Rades"),
    ("Batterie_Reseau_Tozeur", "BatterieLithiumIon", "Batterie réseau de Tozeur", 20000, 10, 91, 10000,
     "Lithium fer phosphate (LFP)", 2024, ["CentraleSolaire_Tozeur"], [], "Poste_Tozeur"),
]


def individus():
    nouveaux = []
    for (sid, cls, label, capacite, charge, rendement, puissance, techno, annee,
         sources, batiments, poste) in STOCKAGES:
        s = SG[sid]
        if cls:
            g.add((s, RDF.type, OWL.NamedIndividual))
            g.add((s, RDF.type, SG[cls]))
            g.add((s, RDFS.label, fr(label)))
            g.add((s, SG.capaciteStockage, f(capacite)))
            nouveaux.append(s)
        if charge is not None:
            g.set((s, SG.niveauCharge, f(charge)))
        g.add((s, SG.rendement, f(rendement)))
        g.add((s, SG.puissanceDecharge, f(puissance)))
        g.add((s, SG.technologie, Literal(techno, datatype=XSD.string)))
        g.add((s, SG.anneeInstallation, Literal(annee, datatype=XSD.integer)))
        g.add((s, SG.raccordeAuPoste, SG[poste]))
        for src in sources:
            g.add((s, SG.stockeEnergieDe, SG[src]))
        for b in batiments:
            g.add((s, SG.alimente, SG[b]))

    # les nouveaux individus rejoignent owl:AllDifferent
    owner = next(g.subjects(RDF.type, OWL.AllDifferent))
    membres = Collection(g, g.value(owner, OWL.distinctMembers))
    for s in nouveaux:
        if s not in membres:
            membres.append(s)
    return nouveaux


def main():
    g.parse(OWL_FILE, format="xml")
    if (SG.StockageVert, RDF.type, OWL.Class) in g:
        print("Ontologie déjà enrichie (stockage) : rien à faire.")
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
