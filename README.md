# Smart Grid — Web Sémantique (5TWIN)

Ontologie OWL (Protégé) → backend **Python + Flask + RDFLib** → frontend **Angular 18**.

## Lancer le projet

```bash
# 1. Backend (http://localhost:5000)
cd backend
pip install -r requirements.txt
python -m spacy download fr_core_news_sm   # modèle français pour les modules NLP
python scripts/verifier_hermit.py           # optionnel : cohérence HermiT (pip install owlready2, Java)
python app.py

# 2. Frontend (http://localhost:4200) — dans un autre terminal
cd frontend
npm install
npx ng serve
```

Le frontend appelle `/api/...` ; `frontend/proxy.conf.json` redirige vers Flask (pas de CORS à gérer).

## Données

- `SmartGrid-1.owl` : l'ontologie Protégé, **jamais modifiée** par l'application.
- `backend/data/smartgrid.owl` : copie de travail créée au premier lancement ; toutes les
  opérations CRUD y sont écrites. `POST /api/reset` (ou supprimer ce fichier) repart de l'ontologie Protégé.
- RDFLib ne fait pas tourner HermiT ni SWRL : les inférences utiles (classes définies, règles)
  sont réécrites en SPARQL dans les requêtes de chaque module.

## Organisation : un dossier par membre

| Membre | Module | Backend | Frontend |
|---|---|---|---|
| 1 · Wala Rezgui | Production | `backend/modules/production/` | `frontend/src/app/pages/production/` |
| 2 · Takoua Naceur | Stockage ✅ | `backend/modules/stockage/` | `frontend/src/app/pages/stockage/` |
| 3 · Abir Mosrati | Bâtiments ✅ | `backend/modules/batiments/` | `frontend/src/app/pages/batiments/` |
| 4 · Nourane Lammouchi | Réseau ✅ | `backend/modules/reseau/` | `frontend/src/app/pages/reseau/` |
| 5 · Ibtihel Mechergui | Mesure | `backend/modules/mesure/` | `frontend/src/app/pages/mesure/` |

Les modules **Réseau**, **Stockage** et **Bâtiments** sont complets ; Réseau sert d'exemple :

- `queries.py` — toutes les requêtes SPARQL (SELECT avec filtres, agrégats, INSERT DATA, DELETE/INSERT, DELETE WHERE, ASK) ;
- `routes.py` — le Blueprint Flask (`/api/reseau/...`) ;
- `pages/reseau/` — service Angular, page, formulaires, graphe SVG.

Partagé par tous (à réutiliser plutôt que recopier) :

- `backend/store.py` — le graphe RDFLib, `select()`, `ask()`, `update()`, ajout/retrait dans `owl:AllDifferent` ;
- `frontend/src/styles.scss` — le design system (couleurs par domaine, `.card`, `.btn`, `.badge`, `.input`, `table.data`, `.skeleton`, `.modal`, mode sombre) ;
- `frontend/src/app/shared/` — `app-icon`, `app-sparql-panel`, `app-chip-select`, `ToastService`.

