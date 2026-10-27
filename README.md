# Smart Grid — Web Sémantique (5TWIN)

Ontologie OWL (Protégé) → backend **Python + Flask + RDFLib** → frontend **Angular 18**.

## Lancer le projet

```bash
# 1. Backend (http://localhost:5000)
cd backend
pip install -r requirements.txt
python -m spacy download fr_core_news_sm   # modèle français pour le module NLP
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
| 2 · Takoua Naceur | Stockage | `backend/modules/stockage/` | `frontend/src/app/pages/stockage/` |
| 3 · Abir Mosrati | Bâtiments | `backend/modules/batiments/` | `frontend/src/app/pages/batiments/` |
| 4 · Nourane Lammouchi | Réseau ✅ | `backend/modules/reseau/` | `frontend/src/app/pages/reseau/` |
| 5 · Ibtihel Mechergui | Mesure | `backend/modules/mesure/` | `frontend/src/app/pages/mesure/` |

Le module **Réseau** est complet et sert d'exemple :

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
