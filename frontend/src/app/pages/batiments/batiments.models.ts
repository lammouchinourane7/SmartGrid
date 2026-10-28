export type TypeBatiment = 'BatimentResidentiel' | 'BatimentIndustriel' | 'BatimentPublic' | 'BatimentCommercial';
export type Definie = 'autonome' | 'vert' | 'gros' | 'intelligent' | 'ht';
export type ClasseDefinie = 'BatimentAutonome' | 'BatimentVert' | 'GrosConsommateur' | 'BatimentIntelligent' | 'BatimentRaccordeHT';
export type Dpe = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G';
export type Via = 'direct' | 'inverse' | 'R1' | 'R2' | 'R3' | 'R6' | 'R7' | 'estRaccordeA' | 'transporteVers' | 'installeDans⁻¹' | 'equipeDe';

export interface Lien { id: string; via: Via; renouvelable?: boolean; }

export interface Batiment {
  id: string;
  label: string;
  classe: TypeBatiment;
  adresse: string | null;
  consommation: number | null;
  surface: number | null;
  occupants: number | null;
  annee: number | null;
  dpe: Dpe | null;
  puissance: number | null;
  intensite: number | null;
  dpeCalcule: Dpe | null;
  consoHoraire: number | null;
  lignes: Lien[];
  sources: Lien[];
  stockages: Lien[];
  postes: Lien[];
  compteurs: Lien[];
  classesDeduites: ClasseDefinie[];
}

export interface Triplet { sens: 'sortant' | 'entrant'; propriete: string; valeur: string; }

export interface Stats {
  nb: number;
  consoTotale: number;
  consoVerte: number;
  partVerte: number;
  intensiteMoyenne: number;
  occupants: number;
  parClasseDefinie: Record<ClasseDefinie, number>;
  parType: Partial<Record<TypeBatiment, { nb: number; consommation: number }>>;
  sparql: string;
}

export interface Option { id: string; label: string; tension?: number | null; renouvelable?: boolean; sources?: string[]; }
export interface Options { lignes: Option[]; sources: Option[]; stockages: Option[]; postes: Option[]; }

export interface Filtres {
  q?: string;
  type?: TypeBatiment | '';
  definie?: Definie | '';
  consoMin?: number | null;
  dpe?: Dpe | '';
  poste?: string;
  source?: string;
}

export interface BatimentForm {
  id: string;
  label: string;
  classe: TypeBatiment | '';
  adresse: string;
  consommation: number | null;
  surface: number | null;
  occupants: number | null;
  annee: number | null;
  dpe: Dpe | '';
  puissance: number | null;
  lignes: string[];
  sources: string[];
  stockages: string[];
}

export interface Inference {
  id: string;
  label: string;
  declare: TypeBatiment;
  classes: { classe: ClasseDefinie; raison: string }[];
  relations: { propriete: string; valeur: string; via: string; explication: string }[];
}

export type StatutDpe = 'conforme' | 'ecart' | 'absent' | 'incomplet';

export interface DiagnosticItem {
  id: string;
  label: string;
  classe: TypeBatiment;
  consommation: number | null;
  surface: number | null;
  intensite: number | null;
  dpe: Dpe | null;
  dpeCalcule: Dpe | null;
  statut: StatutDpe;
}

export interface Diagnostic {
  items: DiagnosticItem[];
  resume: Record<StatutDpe, number>;
  seuils: { classe: Dpe; max: number | null }[];
  sparql: string;
}

export interface DiagnosticApplique { changements: { id: string; avant: Dpe | null; apres: Dpe }[]; sparql: string; }

export interface ListResponse<T> { items: T[]; sparql: string; }
export interface MutationResponse { id: string; sparql: string; }
export interface Dependance { id: string; relation: string; }

// ------------------------------------------------------- vocabulaire OWL

export const TYPES: Record<TypeBatiment, { label: string; court: string; color: string }> = {
  BatimentResidentiel: { label: 'Bâtiment résidentiel', court: 'Résidentiel', color: 'var(--batiments)' },
  BatimentIndustriel: { label: 'Bâtiment industriel', court: 'Industriel', color: 'var(--production)' },
  BatimentPublic: { label: 'Bâtiment public', court: 'Public', color: 'var(--mesure)' },
  BatimentCommercial: { label: 'Bâtiment commercial', court: 'Commercial', color: 'var(--reseau)' },
};