## API Réseau

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/reseau/lignes?q=&categorie=HT\|MT\|BT&tensionMin=&tensionMax=&poste=` | Liste filtrée + classe déduite + gestionnaires (R4) |
| GET | `/api/reseau/lignes/<id>` | Détail : sources qui injectent, bâtiments raccordés |
| POST / PUT / DELETE | `/api/reseau/lignes[/<id>]` | CRUD (`?force=true` pour supprimer malgré les dépendances) |
| GET | `/api/reseau/postes?q=` | Postes + connexions symétriques + bâtiments desservis (R3) |
| POST / PUT / DELETE | `/api/reseau/postes[/<id>]` | CRUD (refus si une ligne n'aurait plus de poste) |
| GET | `/api/reseau/stats` | COUNT / SUM / MAX par catégorie |
| GET | `/api/reseau/graphe` | Nœuds et arêtes du réseau |
| POST | `/api/reseau/nlp` `{ "question": "..." }` | Question en français → analyse spaCy → SPARQL → résultats |
| GET | `/api/reseau/nlp/exemples` | Questions d'exemple |
| POST | `/api/sparql` | Console SPARQL en lecture seule (SELECT / ASK) |

Les POST/PUT invalides renvoient **422** avec une erreur par champ : `{ "error": "...", "champs": { "tension": "..." } }`.

## Réseau : ontologie enrichie

`backend/scripts/enrichir_reseau.py` a ajouté à `SmartGrid-1.owl` (sauvegarde de l'ancienne version dans `backups/`) :

- **Classe définie** `LigneMoyenneTension ≡ LigneElectrique ⊓ tension some float[> 1, < 63]`
- **Axiomes** : HT / MT / BT deux à deux disjointes · `LigneHauteTension ⊑ relie min 2 PosteElectrique` ·
  `PosteElectrique ⊑ estReliePar some LigneElectrique`
- **ObjectProperty** : `estReliePar` (inverse de `relie`), `secourt` (asymétrique, irréflexive)
- **DataProperty** (fonctionnelles) : `capaciteTransformation` (MVA), `ville`, `anneeMiseEnService`
- **Individus** : 5 postes (Bizerte, Sousse, Gabès, Tozeur, Nabeul) et 8 lignes, soit 8 postes et 11 lignes au total

Le script ne refait rien s'il a déjà tourné. Après une modification de `SmartGrid-1.owl`, lancer `POST /api/reset`.

## Réseau : module NLP → SPARQL (sans API de LLM)

`backend/modules/reseau/nlp.py` : **spaCy 3.8** + modèle **`fr_core_news_sm`** (tokenisation, lemmatisation,
étiquettes morpho-syntaxiques, entités nommées) et **`PhraseMatcher`** de spaCy pour relier les mots
aux individus de l'ontologie (libellés, identifiants, villes).
Règles : intention (lister, compter, max, min, somme, moyenne, existe), classe cible, catégorie HT/MT/BT,
comparaisons numériques avec unités (kV, km, MVA, années), relations (connexion, secours, R3, R4)
→ requête SPARQL générée puis exécutée par RDFLib.


## API Stockage

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/stockage/systemes?q=&famille=&definie=vert\|critique\|grande\|secours&niveauMin=&niveauMax=&capaciteMin=&source=&batiment=&poste=` | Liste filtrée + classes définies déduites + énergie disponible et autonomie |
| GET | `/api/stockage/systemes/<id>` | Détail + tous les triplets RDF de l'individu |
| POST / PUT / DELETE | `/api/stockage/systemes[/<id>]` | CRUD (`?force=true` pour supprimer malgré les dépendances) |
| PATCH | `/api/stockage/systemes/<id>/niveau` `{ "niveau": 35 }` | Recharge / décharge : DELETE/INSERT sur `niveauCharge` (fonctionnelle) |
| GET | `/api/stockage/stats` | COUNT / SUM / AVG, effectifs par famille et par classe définie |
| GET | `/api/stockage/batiments` | Bâtiments, `possedeStockage` (R2), sources renouvelables (direct, inverse, R1, R6), `BatimentAutonome` |
| GET | `/api/stockage/scenario?poste=&heures=` | Scénario coupure : bâtiments desservis (R3) et autonomie grâce à leur stockage (R2) |
| POST | `/api/stockage/scenario/appliquer` `{ "poste": "...", "heures": 4 }` | Applique la coupure : décharge les stockages (SPARQL UPDATE) |
| POST | `/api/stockage/nlp` `{ "question": "..." }` | Question en français → spaCy → SPARQL → résultats |
| GET | `/api/stockage/nlp/exemples` | Questions d'exemple |

Les POST/PUT invalides renvoient **422** avec une erreur par champ ; chaque règle cite l'axiome qu'elle applique.

## Stockage : ontologie enrichie

