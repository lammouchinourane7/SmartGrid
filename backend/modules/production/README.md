# Module 1 · Production d'énergie — Wala Rezgui

Sources d'énergie (solaire, éolien, non renouvelable), leurs lignes d'injection et les bâtiments qu'elles
alimentent. Même architecture que les autres modules : **Flask + RDFLib** (`backend/modules/production/`)
et **Angular 18** (`frontend/src/app/pages/production/`). Aucune API de LLM.

| Fichier | Rôle |
| --- | --- |
| `queries.py` | toutes les requêtes SPARQL (SELECT, agrégats, INSERT DATA, DELETE/INSERT, DELETE WHERE, ASK) |
| `validation.py` | contrôle de saisie, appliqué avant toute écriture (422 avec une erreur par champ) |
| `routes.py` | Blueprint `/api/production/...` |
| `nlp.py` | traducteur français → SPARQL (spaCy) |
| `verifications/` | scripts de vérification (CRUD, HermiT, persistance, non-régression, serveur réel) |
| `pages/production/` | page, service, modèles, formulaire, composant NLP |

Aucun fichier commun n'a été modifié : la route `/production`, l'entrée de navigation et l'enregistrement
du blueprint existaient déjà.

## Périmètre ontologique

Namespace : `http://www.esprit.tn/ontologies/smartgrid#`.
Les éléments ci-dessous ont été vérifiés dans l'ontologie ; aucun n'a été ajouté.

- **Classes** : `SourceEnergie` ; `SourceRenouvelable ⊑ SourceEnergie` ; `Solaire ⊑ SourceRenouvelable` ;
  `Eolien ⊑ SourceRenouvelable` ; `SourceNonRenouvelable ⊑ SourceEnergie`.
- **Axiomes** :
  - `SourceRenouvelable` et `SourceNonRenouvelable` disjointes ;
  - `Solaire` et `Eolien` disjointes ;
  - `Eolien ⊑ injecteDans some LigneElectrique` ;
  - `SourceEnergie` disjointe des autres classes racines (AllDisjointClasses).
- **ObjectProperties** :
  - `produitEnergiePour` (SourceEnergie → Batiment) et son inverse `estAlimentePar` (Batiment → SourceEnergie) ;
  - `injecteDans` (SourceEnergie → LigneElectrique).
- **DataProperties** : `puissanceInstallee` (float, kW, fonctionnelle) ; `dateMiseEnService` (dateTime).
- **Règle R1** : `SourceEnergie(?s) ^ injecteDans(?s, ?l) ^ transporteVers(?l, ?b) → estAlimentePar(?b, ?s)`.
- **Individus** (valeurs lues dans l'ontologie) :

| Individu | Type asserté | Puissance | Mise en service | Injecte dans |
| --- | --- | --- | --- | --- |
| CentraleSolaire_Tozeur | Solaire | 10 000 kW | 2019-05-10 | Ligne_Tunis_Sousse |
| Panneau_Maison1 | Solaire | 5 kW | — | — |
| ParcEolien_SidiDaoud | Eolien | 54 000 kW | 2000-10-01 | Ligne_Tunis_Sousse |
| Eolienne_Bizerte | Eolien | 2 000 kW | — | Ligne_Ariana |
| CentraleGaz_Rades | SourceNonRenouvelable | 470 000 kW | 1985-01-01 | Ligne_Tunis_Sousse |

Seul le type le plus précis est asserté : Solaire, par exemple, et pas `SourceRenouvelable`. Les requêtes
utilisent `rdfs:subClassOf*`, si bien qu'une « source renouvelable » inclut Solaire et Eolien.

Écarts et compléments par rapport à la présentation :

- l'ontologie contient aussi **R6** (via un stockage) et **R7** (via le raccordement d'un bâtiment) : elles
  déduisent aussi `estAlimentePar` et sont prises en compte ;
