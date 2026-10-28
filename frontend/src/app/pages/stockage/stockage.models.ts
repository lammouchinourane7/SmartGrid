export type Famille = 'Batterie' | 'StockageHydrogene' | 'STEP' | 'VolantInertie';
export type Classe = 'Batterie' | 'BatterieLithiumIon' | 'BatteriePlomb' | 'StockageHydrogene' | 'STEP' | 'VolantInertie';
export type Definie = 'vert' | 'critique' | 'grande' | 'secours';
export type ClasseDefinie = 'StockageVert' | 'StockageCritique' | 'StockageGrandeCapacite' | 'StockageSecours';

export interface Systeme {
  id: string;
  label: string;
  classe: Classe;
  famille: Famille;
  capacite: number | null;
  niveau: number | null;
  rendement: number | null;
  puissance: number | null;
  technologie: string | null;
  annee: number | null;
  poste: string | null;
  sources: string[];
  batiments: string[];
  energie: number | null;
  autonomie: number | null;
  classesDeduites: ClasseDefinie[];
}

export interface Triplet { sens: 'sortant' | 'entrant'; propriete: string; valeur: string; }

export interface Stats {
  nb: number;
  capaciteTotale: number;
  energieDisponible: number;
  chargeMoyenne: number;
  parClasseDefinie: Record<ClasseDefinie, number>;
  parFamille: Partial<Record<Famille, { nb: number; capacite: number }>>;
  sparql: string;
}

export interface Option { id: string; label: string; renouvelable?: boolean; }
export interface Options { sources: Option[]; batiments: Option[]; postes: Option[]; }

export interface Filtres {
  q?: string;
  famille?: Famille | '';
  definie?: Definie | '';
  niveauMin?: number | null;
  niveauMax?: number | null;
  source?: string;
  batiment?: string;
  poste?: string;
}

export interface SystemeForm {
  id: string;
  label: string;
  classe: Classe | '';
  capacite: number | null;
  niveau: number | null;
  rendement: number | null;
  puissance: number | null;
  technologie: string;
  annee: number | null;
  poste: string;
  sources: string[];
  batiments: string[];
}

export interface BatimentStockage {
  id: string;
  label: string;
  classe: string;
  consommation: number | null;
  stockages: string[];
  energie: number | null;
  sourcesRenouvelables: { id: string; via: 'direct' | 'inverse' | 'R1' | 'R6' }[];
  autonome: boolean;
}

export type Statut = 'tient' | 'partiel' | 'coupe';

export interface ScenarioBatiment {
  id: string;
  label: string;
  stockages: string[];
  consoHoraire: number;
  energie: number;
  puissance: number | null;
  couverture: number;
  autonomie: number;
  energieFournie: number;
  statut: Statut;
}

export interface Scenario {
  poste: string | null;
  heures: number;
  batiments: ScenarioBatiment[];
  resume: Record<Statut, number>;
  stockagesReseau: { id: string; label: string; capacite: number; niveau: number; puissance: number; energie: number }[];
  sparql: string;
}

export interface ScenarioApplique {
  changements: { id: string; avant: number; apres: number; critique: boolean }[];
  sparql: string;
}

export interface ListResponse<T> { items: T[]; sparql: string; }
export interface MutationResponse { id: string; sparql: string; }
export interface Dependance { id: string; relation: string; }

// ------------------------------------------------------- vocabulaire OWL

export const FAMILLES: Record<Famille, { label: string; color: string }> = {
  Batterie: { label: 'Batteries', color: 'var(--stockage)' },
  StockageHydrogene: { label: 'Hydrogène', color: 'var(--batiments)' },
  STEP: { label: 'STEP', color: 'color-mix(in srgb, var(--batiments) 55%, var(--stockage))' },
  VolantInertie: { label: 'Volants', color: 'var(--reseau)' },
};

export const CLASSES: Record<Classe, { label: string; famille: Famille }> = {
  Batterie: { label: 'Batterie (générique)', famille: 'Batterie' },
  BatterieLithiumIon: { label: 'Batterie lithium-ion', famille: 'Batterie' },
  BatteriePlomb: { label: 'Batterie plomb-acide', famille: 'Batterie' },
  StockageHydrogene: { label: 'Stockage hydrogène', famille: 'StockageHydrogene' },
  STEP: { label: 'STEP (pompage-turbinage)', famille: 'STEP' },
  VolantInertie: { label: "Volant d'inertie", famille: 'VolantInertie' },
};

/** Les classes définies (≡), telles que le backend les déduit en SPARQL. */
export const DEFINIES: Record<Definie, { classe: ClasseDefinie; label: string; axiome: string; color: string }> = {
  vert: {
    classe: 'StockageVert', label: 'Vert', color: 'var(--stockage)',
    axiome: 'SystemeStockage ⊓ stockeEnergieDe some SourceRenouvelable',
  },
  critique: {
    classe: 'StockageCritique', label: 'Critique', color: 'var(--danger)',
    axiome: 'SystemeStockage ⊓ niveauCharge some float[< 20]',
  },
  grande: {
    classe: 'StockageGrandeCapacite', label: 'Grande capacité', color: 'var(--batiments)',
    axiome: 'SystemeStockage ⊓ capaciteStockage some float[≥ 10000]',
  },
  secours: {
    classe: 'StockageSecours', label: 'Secours', color: 'var(--mesure)',
    axiome: 'SystemeStockage ⊓ alimente some BatimentPublic',
  },
};