`backend/scripts/enrichir_stockage.py` a ajouté à `SmartGrid-1.owl` (sauvegarde dans `backups/`, ne refait rien s'il a déjà tourné) :

- **Classes** : `BatteriePlomb ⊑ Batterie` (disjointe de `BatterieLithiumIon`), `VolantInertie ⊑ SystemeStockage` ;
  Batterie / StockageHydrogene / STEP / VolantInertie deux à deux disjointes
- **4 classes définies** :
  `StockageVert ≡ SystemeStockage ⊓ stockeEnergieDe some SourceRenouvelable` ·
  `StockageCritique ≡ SystemeStockage ⊓ niveauCharge some float[< 20]` ·
  `StockageGrandeCapacite ≡ SystemeStockage ⊓ capaciteStockage some float[≥ 10000]` ·
  `StockageSecours ≡ SystemeStockage ⊓ alimente some BatimentPublic`
- **Axiomes** : `SystemeStockage ⊑ niveauCharge only float[≥ 0, ≤ 100]` · `SystemeStockage ⊑ rendement only float[> 0, ≤ 100]` ·
  `StockageHydrogene ⊑ stockeEnergieDe some SourceRenouvelable` · `VolantInertie ⊑ raccordeAuPoste exactly 1 PosteElectrique`
- **ObjectProperty** : `estStockePar` (inverse de `stockeEnergieDe`), `raccordeAuPoste` (fonctionnelle, vers `PosteElectrique`)
- **DataProperty** (fonctionnelles) : `rendement` (%), `puissanceDecharge` (kW), `technologie`, `anneeInstallation` ; `niveauCharge` devient fonctionnelle
- **Règle SWRL R6** : `SystemeStockage(?x) ^ stockeEnergieDe(?x, ?s) ^ alimente(?x, ?b) → estAlimentePar(?b, ?s)`
  (un bâtiment alimenté par un stockage l'est indirectement par la source stockée : Immeuble_Lac et Ecole_Ariana deviennent `BatimentAutonome`)
- **Individus** : 4 nouveaux (Batterie_Ecole_Ariana, Batterie_Immeuble_Lac, Volant_Rades, Batterie_Reseau_Tozeur) et données complétées pour les 5 existants, soit 9 systèmes

Vérifié avec HermiT (`scripts/verifier_hermit.py`) : ontologie cohérente, 0 classe insatisfiable.

## Stockage : module NLP → SPARQL (sans API de LLM)

`backend/modules/stockage/nlp.py`, outils utilisés :

- **spaCy 3.8** + modèle **`fr_core_news_sm`** : tokenisation, lemmatisation, étiquettes POS, **NER** (entités `LOC` pour les lieux) ;
- **`PhraseMatcher`** de spaCy : relie les mots aux individus (libellés, identifiants, alias non ambigus) et au vocabulaire
  des classes (« lithium » → `BatterieLithiumIon`, « à recharger » → `StockageCritique`, « non renouvelable » → ¬`StockageVert`) ;
- **`Matcher`** de spaCy (motifs de tokens) : quantités avec unités et conversion (« 10 MWh » → 10 000 kWh, « 1 MW », « 20 % »),
  intervalles « entre 100 et 1000 kWh ».

Règles : intention (lister, compter, somme, moyenne, max, min, existe), cible (stockages, bâtiments, sources),
superlatifs (« la plus chargée », « meilleur rendement »), comparaisons, années → requête SPARQL (avec les classes
définies et les règles R2, R6, R1, R3 réécrites) exécutée par RDFLib.


## API Bâtiments

| Méthode | Route | Description |
|---|---|---|
| GET | `/api/batiments/batiments?q=&type=&definie=autonome\|vert\|gros\|intelligent\|ht&consoMin=&consoMax=&dpe=&ligne=&poste=&source=` | Liste filtrée + 5 classes définies déduites + intensité et classe DPE recalculée + lignes, sources (direct, inverse, R1, R6, R7), stockages (R2), postes (R3), compteurs |
| GET | `/api/batiments/batiments/<id>` | Détail (chaîne d'alimentation) + tous les triplets RDF de l'individu |
| POST / PUT / DELETE | `/api/batiments/batiments[/<id>]` | CRUD (`?force=true` pour supprimer malgré les dépendances) |
| PATCH | `/api/batiments/batiments/<id>/consommation` `{ "consommation": 2500000 }` | DELETE/INSERT sur `consommationAnnuelle` (fonctionnelle) → GrosConsommateur recalculé |
| GET | `/api/batiments/stats` | COUNT / SUM / AVG, effectifs par type et par classe définie, part de consommation verte |
| GET | `/api/batiments/options` | Lignes (tension, sources injectées pour R7), sources, stockages (sources stockées pour R6), postes |
| GET | `/api/batiments/inferences` | Tableau « déclaré / déduit / grâce à » (comme la diapo HermiT) + relations déduites |
| GET | `/api/batiments/diagnostic` | Intensité (kWh/m²·an) et classe DPE calculées en SPARQL vs classe déclarée |
| POST | `/api/batiments/diagnostic/appliquer` `{ "ids": ["Maison1"] }` | Corrige `classeEnergetique` (SPARQL UPDATE) ; sans `ids` : tous les écarts |
| POST | `/api/batiments/nlp` `{ "question": "..." }` | Question en français → spaCy → SPARQL → résultats |
| GET | `/api/batiments/nlp/exemples` | Questions d'exemple |

Les POST/PUT invalides renvoient **422** avec une erreur par champ ; chaque règle cite l'axiome qu'elle applique
(`Batiment ⊑ estRaccordeA some LigneElectrique`, `BatimentIndustriel ⊑ estRaccordeA some (LigneMoyenneTension ⊔ LigneHauteTension)`,
`BatimentPublic ⊑ estAlimentePar min 2 SourceEnergie` en comptant aussi les sources déduites par R7 et R6, plages de valeurs, énumération DPE).

## Bâtiments : ontologie enrichie

`backend/scripts/enrichir_batiments.py` a ajouté à `SmartGrid-1.owl` (sauvegarde dans `backups/`, ne refait rien s'il a déjà tourné) :

- **Classe** : `BatimentCommercial ⊑ Batiment` ; Résidentiel / Industriel / Public / Commercial deux à deux disjointes
- **4 classes définies** (en plus de `BatimentAutonome`) :
  `BatimentVert ≡ Batiment ⊓ estAlimentePar some SourceRenouvelable` ·
  `GrosConsommateur ≡ Batiment ⊓ consommationAnnuelle some float[≥ 1000000]` ·
  `BatimentIntelligent ≡ Batiment ⊓ equipeDe some CompteurIntelligent` ·
  `BatimentRaccordeHT ≡ Batiment ⊓ estRaccordeA some LigneHauteTension` (chaîne : tension ≥ 63 kV → LigneHauteTension → BatimentRaccordeHT)
- **Axiomes** : `Batiment ⊑ consommationAnnuelle only float[≥ 0]` · `surface only float[> 0]` · `nombreOccupants only integer[≥ 0]` ·
  `classeEnergetique only {"A", "B", "C", "D", "E", "F", "G"}` (énumération) ·
  `BatimentIndustriel ⊑ estRaccordeA some (LigneMoyenneTension ⊔ LigneHauteTension)` (union)
- **ObjectProperty** : `equipeDe` (inverse de `installeDans`)
- **DataProperty** (fonctionnelles) : `surface` (m²), `nombreOccupants`, `anneeConstruction`, `classeEnergetique`, `puissanceSouscrite` (kW) ;
  `consommationAnnuelle` devient fonctionnelle
- **Règle SWRL R7** : `Batiment(?b) ^ estRaccordeA(?b, ?l) ^ injecteDans(?s, ?l) → estAlimentePar(?b, ?s)`
- **Individus** : 4 nouveaux (Mairie_Nabeul, Villa_Hammamet, Cimenterie_Gabes, Centre_Commercial_Lac) et données complétées pour les 5 existants, soit 9 bâtiments

Vérifié avec HermiT (`scripts/verifier_hermit.py`) : ontologie cohérente, 0 classe insatisfiable ;
BatimentAutonome ← 5, BatimentVert ← 6, GrosConsommateur ← 4, BatimentIntelligent ← 2, BatimentRaccordeHT ← 2
(exactement les mêmes individus que les requêtes SPARQL du backend).

## Bâtiments : module NLP → SPARQL (sans API de LLM)

`backend/modules/batiments/nlp.py` : **spaCy 3.8** + **`fr_core_news_sm`** (tokens, lemmes, POS, NER `LOC`),
**`PhraseMatcher`** (individus : bâtiments, sources, lignes, postes, stockages ; types « usine » → `BatimentIndustriel` ;
classes définies « énergivore » → `GrosConsommateur`, « sans batterie » → ¬`possedeStockage`),
**`Matcher`** (quantités : « 2 GWh » → 2 000 000 kWh, « 500 m² », « 200 kWh/m² », « entre 100 et 5000 m² », « 1 GWh ou plus »).
Règles : intention (lister, compter, somme, moyenne, max, min, existe), cible (bâtiments, sources qui les alimentent,
postes qui les desservent), superlatifs (« le plus ancien », « le plus économe », « consomme le plus »), classe DPE
(« classe D ou pire »), lieux (ville d'un poste via R3, ou adresse) → requête SPARQL exécutée par RDFLib.

## Bâtiments : interface (`/batiments`)

4 onglets : **Bâtiments** (tableau filtrable, CRUD avec contrôle de saisie et aperçu des classes déduites en direct,
fiche avec chaîne d'alimentation sources → lignes → postes, mise à jour de la consommation) ·
**Déclaré / déduit** (ce que HermiT déduit, recalculé en SPARQL avec la justification) ·
**Diagnostic énergétique** (intensité et classe DPE calculées, correction par SPARQL UPDATE) · **Question (NLP)**.