/** Les classes définies (≡), telles que le backend les déduit en SPARQL (et HermiT dans Protégé). */
export const DEFINIES: Record<Definie, { classe: ClasseDefinie; label: string; axiome: string; color: string }> = {
  autonome: {
    classe: 'BatimentAutonome', label: 'Autonome', color: 'var(--stockage)',
    axiome: 'Batiment ⊓ estAlimentePar some SourceRenouvelable ⊓ possedeStockage some SystemeStockage',
  },
  vert: {
    classe: 'BatimentVert', label: 'Vert', color: 'color-mix(in srgb, var(--stockage) 60%, var(--production))',
    axiome: 'Batiment ⊓ estAlimentePar some SourceRenouvelable',
  },
  gros: {
    classe: 'GrosConsommateur', label: 'Gros consommateur', color: 'var(--danger)',
    axiome: 'Batiment ⊓ consommationAnnuelle some float[≥ 1000000]',
  },
  intelligent: {
    classe: 'BatimentIntelligent', label: 'Intelligent', color: 'var(--mesure)',
    axiome: 'Batiment ⊓ equipeDe some CompteurIntelligent',
  },
  ht: {
    classe: 'BatimentRaccordeHT', label: 'Raccordé HT', color: 'var(--reseau)',
    axiome: 'Batiment ⊓ estRaccordeA some LigneHauteTension',
  },
};

export const DEFINIE_PAR_CLASSE = Object.fromEntries(
  Object.entries(DEFINIES).map(([k, v]) => [v.classe, k]),
) as Record<ClasseDefinie, Definie>;

export const VIA: Record<string, string> = {
  direct: 'assertion', inverse: 'inverse', R1: 'R1', R2: 'R2', R3: 'R3', R6: 'R6', R7: 'R7',
  estRaccordeA: 'estRaccordeA', transporteVers: 'transporteVers⁻¹', 'installeDans⁻¹': 'installeDans⁻¹', equipeDe: 'equipeDe',
};

export const DPES: Dpe[] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
export const SEUILS_DPE: [Dpe, number][] = [['A', 70], ['B', 110], ['C', 180], ['D', 250], ['E', 330], ['F', 420]];
export const COULEURS_DPE: Record<Dpe, string> = {
  A: '#2e9e6b', B: '#57b05a', C: '#a5c63b', D: '#e6c229', E: '#e8912d', F: '#e0663a', G: '#d9534f',
};

export const SEUIL_GROS = 1_000_000;
export const SEUIL_HT = 63;

export function dpeCalcule(intensite: number | null | undefined): Dpe | null {
  if (intensite == null || isNaN(intensite)) return null;
  for (const [l, s] of SEUILS_DPE) if (intensite <= s) return l;
  return 'G';
}

/** Sources qui alimenteraient le bâtiment : directes + R7 (lignes) + R6 (stockages). */
export function sourcesDeduites(f: BatimentForm, o: Options, fixes: string[] = []): Set<string> {
  const out = new Set([...f.sources, ...fixes]);   // fixes : liens existants (inverse, R1)
  for (const l of f.lignes) for (const s of o.lignes.find(x => x.id === l)?.sources ?? []) out.add(s);
  for (const x of f.stockages) for (const s of o.stockages.find(y => y.id === x)?.sources ?? []) out.add(s);
  return out;
}

/** Classes définies qu'un formulaire en cours de saisie ferait déduire. */
export function deduire(f: BatimentForm, o: Options, compteurs: number, fixes: string[] = []): Definie[] {
  const out: Definie[] = [];
  const renouv = [...sourcesDeduites(f, o, fixes)].some(s => o.sources.find(x => x.id === s)?.renouvelable);
  if (renouv && f.stockages.length) out.push('autonome');
  if (renouv) out.push('vert');
  if (!vide(f.consommation) && f.consommation! >= SEUIL_GROS) out.push('gros');
  if (compteurs > 0) out.push('intelligent');
  if (f.lignes.some(l => (o.lignes.find(x => x.id === l)?.tension ?? 0) >= SEUIL_HT)) out.push('ht');
  return out;
}