- la propriété `estStockePar` (inverse de `stockeEnergieDe`) a été ajoutée par le module Stockage ;
- `STEP ⊑ stockeEnergieDe only SourceRenouvelable` (module Stockage) contraint le type des sources stockées par une STEP.

## Restrictions OWL et contrôles applicatifs

| Contrôle | Origine |
| --- | --- |
| un seul type parmi les 5 classes de la hiérarchie | disjonctions (pas de type incompatible) |
| éolienne : au moins une ligne d'injection | `Eolien ⊑ injecteDans some LigneElectrique` (*) |
| puissance : nombre fini, ≥ 0, une seule valeur, ≤ 10 000 000 kW ; vide = « non renseignée », jamais 0 | `puissanceInstallee` fonctionnelle + règle applicative |
| date au format de l'ontologie (`AAAA-MM-JJT00:00:00`), pas dans le futur | règle applicative |
| lignes et bâtiments : individus existants du bon type | domaines et codomaines |
| URI unique ; libellé unique parmi les sources | règle applicative (convention des autres modules) |
| type compatible avec les stockages qui imposent `stockeEnergieDe only C` | axiome du module Stockage |

(*) Sous l'hypothèse du monde ouvert, une éolienne sans ligne n'est pas incohérente pour HermiT : la ligne
pourrait exister sans être connue. L'application exige donc explicitement au moins une ligne.

Toute la validation a lieu **avant** l'écriture : une requête refusée laisse le graphe inchangé (vérifié
par isomorphisme après 13 refus). L'écriture passe ensuite par `store.update`, qui exécute la requête sous
le verrou partagé du graphe et sauvegarde dans `backend/data/smartgrid.owl`.

## Qui écrit quoi : relations directes et déduites

| Relation | Écrite par | Dans le détail d'une source |
| --- | --- | --- |
| `source produitEnergiePour bâtiment` | Production (formulaire) | lien direct, modifiable ici |
| `bâtiment estAlimentePar source` | Bâtiments | lien direct, en lecture seule (à modifier dans Bâtiments) |
| R1 : `injecteDans` + `transporteVers` | déduit | modifier `injecteDans` (ici) ou `transporteVers` (Réseau) |
| R7 : `injecteDans` + `estRaccordeA` | déduit | modifier `injecteDans` (ici) ou `estRaccordeA` (Bâtiments) |
| R6 : `stockeEnergieDe` + `alimente` | déduit | modifier le stockage (module Stockage) |

Le détail d'une source affiche chaque chemin, `source → ligne → bâtiment` : un bâtiment n'apparaît qu'une fois,
avec toutes ses justifications. Par exemple, Usine_Sfax est alimentée par ParcEolien_SidiDaoud via R1, R6 et R7.
Les stockages (`stockeEnergieDe`) et les mesures de production (`concerne`) sont affichés en lecture seule.

**Modification** : seuls les triplets possédés par Production sont réécrits (`DELETE/INSERT`) : type de la
hiérarchie, libellé, puissance, date, `injecteDans` et `produitEnergiePour`. Les `estAlimentePar` des
Bâtiments, les `stockeEnergieDe` du Stockage et les `concerne` des Mesures ne sont jamais touchés.

**Suppression** : les relations entrantes et sortantes sont examinées d'abord (`GET /sources/<id>/dependances`).

- Toute relation entrante (`estAlimentePar`, `stockeEnergieDe`, `concerne`…), ou sortante non possédée
  (`estStockePar`), bloque la suppression : réponse **409** avec la liste des dépendances, sans suppression en cascade.
- Sinon, seuls les triplets de la source partent (dont `injecteDans` et `produitEnergiePour`), et elle est
  retirée de `owl:AllDifferent`.
- Les 5 sources de l'ontologie sont toutes référencées par un autre module : aucune n'est supprimable telle quelle.

## R1 : mécanisme réel