export const DEFINIE_PAR_CLASSE = Object.fromEntries(
  Object.entries(DEFINIES).map(([k, v]) => [v.classe, k]),
) as Record<ClasseDefinie, Definie>;

export const SEUIL_CRITIQUE = 20;

/** Classes définies qu'un formulaire en cours de saisie ferait déduire. */
export function deduire(f: SystemeForm, sources: Option[], batimentsPublics: Set<string>): Definie[] {
  const out: Definie[] = [];
  if (f.sources.some(s => sources.find(o => o.id === s)?.renouvelable)) out.push('vert');
  if (f.niveau != null && (f.niveau as unknown) !== '' && f.niveau < SEUIL_CRITIQUE) out.push('critique');
  if (f.capacite != null && f.capacite >= 10000) out.push('grande');
  if (f.batiments.some(b => batimentsPublics.has(b))) out.push('secours');
  return out;
}

/** Formatage français des grands nombres : 400000 kWh → « 400 MWh ». */
export function energie(kwh: number | null | undefined): string {
  if (kwh == null) return '—';
  if (kwh >= 1_000_000) return `${(kwh / 1_000_000).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} GWh`;
  if (kwh >= 1000) return `${(kwh / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} MWh`;
  return `${kwh.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kWh`;
}

export function puissance(kw: number | null | undefined): string {
  if (kw == null) return '—';
  if (kw >= 1000) return `${(kw / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} MW`;
  return `${kw.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kW`;
}

export function duree(h: number | null | undefined): string {
  if (h == null) return '—';
  if (h < 1) return `${Math.round(h * 60)} min`;
  const hh = Math.floor(h), mm = Math.round((h - hh) * 60);
  return mm ? `${hh} h ${String(mm).padStart(2, '0')}` : `${hh} h`;
}

/** "Batterie de l'école" → "Batterie_de_l_ecole" (identifiant d'individu OWL). */
export function slugify(text: string): string {
  return text
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
}

// ------------------------------------------------------- contrôle de saisie
// Mêmes règles que backend/modules/stockage/validation.py (le backend revérifie tout).

export type Erreurs = Partial<Record<string, string>>;

const ID_RE = /^[A-Za-z][A-Za-z0-9_]{1,63}$/;
const ANNEE_MAX = new Date().getFullYear();

function vide(v: unknown) { return v == null || v === ''; }

export function valider(f: SystemeForm, edit: boolean, sources: Option[]): Erreurs {
  const e: Erreurs = {};
  if (!edit && !ID_RE.test(f.id)) e['id'] = '2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre';
  const l = f.label.trim();
  if (l.length < 3) e['label'] = 'Au moins 3 caractères';
  else if (l.length > 120) e['label'] = '120 caractères au maximum';
  if (!f.classe) e['classe'] = 'Choisissez un type de stockage';

  if (vide(f.capacite)) e['capacite'] = 'Champ obligatoire';
  else if (isNaN(f.capacite!) || f.capacite! <= 0) e['capacite'] = 'Doit être supérieur à 0 kWh';
  else if (f.capacite! > 10_000_000) e['capacite'] = 'Ne peut pas dépasser 10 000 000 kWh';

  if (!vide(f.niveau) && (isNaN(f.niveau!) || f.niveau! < 0 || f.niveau! > 100))
    e['niveau'] = 'Entre 0 et 100 % (niveauCharge only float[≥ 0, ≤ 100])';
  if (!vide(f.rendement) && (isNaN(f.rendement!) || f.rendement! <= 0 || f.rendement! > 100))
    e['rendement'] = 'Entre 0 (exclu) et 100 %';
  if (!vide(f.puissance) && (isNaN(f.puissance!) || f.puissance! <= 0)) e['puissance'] = 'Doit être supérieur à 0 kW';
  if (!vide(f.annee) && (!Number.isInteger(f.annee) || f.annee! < 1900 || f.annee! > ANNEE_MAX))
    e['annee'] = `Entre 1900 et ${ANNEE_MAX}`;
  if (f.technologie.length > 80) e['technologie'] = '80 caractères au maximum';

  if (f.classe === 'VolantInertie' && !f.poste)
    e['poste'] = "Un volant d'inertie est raccordé à exactement 1 poste (exactly 1)";

  const renouv = (id: string) => !!sources.find(s => s.id === id)?.renouvelable;
  if (!f.sources.length) e['sources'] = 'Au moins une source (SystemeStockage ⊑ stockeEnergieDe some SourceEnergie)';
  else if (f.classe === 'STEP' && !f.sources.every(renouv))
    e['sources'] = 'Une STEP ne stocke que du renouvelable (STEP ⊑ stockeEnergieDe only SourceRenouvelable)';
  else if (f.classe === 'StockageHydrogene' && !f.sources.some(renouv))
    e['sources'] = "L'hydrogène vert exige une source renouvelable (StockageHydrogene ⊑ stockeEnergieDe some SourceRenouvelable)";
  return e;
}

// ------------------------------------------------------------ NLP → SPARQL

export interface NlpReponse {
  analyse: {
    question: string;
    tokens: { texte: string; lemme: string; pos: string }[];
    ner: { texte: string; label: string }[];
    entites: { texte: string; type: string; id: string; label: string }[];
    classes: string[];
    definies: Partial<Record<Definie, boolean>>;
    lieux: { texte: string; source: string; postes: string[] }[];
    intention: string;
    cible: string;
    attribut: string | null;
    comparaisons: unknown[];
  };
  interpretation: string;
  sparql: string;
  colonnes?: string[];
  lignes?: Record<string, string | number | boolean | null>[];
  booleen?: boolean;
}