/** Formatage français : 45 000 000 kWh → « 45 GWh ». */
export function energie(kwh: number | null | undefined): string {
  if (kwh == null) return '—';
  if (kwh >= 1_000_000) return `${(kwh / 1_000_000).toLocaleString('fr-FR', { maximumFractionDigits: 2 })} GWh`;
  if (kwh >= 1000) return `${(kwh / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} MWh`;
  return `${kwh.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kWh`;
}

export function nombre(x: number | null | undefined, unite = ''): string {
  if (x == null) return '—';
  return `${x.toLocaleString('fr-FR', { maximumFractionDigits: 1 })}${unite}`;
}

export function puissance(kw: number | null | undefined): string {
  if (kw == null) return '—';
  if (kw >= 1000) return `${(kw / 1000).toLocaleString('fr-FR', { maximumFractionDigits: 1 })} MW`;
  return `${kw.toLocaleString('fr-FR', { maximumFractionDigits: 1 })} kW`;
}

/** "Lycée de Sousse" → "Lycee_de_Sousse" (identifiant d'individu OWL). */
export function slugify(text: string): string {
  return text
    .normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/[^A-Za-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 64);
}

// ------------------------------------------------------- contrôle de saisie
// Mêmes règles que backend/modules/batiments/validation.py (le backend revérifie tout).

export type Erreurs = Partial<Record<string, string>>;

const ID_RE = /^[A-Za-z][A-Za-z0-9_]{1,63}$/;
const ANNEE_MAX = new Date().getFullYear();

function vide(v: unknown) { return v == null || v === ''; }

export function valider(f: BatimentForm, edit: boolean, o: Options, fixes: string[] = []): Erreurs {
  const e: Erreurs = {};
  if (!edit && !ID_RE.test(f.id)) e['id'] = '2 à 64 caractères : lettres, chiffres et _, en commençant par une lettre';
  const l = f.label.trim();
  if (l.length < 3) e['label'] = 'Au moins 3 caractères';
  else if (l.length > 120) e['label'] = '120 caractères au maximum';
  if (!f.classe) e['classe'] = 'Choisissez un type de bâtiment';
  if (f.adresse.length > 160) e['adresse'] = '160 caractères au maximum';

  if (vide(f.consommation)) e['consommation'] = 'Champ obligatoire';
  else if (isNaN(f.consommation!) || f.consommation! < 0) e['consommation'] = 'Doit être au moins 0 kWh (consommationAnnuelle only float[≥ 0])';
  else if (f.consommation! > 1_000_000_000) e['consommation'] = 'Ne peut pas dépasser 1 000 000 000 kWh';

  if (!vide(f.surface) && (isNaN(f.surface!) || f.surface! <= 0)) e['surface'] = 'Doit être supérieur à 0 m² (surface only float[> 0])';
  if (!vide(f.occupants) && (!Number.isInteger(f.occupants) || f.occupants! < 0)) e['occupants'] = 'Entier positif ou nul';
  if (!vide(f.puissance) && (isNaN(f.puissance!) || f.puissance! <= 0)) e['puissance'] = 'Doit être supérieur à 0 kW';
  if (!vide(f.annee) && (!Number.isInteger(f.annee) || f.annee! < 1800 || f.annee! > ANNEE_MAX))
    e['annee'] = `Entre 1800 et ${ANNEE_MAX}`;

  if (!f.lignes.length) e['lignes'] = 'Au moins une ligne (Batiment ⊑ estRaccordeA some LigneElectrique)';
  else if (f.classe === 'BatimentIndustriel'
    && !f.lignes.some(id => (o.lignes.find(x => x.id === id)?.tension ?? 0) > 1))
    e['lignes'] = 'Un site industriel est raccordé en MT ou HT (BatimentIndustriel ⊑ estRaccordeA some (LigneMoyenneTension ⊔ LigneHauteTension))';

  if (f.classe === 'BatimentPublic' && !e['lignes']) {
    const n = sourcesDeduites(f, o, fixes).size;
    if (n < 2) e['sources'] = `Un bâtiment public est alimenté par au moins 2 sources (BatimentPublic ⊑ estAlimentePar min 2 SourceEnergie) : ${n} trouvée(s), directes ou déduites (R7, R6)`;
  }
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
    definies: Partial<Record<Definie | 'stockage', boolean>>;
    dpe: { lettre: Dpe; op: string } | null;
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
