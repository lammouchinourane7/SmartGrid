# Module 5 · Gestion et mesure — Ibtihel Mechergui

Compteurs intelligents, mesures de consommation / production et opérateurs réseau.
Même architecture que les autres modules : **Flask + RDFLib** (`backend/modules/mesure/`) et
**Angular 18** (`frontend/src/app/pages/mesure/`). Aucune API de LLM.

| Fichier | Rôle |
| --- | --- |
| `queries.py` | toutes les requêtes SPARQL (SELECT filtrés, agrégats, INSERT DATA, DELETE/INSERT, DELETE WHERE, ASK) |
| `validation.py` | contrôle de saisie (422 avec une erreur par champ, axiome cité) |
| `routes.py` | Blueprint `/api/mesure/...` |
| `nlp.py` | traducteur français → SPARQL (spaCy) |
| `pages/mesure/` | page, service, modèles, 3 formulaires, composant NLP |
| `verifications/` | scripts de vérification (scénario conserver, HermiT, persistance, non-régression, serveur réel, isomorphisme) |

## Ontologie utilisée (rien n'a été ajouté)

- **Classes** : `CompteurIntelligent`, `Mesure`, `MesureConsommation ⊑ Mesure`, `MesureProduction ⊑ Mesure` (disjointes), `OperateurReseau`
- **ObjectProperties** : `installeDans` (fonctionnelle, Compteur → Batiment), `enregistre` (Compteur → Mesure),
  `concerne` (Mesure → Batiment ⊔ SourceEnergie), `gere` (Opérateur → InfrastructureReseau) ;
  lue aussi : `equipeDe ≡ installeDans⁻¹` (ajoutée par le module Bâtiments)
- **DataProperties** : `identifiant` (string, fonctionnelle), `valeurKWh` (float, fonctionnelle), `dateDebut`, `dateFin` (dateTime)
- **Axiomes** : `CompteurIntelligent ⊑ installeDans exactly 1 Batiment` · `CompteurIntelligent ⊑ enregistre some Mesure` ·
  `MesureConsommation ⊑ concerne only Batiment` · `MesureConsommation ⊑ concerne max 1 Batiment` ·
  `MesureProduction ⊑ concerne only SourceEnergie`
- **R5 (SWRL)** : `CompteurIntelligent(?c) ^ installeDans(?c, ?b) ^ enregistre(?c, ?m) ^ MesureConsommation(?m) → concerne(?m, ?b)`

