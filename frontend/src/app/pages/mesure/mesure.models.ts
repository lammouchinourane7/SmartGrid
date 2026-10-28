export type TypeMesure = 'consommation' | 'production';
export type Politique = 'reaffecter' | 'conserver';

export interface Compteur {
  id: string;
  label: string;
  identifiant: string | null;
  batiments: string[];
  nbBatiments: number;
  mesures: string[];
  nbMesures: number;
  detailMesures?: Mesure[];
}

export interface Cible { id: string; via: 'assertion' | 'R5'; }

export interface Mesure {
  id: string;
  label: string;
  type: TypeMesure | 'indeterminee';
  valeur: number | null;
  debut: string | null;
  fin: string | null;
  compteurs: string[];
  cibles: Cible[];
  historique?: string[];
}

export interface Operateur {
  id: string;
  label: string;
  gere: string[];
  lignesR4: string[];
}

export interface Option { id: string; label: string; classe: string; }

export interface Options {
  batiments: Option[];
  sources: Option[];
  infrastructures: Option[];
  compteurs: Option[];
  operateurs: Option[];
}

export interface Stats { compteurs: number; consommations: number; productions: number; operateurs: number; sparql: string; }

export interface Bilan {
  debut: string | null;
  fin: string | null;
  regle: string;
  totaux: Record<TypeMesure, { nombre: number; totalKWh: number }>;
  parCible: { type: TypeMesure; cible: string; via: string; nombre: number; totalKWh: number }[];
  exclues: { id: string; type: TypeMesure; debut: string; fin: string }[];
  chevauchements: { m1: string; m2: string; cible: string }[];
  sparql: string;
}

export interface Anomalie { id: string; probleme: string; detail: string; }

export interface MesureFiltres {
  q?: string;
  type?: TypeMesure | '';
  compteur?: string;
  cible?: string;
  valeurMin?: number | null;
  valeurMax?: number | null;
  debut?: string;
  fin?: string;
  mode?: 'chevauchement' | 'inclusion';
}

export interface CompteurForm { id: string; label: string; identifiant: string; batiment: string; }

export interface MesureForm {
  id: string; label: string; type: TypeMesure; valeur: number | null;
  debut: string; fin: string; compteur: string; cible: string;
  confirmerReaffectation?: boolean;
}

export interface OperateurForm { id: string; label: string; gere: string[]; }

export interface Dependance { id: string; relation: string; }

export interface ApercuMesure { mesure: string; retires: string[]; ajoutes: string[]; resultat: string; }

export interface Impact {
  anciens: string[];
  nouveau: string;
  mesures: { id: string; label: string; concerneAssertee: string[] }[];
  /** Triplets exacts retirés / ajoutés pour chaque politique, calculés par le backend. */
  apercu: Record<Politique, ApercuMesure[]>;
}

export interface ListResponse<T> { items: T[]; sparql: string; }
export interface MutationResponse { id: string; sparql: string; }

export const TYPES: Record<TypeMesure, { label: string; classe: string; axiome: string; color: string }> = {
  consommation: {
    label: 'Consommation', classe: 'MesureConsommation',
    axiome: 'concerne only Batiment ⊓ concerne max 1 Batiment', color: 'var(--batiments)',
  },
  production: {
    label: 'Production', classe: 'MesureProduction',
    axiome: 'concerne only SourceEnergie', color: 'var(--production)',
  },
};

/** "Compteur école Ariana" → "Compteur_ecole_Ariana" (identifiant d'individu OWL). */
export function slugify(text: string): string {
  return text
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
}

/** '2025-01-31T23:59:59' → '31/01/2025' (une heure n'est affichée que si elle n'est pas 00:00 / 23:59:59). */
export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return '—';
  const [d, t] = iso.split('T');
  const [y, m, j] = d.split('-');
  const heure = t && t !== '00:00:00' && t !== '23:59:59' ? ' ' + t.slice(0, 5) : '';
  return `${j}/${m}/${y}${heure}`;
}

export function fmtKWh(v: number | null | undefined): string {
  if (v == null) return '—';
  return v.toLocaleString('fr-FR', { maximumFractionDigits: 2 }) + ' kWh';
}