RDFLib n'exécute pas SWRL. R1 (comme R6 et R7) est **réécrite en SPARQL** dans `queries.chemins()` et
évaluée à chaque lecture sur le graphe courant. Aucune déduction n'est stockée, donc rien ne devient obsolète
après une modification : en changeant l'injection d'une source de `Ligne_MT_Lac` à `Ligne_Ariana`, les
bâtiments du Lac disparaissent et l'hôpital apparaît (vérifié).

HermiT a été lancé sur des copies du graphe : il déduit exactement les mêmes paires `estAlimentePar` que la
réécriture SPARQL (11 paires sur l'ontologie actuelle, 14 avec une source de test).

## API

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/production/sources?q=&categorie=renouvelable\|non_renouvelable\|solaire\|eolien\|non_classee&puissanceMin=&puissanceMax=&sansPuissance=true&dateMin=&dateMax=` | liste, recherche (nom, libellé, URI, sans accents) et filtres |
| GET | `/api/production/sources/<id>` | détail : chemins d'alimentation, lignes, stockages, mesures |
| GET | `/api/production/sources/<id>/dependances` | dépendances bloquantes et triplets supprimés avec la source |
| POST / PUT / DELETE | `/api/production/sources[/<id>]` | CRUD (422 champ par champ, 409 si dépendances) |
| GET | `/api/production/stats` | nombres, renouvelable / non renouvelable, puissance totale (kW), par type, énergie mesurée (kWh) |
| GET | `/api/production/options` | lignes, bâtiments, sources pour les formulaires |
| POST | `/api/production/nlp` `{ "question": "..." }` | question → SPARQL → résultats (lecture seule) |
| GET | `/api/production/nlp/exemples` | questions d'exemple |

## kW et kWh

- **Puissance installée** (`puissanceInstallee`, **kW**) : la capacité d'une installation. Le tableau de bord
  la totalise, mais les sources sans valeur sont signalées et ne comptent jamais pour 0.
- **Énergie mesurée** (**kWh**) : uniquement la somme des `valeurKWh` des mesures de production existantes
  (module Mesure), avec leur période (première date → dernière date) et un avertissement si des mesures d'une
  même source se chevauchent. Aucune énergie n'est estimée à partir de la puissance.
- Le NLP convertit MW, GW et W en kW. Une valeur en kWh dans une question de puissance est refusée avec une explication.

## Exemples SPARQL

Ces exemples ont été exécutés sur l'ontologie par `verifications/verif_readme.py`.

Sources renouvelables, sous-classes comprises :

```sparql
SELECT ?s ?label WHERE {
  ?s a/rdfs:subClassOf* sg:SourceRenouvelable .
  OPTIONAL { ?s rdfs:label ?label }
}
```

Puissance installée totale des sources solaires (kW) :

```sparql
SELECT (SUM(?p) AS ?totalKW) (COUNT(?s) AS ?nbSources) WHERE {
  { SELECT DISTINCT ?s ?p WHERE { ?s a/rdfs:subClassOf* sg:Solaire . OPTIONAL { ?s sg:puissanceInstallee ?p } } }
}
```

R1 réécrite : bâtiments alimentés par CentraleSolaire_Tozeur via une ligne qui les dessert :

```sparql
SELECT DISTINCT ?b ?l WHERE {
  sg:CentraleSolaire_Tozeur a/rdfs:subClassOf* sg:SourceEnergie ;
                            sg:injecteDans ?l .
  ?l sg:transporteVers ?b .
}
```

Création d'une source :

```sparql
INSERT DATA {
  sg:CentraleSolaire_Kairouan a owl:NamedIndividual, sg:Solaire ;
    rdfs:label "Centrale solaire de Kairouan"@fr ;
    sg:puissanceInstallee "1500.0"^^xsd:float ;
    sg:dateMiseEnService "2021-06-15T00:00:00"^^xsd:dateTime ;
    sg:injecteDans sg:Ligne_Ariana .
}
```

Modification de la puissance (propriété fonctionnelle : une seule valeur) :

```sparql
DELETE { sg:CentraleSolaire_Kairouan sg:puissanceInstallee ?p }
INSERT { sg:CentraleSolaire_Kairouan sg:puissanceInstallee "2000.0"^^xsd:float }
WHERE  { OPTIONAL { sg:CentraleSolaire_Kairouan sg:puissanceInstallee ?p } }
```

## NLP : français → SPARQL

Outils réellement utilisés : **spaCy 3.8** et **`fr_core_news_sm`**.

- Tokenisation, lemmes, POS et NER : la NER est affichée, mais ne sert pas à décider.
- **`PhraseMatcher`** relie les mots aux individus (sources, lignes, bâtiments), à partir des libellés et identifiants.
  Un nom exact l'emporte sur un nom de lieu : « Maison1 » désigne le bâtiment, pas Panneau_Maison1.
- **`Matcher`** (motifs de tokens) reconnaît :
  - les puissances : « 100 kW », « 2,5 MW » (converti en 2 500 kW), « 100kW » ;
  - les énergies (« 100 kWh »), pour les refuser ;
  - les dates : « 1 janvier 2020 », « mai 2019 », « 31/12/2019 », « 2019-05-10 », « en, depuis, après, avant 2010 »,
    « entre 1990 et 2010 ».

Le reste repose sur des règles et des dictionnaires métier, appliqués aux lemmes et aux formes normalisées
(sans accents) :

- **intentions** : lister, compter (« combien »), somme (« totale »), moyenne, max ou min (« la plus puissante »,
  « la plus récente »), existe ;
- **cibles** : sources, lignes d'injection (« dans quelles lignes injecte… »), bâtiments alimentés
  (« quels bâtiments sont alimentés par… ») ;
- **catégories** : renouvelable, non renouvelable (« fossile », « gaz »), solaire (« photovoltaïque »,
  « panneaux »), éolien (« éolienne », « vent ») ;
- **comparateurs** : « supérieure à », « au moins », « moins de », « comprise entre … et … ».

La requête est construite par patrons contrôlés : les URI passent par `iri()`, les littéraux par `Literal().n3()`.
Elle est exécutée sur le graphe réel. Le traducteur est en lecture seule.

Comportements prévus :

- **nom ambigu** (« le Lac ») : demande de précision avec les candidats. Les candidats incompatibles avec la
  cible sont écartés : « alimentés par Tozeur » donne la centrale solaire ;
- **identifiant inconnu** (« Centrale_Inconnue ») : demande de vérifier, aucune URI n'est inventée ;
- **date sans année** : l'année est demandée ;
- **kWh** : refus avec l'explication puissance / énergie ;
- **écriture** : refusée ; **question hors domaine** : liste de ce qui est pris en charge ;
- **résultat vide** : explication. Les sources sans puissance ou sans date sont exclues des filtres
  correspondants, et le signalent.

Pour l'alimentation, une seule ligne par bâtiment ou par source, avec la liste des justifications
(estAlimentePar, produitEnergiePour, R1, R7, R6).

Limites :

- la reconnaissance se fait par règles : une formulation très éloignée n'est pas comprise ;
- pas de négation (sauf « non renouvelable ») ;
- une seule période ;
- les nombres écrits en lettres ne sont pas reconnus ;
- pas de question sur l'énergie produite (kWh) : elle relève du module Mesure.

## Lancement et vérification

```bash
cd backend && python app.py            # http://localhost:5000/api/production/stats
cd frontend && npx ng serve            # http://localhost:4200/production
```

Les scripts de vérification se lancent depuis `backend/` (sous Windows : `python -X utf8`). Ils travaillent
sur une copie temporaire du graphe courant, sauf `verif_live.py`.

| Commande | Résultat observé |
| --- | --- |
| `python modules/production/verifications/verif_crud.py` | 34/34 : 13 refus sans écriture, sous-classes, R1 avant/après, 409 sans cascade, contrainte STEP |
| `python modules/production/verifications/verif_hermit.py FICHIER.owl --comparer-sparql` | cohérente ; HermiT = SPARQL (11 paires sur l'ontologie actuelle) |
| `python modules/production/verifications/verif_hermit.py <controle_step.owl> --incoherent` | incohérente : `STEP only SourceRenouvelable` + disjonction |
| `python modules/production/verifications/verif_persistance.py` | 5/5 : relue dans un nouveau processus, isomorphe après nettoyage |
| `python modules/production/verifications/verif_non_regression.py` | 8/8 : 79 réponses des autres modules identiques |
| `python modules/production/verifications/verif_live.py avant\|apres URL` | vrai serveur via le proxy, redémarrage, isomorphe à l'instantané |
| `python modules/production/verifications/verif_readme.py` | exemples SPARQL de ce fichier exécutés |

## Démonstration (≈ 5 min)

1. **/production** : les indicateurs. 5 sources (4 renouvelables, 1 non renouvelable) ; 536 MW installés ;
   520 kWh mesurés en janvier 2025, une seule mesure. Expliquer : kW ≠ kWh.
2. **Filtres** : « Renouvelables » donne Solaire et Éolien, sans type parent asserté. Puis un minimum de 1 000 kW,
   une recherche « eolien » (sans accent) et une date de mise en service.
3. **Détail** de ParcEolien_SidiDaoud : Usine_Sfax avec trois justifications (R1, R6, R7), Mairie_Nabeul
   (estAlimentePar, côté Bâtiments), STEP de Sejnane en stockage.
4. **Créer** une source Solaire « Centrale solaire de Kairouan » : 1 500 kW, injecte dans Ligne Ariana.
   Dans le détail, l'hôpital apparaît via R1 et l'école via R7. Essayer d'abord une puissance négative,
   ou le type Éolien sans ligne, pour montrer les refus.
5. **Modifier** l'injection vers Ligne MT Lac : les bâtiments changent aussitôt.
6. **Supprimer** CentraleGaz_Rades : refus, avec la liste des dépendances. Supprimer ensuite la source de démonstration.
7. **Question (NLP)** : « Quelles sources alimentent Maison1 ? », puis « quelles éoliennes dépassent 2 MW »,
   « sources alimentant le Lac » (demande de précision) et « énergie supérieure à 100 kWh » (refus expliqué).

## Pour la soutenance

- **Ontologie** : hiérarchie à 5 classes et deux disjonctions ; `Eolien ⊑ injecteDans some LigneElectrique` ;
  `puissanceInstallee` fonctionnelle ; `produitEnergiePour ≡ estAlimentePar⁻¹` ; R1, avec R6 et R7, qui
  déduisent `estAlimentePar`.
- **CRUD SPARQL** :
  - SELECT avec `rdfs:subClassOf*` et des agrégats (`COUNT`, `SUM`) ;
  - `INSERT DATA` pour créer, `DELETE/INSERT WHERE` pour modifier, `DELETE WHERE` pour supprimer ;
  - les règles sont réécrites en SPARQL et évaluées à chaque lecture ;
  - la suppression est refusée en 409 si un autre module référence la source.
- **Front ↔ back** : Angular (`/api/production/...`) → proxy → Flask → `store.select` / `store.update`
  (RDFLib, verrou partagé) → sauvegarde dans `backend/data/smartgrid.owl`.
- **NLP** : spaCy `fr_core_news_sm` + `PhraseMatcher` + `Matcher` + règles + patrons SPARQL. Aucun LLM.
- **kW / kWh** : la puissance installée (kW) est une donnée de l'ontologie ; l'énergie (kWh) ne provient que des
  mesures. Le module ne les mélange jamais.