Écarts constatés entre la présentation et `SmartGrid-1.owl` (le fichier n'a pas été modifié) :
`installeDans` est fonctionnelle, `CompteurIntelligent ⊑ enregistre some Mesure` existe dans le fichier mais pas dans
le PDF, et l'ontologie compte désormais plus d'individus que les 27 du PDF (enrichissements des autres modules).
`Mesure_Maison1_Janvier` et `Mesure_Usine_Q1` n'ont **aucun** `concerne` asserté : leur bâtiment vient de R5.
Les mesures existantes datent de 2025 (une question sur 2026 renvoie donc un résultat vide, avec explication).

## R5 : mécanisme réel

RDFLib n'exécute pas SWRL. R5 est **réécrite en SPARQL** et évaluée à chaque requête (motif `r5()` de `queries.py`) :
rien n'est stocké, donc la déduction reste exacte après chaque modification. Dans l'interface, une cible déduite
porte le badge `R5`. HermiT (owlready2) a été lancé sur une copie du graphe de travail : ontologie cohérente,
0 classe insatisfiable, et les `concerne` déduits par HermiT sont identiques à ceux de la requête SPARQL.

## Axiomes OWL et contrôles applicatifs

Sous l'hypothèse du monde ouvert, un raisonneur ne signale ni un compteur sans bâtiment ni une mesure sans valeur.
Le backend ajoute donc des contrôles (le message cite l'axiome, ou « règle applicative ») :

| Contrôle | Origine |
| --- | --- |
| un et un seul bâtiment par compteur, qui doit être un `Batiment` | `installeDans exactly 1 Batiment` |
| consommation : cible `Batiment` ; production : cible `SourceEnergie` | `concerne only …` |
| consommation avec compteur : pas de bâtiment différent de celui du compteur | `max 1 Batiment` + R5 |
| identifiant de compteur unique | règle applicative (`identifiant` est fonctionnelle, pas une clé) |
| valeur ≥ 0, dates valides, `dateFin` > `dateDebut`, une seule valeur par date | règles applicatives |
| `gere` vers une `InfrastructureReseau` existante | range de `gere` |

Consommation **avec** compteur : aucun `concerne` n'est asserté, R5 donne le bâtiment. Sans compteur : `concerne` est asserté.
L'onglet *Bilan* liste aussi les anomalies présentes dans les données (`GET /api/mesure/coherence`).

**Changement de bâtiment d'un compteur** : l'aperçu (`GET /compteurs/<id>/impact`) liste les mesures de
consommation touchées et, pour chaque politique, **les triplets exacts retirés et ajoutés**, affichés avant
confirmation. Sans politique explicite, le PUT répond **409**, sans aucune réaffectation silencieuse :

- `?politique=reaffecter` : les mesures suivent le compteur (R5) ; un `concerne` asserté vers un bâtiment est retiré ;
- `?politique=conserver` : les mesures restent sur l'ancien bâtiment.

Exemple : `Compteur_M1` passe de Maison1 à Villa_Hammamet avec « Conserver ».

| | Avant | Après |
| --- | --- | --- |
| compteur | `Compteur_M1 installeDans Maison1`, `Compteur_M1 enregistre Mesure_Maison1_Janvier` | `Compteur_M1 installeDans Villa_Hammamet` |
| mesure | aucun `concerne` asserté | `Mesure_Maison1_Janvier concerne Maison1`, `rdfs:comment "Enregistrée par sg:Compteur_M1 … (politique conserver)"@fr` |
| R5 | `concerne Maison1` (déduit) | ne s'applique plus : l'atome `enregistre(?c, ?m)` du corps est faux |
| résultat | Maison1 seul | Maison1 seul, par assertion ; jamais Villa_Hammamet |

Le retrait de `enregistre` est indispensable. Si on le gardait, R5 déduirait `concerne Villa_Hammamet` en plus de
Maison1, ce qui viole `concerne max 1 Batiment` : HermiT déclare alors l'ontologie **incohérente** (contrôle négatif
de `verif_conserver.py`). L'historique du compteur est conservé par l'annotation `rdfs:comment` (pas de nouvelle
DataProperty), affichée dans le détail de la mesure. Les mesures de **production** du compteur ne sont pas concernées
par R5 et gardent leur lien `enregistre`.

**Édition d'une mesure** : rattacher à un compteur une mesure dont le `concerne` asserté désigne un autre bâtiment
la ferait changer de bâtiment par R5. Le PUT répond alors **409** tant que `confirmerReaffectation: true` n'est pas
envoyé ; le formulaire affiche l'ancien et le nouveau bâtiment, avec une case à cocher.

**Suppressions** (toujours confirmées dans l'interface) :

- références entrantes d'un autre module → **409 bloquant** ;
- compteur ayant des mesures → 409, puis `force=true` : les mesures sont conservées et leur bâtiment R5 est écrit en `concerne` ;
- opérateur → seuls ses triplets et ses `gere` sont retirés ; aucune infrastructure, aucun bâtiment, aucune source n'est supprimé.

## API

| Méthode | Route | Description |
| --- | --- | --- |
| GET | `/api/mesure/compteurs?q=&batiment=` | liste (bâtiment via installeDans ou equipeDe, mesures) |
| GET | `/api/mesure/compteurs/<id>` | détail + mesures enregistrées |
| GET | `/api/mesure/compteurs/<id>/impact?batiment=` | mesures touchées par un changement de bâtiment |
| POST / PUT / DELETE | `/api/mesure/compteurs[/<id>]` | CRUD (`?politique=reaffecter\|conserver`, `?force=true`) |
| GET | `/api/mesure/mesures?q=&type=&compteur=&cible=&valeurMin=&valeurMax=&debut=&fin=&mode=chevauchement\|inclusion` | recherche et filtres |
| GET | `/api/mesure/mesures/<id>` | détail |
| POST / PUT / DELETE | `/api/mesure/mesures[/<id>]` | CRUD |
| GET | `/api/mesure/operateurs?q=&infrastructure=` | liste + lignes gérées par R4 |
| POST / PUT / DELETE | `/api/mesure/operateurs[/<id>]` | CRUD (`?force=true`) |
| GET | `/api/mesure/stats` | nombres de compteurs, mesures (par type), opérateurs |
| GET | `/api/mesure/bilan?debut=&fin=` | totaux par type et par cible, mesures exclues, chevauchements |
| GET | `/api/mesure/coherence` | anomalies vis-à-vis des axiomes du module |
| GET | `/api/mesure/options` | listes de choix (bâtiments, sources, infrastructures, compteurs, opérateurs) |
| POST | `/api/mesure/nlp` `{ "question": "..." }` | question → SPARQL → résultats |
| GET | `/api/mesure/nlp/exemples` | questions d'exemple |

**Règle temporelle.** La liste et les filtres utilisent le mode *chevauchement* par défaut (la période de la mesure
touche l'intervalle) ou *inclusion*. Les totaux (Bilan, NLP « total / moyenne ») ne prennent **que les mesures
entièrement incluses** : il n'y a pas de proratisation, et les mesures qui chevauchent seulement l'intervalle sont
affichées comme exclues. Consommation et production ne sont jamais additionnées ensemble. Si deux mesures de même
type et de même cible se recouvrent, un avertissement le signale.

## NLP : français → SPARQL

Outils réellement utilisés : **spaCy 3.8** et **`fr_core_news_sm`**.

- Tokenisation, lemmes, POS et NER : la NER est affichée mais ne sert pas à décider, car elle est peu fiable sur ce domaine.
- **`PhraseMatcher`** relie les mots aux individus, à partir des `rdfs:label`, des identifiants et des `sg:identifiant` (« CPT-0002 »).
- **`Matcher`**, avec des motifs de tokens, reconnaît :
  - les dates : « 1 janvier 2026 », « janvier 2026 », « 31/03/2026 », « 2026-03-31 », « 1er trimestre 2025 », « en / depuis / avant 2025 » ;
  - les quantités avec conversion : Wh, kWh, MWh (×1 000), GWh (×10⁶).

Le reste repose sur des règles et des dictionnaires métier, sur les lemmes et les formes normalisées (sans accents) :

- les comparateurs : « supérieures à », « au moins », « moins de », « entre X et Y kWh » ;
- l'intention : lister, compter, somme, moyenne, max, min, existe ;
- la cible : compteurs, mesures (consommation / production), opérateurs, infrastructures gérées.

La requête est construite par **patrons contrôlés** : les URI passent par `iri()`, les littéraux par `Literal().n3()`.
Elle est ensuite exécutée par RDFLib.

Comportements prévus :

- **nom ambigu** (« le Lac » : Immeuble_Lac ou Centre_Commercial_Lac) → demande de précision avec les candidats. Les
  candidats incompatibles avec la cible sont écartés : « opérateurs qui gèrent Sfax » donne le poste, pas l'usine ;
- **identifiant inconnu** (« Compteur_X9 ») → demande de vérifier, aucune URI n'est inventée ;
- **date sans année** (« en janvier ») → demande l'année. Si une autre date de la question porte l'année
  (« entre le 1 janvier et le 31 mars 2025 »), elle est reprise, et la convention est affichée ;
- **valeur sans unité** → kWh, signalé ;
- **demande d'écriture** (« supprime… ») → refusée : le traducteur est en lecture seule et le CRUD se fait dans les onglets ;
- **question hors domaine** → message listant ce qui est pris en charge.

Limites :

- la recherche texte des listes (`?q=`) est sensible aux accents : « verification » ne trouve pas « vérification »,
  comme dans les autres modules. Le NLP, lui, normalise les accents ;
- la reconnaissance se fait par règles : une formulation très éloignée des motifs n'est pas comprise ;
- une seule période et une seule cible par type d'entité ;
- pas de négation (« sauf », « hors ») ni de comparaison entre deux entités ;
- les nombres écrits en lettres ne sont pas reconnus.

## Lancement et vérification

```bash
# backend
cd backend
pip install -r requirements.txt
python -m spacy download fr_core_news_sm
python app.py                                   # http://localhost:5000/api/mesure/stats

# frontend (autre terminal)
cd frontend
npm install
npx ng serve                                    # http://localhost:4200/mesure

# vérifications rapides
curl http://localhost:5000/api/mesure/compteurs
curl "http://localhost:5000/api/mesure/mesures?type=consommation&valeurMin=100"
curl "http://localhost:5000/api/mesure/bilan?debut=2025-01-01&fin=2025-01-31"
curl http://localhost:5000/api/mesure/coherence
```

Sous Windows, envoyer les questions NLP depuis l'interface plutôt qu'avec `curl` : la console peut mal encoder les accents.

## Vérifications

Les scripts sont dans `backend/modules/mesure/verifications/` et se lancent depuis `backend/`.
Sous Windows, ajouter `-X utf8` à `python` pour l'affichage des accents.
Tous travaillent sur une copie temporaire de `SmartGrid-1.owl`, sauf `verif_live.py`.

| Commande | Ce qui est vérifié |
| --- | --- |
| `python modules/mesure/verifications/verif_conserver.py` | scénario « Conserver » : triplets avant/après, R5, refus 409, historique, ré-attachement confirmé, contrôle négatif (14 vérifications) |
| `python modules/mesure/verifications/verif_hermit.py FICHIER.owl Mesure=Bat ... [--incoherent]` | HermiT avec les règles SWRL du fichier : cohérence et `concerne` déduits |
| `python modules/mesure/verifications/verif_persistance.py` | écriture dans un processus, relecture dans un nouvel interpréteur (redémarrage), nettoyage, isomorphisme |
| `python modules/mesure/verifications/verif_non_regression.py` | 60 réponses des autres modules (GET + exemples NLP + console SPARQL) identiques avant/après un cycle CRUD Mesure |
| `python modules/mesure/verifications/verif_live.py avant\|apres [URL]` | vrai serveur HTTP, avec redémarrage manuel entre les deux phases ; instantané puis isomorphisme |
| `python modules/mesure/verifications/verif_isomorphisme.py A.owl B.owl` | identité du contenu RDF (nœuds anonymes compris) |

**HermiT.** `verif_hermit.py` charge le fichier donné en argument avec owlready2, dans un `World` isolé.

- Les 7 règles `swrl:Imp` du fichier (R1 à R7) sont listées puis transmises à HermiT par
  `sync_reasoner(world, infer_property_values=True)`.
- R5 est bien exécutée : sur `SmartGrid-1.owl`, HermiT déduit `Mesure_Usine_Q1 concerne Usine_Sfax`, triplet qui
  n'est pas dans le fichier.
- `scripts/verifier_hermit.py`, le script de l'équipe, ne s'exécute pas sous Windows à cause de
  `Path.as_uri()` ; `verif_hermit.py` passe le chemin en chaîne simple.

## Exemples SPARQL

R5, le bâtiment d'une mesure de consommation :

```sparql
SELECT ?m ?b WHERE {
  ?m a sg:MesureConsommation . ?c a sg:CompteurIntelligent ; sg:enregistre ?m .
  { ?c sg:installeDans ?b } UNION { ?b sg:equipeDe ?c }
}
```

Consommation de Maison1 en janvier 2025 (mesures incluses, cible assertée ou R5) :

```sparql
SELECT (SUM(?v) AS ?totalKWh) (COUNT(?m) AS ?nombre) WHERE {
  { SELECT DISTINCT ?m ?v WHERE {
    ?m a sg:MesureConsommation ; sg:valeurKWh ?v ; sg:dateDebut ?d ; sg:dateFin ?f .
    { ?m sg:concerne sg:Maison1 } UNION {
      ?c a sg:CompteurIntelligent ; sg:enregistre ?m .
      { ?c sg:installeDans sg:Maison1 } UNION { sg:Maison1 sg:equipeDe ?c } }
    FILTER(?d >= "2025-01-01T00:00:00"^^xsd:dateTime && ?f <= "2025-01-31T23:59:59"^^xsd:dateTime)
  } }
}
```

Création d'une mesure (le bâtiment sera déduit par R5) :

```sparql
INSERT DATA {
  sg:Mesure_Maison1_Fevrier a owl:NamedIndividual, sg:MesureConsommation ;
    rdfs:label "Consommation de Maison1 en février 2025"@fr ;
    sg:valeurKWh "310.0"^^xsd:float ;
    sg:dateDebut "2025-02-01T00:00:00"^^xsd:dateTime ; sg:dateFin "2025-02-28T23:59:59"^^xsd:dateTime .
  sg:Compteur_M1 sg:enregistre sg:Mesure_Maison1_Fevrier .
}
```

Infrastructures gérées par STEG (asserté + R4) :

```sparql
SELECT DISTINCT ?x ?via WHERE {
  { sg:STEG sg:gere ?x . BIND("gere" AS ?via) }
  UNION { sg:STEG sg:gere ?p . ?x sg:relie ?p . FILTER NOT EXISTS { sg:STEG sg:gere ?x } BIND("R4" AS ?via) }
}
```

## Démonstration (≈ 5 min)

1. **/mesure, onglet Compteurs** : 2 compteurs, `Compteur_M1` installé dans Maison 1. Ouvrir la fiche pour voir ses 2 mesures.
2. **Créer** une mesure (onglet Mesures, *Nouvelle mesure*) : consommation, 310 kWh, 01/02/2025 → 28/02/2025,
   compteur `Compteur_M1`. L'encadré « Bâtiment déduit par R5 : Maison 1 » apparaît. Enregistrer.
   - Essayer d'abord une date de fin antérieure, ou une valeur négative : les messages s'affichent sous les champs.
3. **Filtrer** : type *Consommation*, kWh min 300, puis une période 01/02 → 28/02 en mode *Chevauche* ou *Incluse*.
   Le panneau « Requête SPARQL exécutée » montre la requête. Dans la colonne *Concerne*, le badge `R5` est visible.
4. **Compteur** : modifier `Compteur_M1` et choisir un autre bâtiment. La liste des mesures touchées apparaît, avec le
   choix *Réaffecter* ou *Conserver*. Annuler.
5. **Bilan** : 01/01/2025 → 31/01/2025. La consommation et la production sont totalisées séparément, et
   `Mesure_Usine_Q1` (janvier–mars) est signalée comme exclue.
6. **Question (NLP)** : « Quelle est la consommation totale de Maison1 en février 2025 ? ». Montrer les tokens et lemmes,
   l'entité `sg:Maison1`, la période reconnue, le SPARQL généré, puis le résultat. Essayer ensuite :
   - « Quelles mesures concernent le Lac ? » : demande de précision ;
   - « Consommation totale en janvier » : l'année est demandée.
7. **Supprimer** la mesure créée : confirmation, puis le graphe revient à son état initial.

## Pour la soutenance

- **Classes et propriétés** : voir « Ontologie utilisée ». `MesureConsommation` et `MesureProduction` sont disjointes ;
  `concerne` a pour codomaine l'union `Batiment ⊔ SourceEnergie`, restreinte par `only` dans chaque sous-classe.
- **Restrictions** : `exactly 1` (compteur), `only` et `max 1` (mesures), `some` (`enregistre some Mesure`).
- **SWRL** : R5 est déclarée dans l'ontologie. HermiT la prend en compte (vérifié), et le backend l'applique en SPARQL
  puisque RDFLib n'exécute pas SWRL.
- **Front ↔ back** : Angular → `/api/mesure/...` (proxy `proxy.conf.json`) → Flask → `store.select` / `store.update`
  sur le graphe RDFLib → sauvegarde dans `backend/data/smartgrid.owl` à chaque écriture.
- **NLP** : spaCy (`fr_core_news_sm`, `PhraseMatcher`, `Matcher`) + règles métier + patrons SPARQL. Aucun LLM.