// ------------------------------------------------------- contrôle de saisie
// Mêmes règles que backend/modules/mesure/validation.py (le backend revérifie tout).

export type Erreurs = Partial<Record<string, string>>;

const ID_RE = /^[A-Za-z][A-Za-z0-9_]{1,63}$/;
const IDENTIFIANT_RE = /^[A-Za-z0-9][A-Za-z0-9_-]{1,39}$/;
const DATE_RE = /^(20\d\d|2100)-\d{2}-\d{2}$/;

function identite(e: Erreurs, id: string, label: string, edit: boolean, labelsPris: string[]) {
  if (!edit && !ID_RE.test(id)) e['id'] = '2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre';
  const l = label.trim();
  if (l.length < 3) e['label'] = 'Au moins 3 caractères';
  else if (l.length > 120) e['label'] = '120 caractères au maximum';
  else if (labelsPris.includes(l.toLowerCase())) e['label'] = 'Un autre individu de cette classe porte déjà ce libellé';
}

export function validerCompteur(f: CompteurForm, edit: boolean, labelsPris: string[] = []): Erreurs {
  const e: Erreurs = {};
  identite(e, f.id, f.label, edit, labelsPris);
  if (!f.identifiant.trim()) e['identifiant'] = 'Champ obligatoire';
  else if (!IDENTIFIANT_RE.test(f.identifiant.trim())) e['identifiant'] = '2 à 40 caractères : lettres, chiffres, - et _';
  if (!f.batiment) e['batiment'] = 'Bâtiment obligatoire (installeDans exactly 1 Batiment)';
  return e;
}

function dateValide(v: string) {
  return DATE_RE.test(v) && !isNaN(new Date(v + 'T00:00:00').getTime())
    && new Date(v + 'T00:00:00').toISOString().startsWith(v);
}

export function validerMesure(f: MesureForm, edit: boolean, labelsPris: string[] = [], batimentCompteur?: string | null): Erreurs {
  const e: Erreurs = {};
  identite(e, f.id, f.label, edit, labelsPris);
  const v = f.valeur as unknown;
  if (v == null || v === '') e['valeur'] = 'Champ obligatoire (valeurKWh)';
  else if (isNaN(Number(v))) e['valeur'] = 'Doit être un nombre';
  else if (Number(v) < 0) e['valeur'] = 'Doit être un nombre positif ou nul';
  if (!f.debut) e['debut'] = 'Champ obligatoire';
  else if (!dateValide(f.debut)) e['debut'] = 'Date invalide (années 2000–2100)';
  if (!f.fin) e['fin'] = 'Champ obligatoire';
  else if (!dateValide(f.fin)) e['fin'] = 'Date invalide (années 2000–2100)';
  else if (!e['debut'] && f.fin < f.debut) e['fin'] = 'La date de fin doit être postérieure à la date de début';
  if (f.type === 'production' && !f.cible) e['cible'] = "Source d'énergie obligatoire (concerne only SourceEnergie)";
  if (f.type === 'consommation') {
    if (!f.compteur && !f.cible) e['cible'] = 'Bâtiment obligatoire sans compteur';
    if (f.compteur && batimentCompteur && f.cible && f.cible !== batimentCompteur)
      e['cible'] = `Le compteur est installé dans ${batimentCompteur} : R5 en déduirait un second bâtiment (max 1 Batiment)`;
  }
  return e;
}

export function validerOperateur(f: OperateurForm, edit: boolean, labelsPris: string[] = []): Erreurs {
  const e: Erreurs = {};
  identite(e, f.id, f.label, edit, labelsPris);
  return e;
}

// ------------------------------------------------------------ NLP → SPARQL

export interface NlpToken { texte: string; lemme: string; pos: string; }
export interface NlpCandidat { id: string; type: string; label: string; }
export interface NlpEntite { texte: string; type: string; id: string; label: string; }

export interface NlpReponse {
  analyse: {
    question: string;
    tokens: NlpToken[];
    ner: { texte: string; label: string }[];
    entites: NlpEntite[];
    intention: string;
    cible: string | null;
    typeMesure: TypeMesure | null;
    typeInfrastructure: string | null;
    comparaisons: { op: string; valeur?: number; min?: number; max?: number }[];
    periode: { debut: string | null; fin: string | null; convention: string | null } | null;
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
