export type TypeSource = 'Solaire' | 'Eolien' | 'SourceRenouvelable' | 'SourceNonRenouvelable' | 'SourceEnergie';
export type Famille = 'renouvelable' | 'non_renouvelable' | 'non_classee';
export type Categorie = Famille | 'solaire' | 'eolien';
export type Via = 'produitEnergiePour' | 'estAlimentePar' | 'R1' | 'R7' | 'R6';

export interface Chemin { via: Via; par: string | null; origine: string; }

export interface Source {
  id: string;
  label: string;
  type: TypeSource | null;
  types: string[];
  famille: Famille;
  puissance: number | null;
  date: string | null;
  lignes: string[];
  nbBatiments: number;
  batimentsDirects: string[];
  alimentation?: { batiment: string; chemins: Chemin[] }[];
  liens?: {
    lignes: { id: string; label: string; tension: number | null }[];
    stockages: { id: string; label: string }[];
    mesures: { id: string; label: string; valeurKWh: number | null; debut: string | null; fin: string | null }[];
  };
}

export interface Option { id: string; label: string; classe: string; tension?: number | null; }
export interface Options { lignes: Option[]; batiments: Option[]; sources: Option[]; }

export interface Stats {
  nbSources: number;
  nbRenouvelables: number;
  nbNonRenouvelables: number;
  nbAvecPuissance: number;
  nbSansPuissance: number;
  puissanceTotaleKW: number;
  parType: { type: TypeSource; nb: number; nbAvecPuissance: number; puissanceKW: number }[];
  energieMesuree: {
    nbMesures: number; nbSources: number; totalKWh: number; debut: string | null; fin: string | null;
    chevauchements: { m1: string; m2: string; source: string }[]; regle: string;
  };
  sparql: string;
}

export interface Filtres {
  q?: string;
  categorie?: Categorie | '';
  puissanceMin?: number | null;
  puissanceMax?: number | null;
  sansPuissance?: boolean;
  dateMin?: string;
  dateMax?: string;
}

export interface SourceForm {
  id: string; label: string; type: TypeSource; puissance: number | null; date: string;
  lignes: string[]; batiments: string[];
}

export interface Dependance { id: string; relation: string; sens: 'entrante' | 'sortante'; }
export interface Dependances { bloquantes: Dependance[]; supprimees: Dependance[]; }
export interface ListResponse<T> { items: T[]; sparql: string; }
export interface MutationResponse { id: string; sparql: string; }

/** La hiérarchie de l'ontologie, du plus précis au plus général. */
export const TYPES: Record<TypeSource, { label: string; parent: string; color: string }> = {
  Solaire: { label: 'Solaire', parent: 'SourceRenouvelable', color: 'var(--production)' },
  Eolien: { label: 'Éolien', parent: 'SourceRenouvelable', color: 'var(--reseau)' },
  SourceRenouvelable: { label: 'Renouvelable (autre)', parent: 'SourceEnergie', color: 'var(--stockage)' },
  SourceNonRenouvelable: { label: 'Non renouvelable', parent: 'SourceEnergie', color: 'var(--mesure)' },
  SourceEnergie: { label: 'Non classée', parent: '—', color: 'var(--muted)' },
};
export const TYPE_KEYS = Object.keys(TYPES) as TypeSource[];

export const FAMILLES: Record<Famille, { label: string; color: string }> = {
  renouvelable: { label: 'Renouvelable', color: 'var(--stockage)' },
  non_renouvelable: { label: 'Non renouvelable', color: 'var(--mesure)' },
  non_classee: { label: 'Non classée', color: 'var(--muted)' },
};

export const VIA: Record<Via, { label: string; deduit: boolean }> = {
  produitEnergiePour: { label: 'produitEnergiePour', deduit: false },
  estAlimentePar: { label: 'estAlimentePar (Bâtiments)', deduit: false },
  R1: { label: 'R1 · ligne transporteVers', deduit: true },
  R7: { label: 'R7 · bâtiment raccordé', deduit: true },
  R6: { label: 'R6 · via un stockage', deduit: true },
};

export function slugify(text: string): string {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '').slice(0, 64);
}

/** 470000 → « 470 000 kW » ; null → « non renseignée » (jamais 0). */
export function fmtKW(v: number | null | undefined): string {
  if (v == null) return 'non renseignée';
  return v.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' kW';
}

export function fmtKWh(v: number | null | undefined): string {
  return v == null ? '—' : v.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' kWh';
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [y, m, j] = iso.slice(0, 10).split('-');
  return `${j}/${m}/${y}`;
}

// ------------------------------------------------------- contrôle de saisie
// Mêmes règles que backend/modules/production/validation.py (le backend revérifie tout).

export type Erreurs = Partial<Record<string, string>>;
const ID_RE = /^[A-Za-z][A-Za-z0-9_]{1,63}$/;

export function valider(f: SourceForm, edit: boolean, labelsPris: string[] = []): Erreurs {
  const e: Erreurs = {};
  if (!edit && !ID_RE.test(f.id)) e['id'] = '2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre';
  const l = f.label.trim();
  if (l.length < 3) e['label'] = 'Au moins 3 caractères';
  else if (l.length > 120) e['label'] = '120 caractères au maximum';
  else if (labelsPris.includes(l.toLowerCase())) e['label'] = 'Une autre source porte déjà ce libellé';
  const p = f.puissance as unknown;
  if (p != null && p !== '') {
    const n = Number(p);
    if (!Number.isFinite(n)) e['puissance'] = 'Doit être un nombre fini (kW)';
    else if (n < 0) e['puissance'] = 'La puissance installée ne peut pas être négative';
    else if (n > 10_000_000) e['puissance'] = 'Ne peut pas dépasser 10 000 000 kW';
  }
  if (f.date) {
    const d = new Date(f.date + 'T00:00:00');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(f.date) || isNaN(d.getTime()) || d.getFullYear() < 1900) e['date'] = 'Date invalide';
    else if (f.date > new Date().toISOString().slice(0, 10)) e['date'] = 'Une date de mise en service ne peut pas être dans le futur';
  }
  if (f.type === 'Eolien' && !f.lignes.length)
    e['lignes'] = 'Une source éolienne injecte dans au moins une ligne (Eolien ⊑ injecteDans some LigneElectrique)';
  return e;
}

// ------------------------------------------------------------ NLP → SPARQL

export interface NlpCandidat { id: string; type: string; label: string; }
export interface NlpReponse {
  analyse: {
    question: string;
    tokens: { texte: string; lemme: string; pos: string }[];
    entites: { texte: string; type: string; id: string; label: string }[];
    intention: string;
    cible: string | null;
    categorie: string | null;
    comparaisons: { op: string; valeur?: number; min?: number; max?: number }[];
    periode: { debut: string | null; fin: string | null; sens: string; convention: string | null } | null;
  };
  interpretation: string | null;
  sparql: string | null;
  notes: string[];
  colonnes?: string[];
  lignes?: Record<string, string | number | null>[];
  booleen?: boolean;
  erreur?: string;
  precision?: { message: string; candidats: NlpCandidat[] };
}
