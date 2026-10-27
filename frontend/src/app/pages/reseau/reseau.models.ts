export type Categorie = 'HT' | 'MT' | 'BT';

export interface Ligne {
  id: string;
  label: string;
  tension: number | null;
  longueur: number | null;
  annee: number | null;
  categorie: Categorie;
  postes: string[];
  batiments: string[];
  gestionnaires: string[];
  sources?: string[];
  batimentsRaccordes?: string[];
}

export interface Poste {
  id: string;
  label: string;
  ville: string | null;
  capacite: number | null;
  annee: number | null;
  nbLignes: number;
  lignes: string[];
  connexions: string[];
  secours: string[];
  secourusPar: string[];
  gestionnaires: string[];
  batimentsDesservis: string[];
}

export interface Stats {
  nbLignes: number;
  nbPostes: number;
  longueurTotale: number;
  tensionMax: number;
  parCategorie: Record<Categorie, number>;
  sparql: string;
}

export interface Option { id: string; label: string; }

export interface Options {
  postes: Option[];
  batiments: Option[];
  operateurs: Option[];
  sources: Option[];
}

export interface LigneFiltres {
  q?: string;
  categorie?: Categorie | '';
  tensionMin?: number | null;
  tensionMax?: number | null;
  poste?: string;
}

export interface LigneForm {
  id: string;
  label: string;
  tension: number | null;
  longueur: number | null;
  annee: number | null;
  postes: string[];
  batiments: string[];
}

export interface PosteForm {
  id: string;
  label: string;
  ville: string;
  capacite: number | null;
  annee: number | null;
  connexions: string[];
  secours: string[];
  gestionnaires: string[];
}

export interface Dependance { id: string; relation: string; }

export interface GNode {
  id: string;
  label: string;
  type: 'poste' | 'ligne' | 'batiment' | 'source' | 'operateur';
  categorie?: Categorie;
  tension?: number;
}

export interface GEdge { source: string; target: string; relation: string; }

export interface Graphe { nodes: GNode[]; edges: GEdge[]; sparql: string; }

export interface ListResponse<T> { items: T[]; sparql: string; }

export interface MutationResponse { id: string; sparql: string; }

/** Les classes définies de l'ontologie, telles que le backend les déduit en SPARQL. */
export const CATEGORIES: Record<Categorie, { label: string; classe: string; axiome: string; color: string }> = {
  HT: {
    label: 'Haute tension', classe: 'LigneHauteTension',
    axiome: 'LigneElectrique ⊓ tension some float[≥ 63]', color: 'var(--reseau)',
  },
  MT: {
    label: 'Moyenne tension', classe: 'LigneMoyenneTension',
    axiome: 'LigneElectrique ⊓ tension some float[> 1, < 63]', color: 'color-mix(in srgb, var(--reseau) 45%, var(--batiments))',
  },
  BT: {
    label: 'Basse tension', classe: 'LigneBasseTension',
    axiome: 'LigneElectrique ⊓ tension some float[≤ 1]', color: 'var(--muted)',
  },
};

export function categorieDe(tension: number | null | undefined): Categorie | null {
  if (tension == null || isNaN(tension)) return null;
  return tension >= 63 ? 'HT' : tension <= 1 ? 'BT' : 'MT';
}

/** "Ligne Bizerte–Ariana" → "Ligne_Bizerte_Ariana" (identifiant d'individu OWL). */
export function slugify(text: string): string {
  return text
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
}

// ------------------------------------------------------- contrôle de saisie
// Mêmes règles que backend/modules/reseau/validation.py (le backend revérifie tout).

export type Erreurs = Partial<Record<string, string>>;

const ID_RE = /^[A-Za-z][A-Za-z0-9_]{1,63}$/;
const VILLE_RE = /^[A-Za-zÀ-ÿ' -]{2,60}$/;
const ANNEE_MAX = new Date().getFullYear();

function identite(e: Erreurs, id: string, label: string, edit: boolean, labelsPris: string[]) {
  if (!edit && !ID_RE.test(id)) e['id'] = '2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre';
  const l = label.trim();
  if (l.length < 3) e['label'] = 'Au moins 3 caractères';
  else if (l.length > 120) e['label'] = '120 caractères au maximum';
  else if (labelsPris.includes(l.toLowerCase())) e['label'] = 'Un autre individu de cette classe porte déjà ce libellé';
}

function nombre(e: Erreurs, champ: string, v: number | null, requis: boolean, max: number, unite: string) {
  if (v == null || (v as unknown) === '') { if (requis) e[champ] = 'Champ obligatoire'; return; }
  if (isNaN(v)) e[champ] = 'Doit être un nombre';
  else if (v <= 0) e[champ] = `Doit être supérieur à 0${unite}`;
  else if (v > max) e[champ] = `Ne peut pas dépasser ${max}${unite}`;
}

function annee(e: Erreurs, v: number | null) {
  if (v == null || (v as unknown) === '') return;
  if (!Number.isInteger(v)) e['annee'] = 'Doit être un nombre entier';
  else if (v < 1900 || v > ANNEE_MAX) e['annee'] = `Entre 1900 et ${ANNEE_MAX}`;
}

export function validerLigne(f: LigneForm, edit: boolean, labelsPris: string[] = []): Erreurs {
  const e: Erreurs = {};
  identite(e, f.id, f.label, edit, labelsPris);
  nombre(e, 'tension', f.tension, true, 1000, ' kV');
  nombre(e, 'longueur', f.longueur, false, 2000, ' km');
  annee(e, f.annee);
  if (!f.postes.length) e['postes'] = 'Au moins un poste (relie min 1 PosteElectrique)';
  else if (f.tension != null && f.tension >= 63 && f.postes.length < 2)
    e['postes'] = 'Une ligne haute tension relie au moins 2 postes (LigneHauteTension ⊑ relie min 2)';
  return e;
}

export function validerPoste(f: PosteForm, edit: boolean, labelsPris: string[] = []): Erreurs {
  const e: Erreurs = {};
  identite(e, f.id, f.label, edit, labelsPris);
  if (f.ville.trim() && !VILLE_RE.test(f.ville.trim())) e['ville'] = 'Lettres, espaces, apostrophes et tirets uniquement';
  nombre(e, 'capacite', f.capacite, false, 5000, ' MVA');
  annee(e, f.annee);
  if (f.secours.includes(f.id)) e['secours'] = 'Un poste ne peut pas se secourir lui-même (irréflexive)';
  return e;
}

// ------------------------------------------------------------ NLP → SPARQL

export interface NlpToken { texte: string; lemme: string; pos: string; }
export interface NlpEntite { texte: string; type: string; id: string; label: string; }

export interface NlpReponse {
  analyse: {
    question: string;
    tokens: NlpToken[];
    ner: { texte: string; label: string }[];
    entites: NlpEntite[];
    intention: string;
    cible: string | null;
    categorie: Categorie | null;
    attribut: string | null;
    comparaisons: unknown[];
    relation: string | null;
  };
  interpretation: string | null;
  sparql: string | null;
  colonnes?: string[];
  lignes?: Record<string, string | number | null>[];
  booleen?: boolean;
  erreur?: string;
}
