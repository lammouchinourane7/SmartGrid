import { IconName } from '../shared/icon.component';

/** Les 5 domaines de l'ontologie, un par membre de l'équipe. */
export interface Domain {
  key: 'production' | 'stockage' | 'batiments' | 'reseau' | 'mesure';
  label: string;
  title: string;
  membre: string;
  numero: number;
  icon: IconName;
  classes: string[];
  description: string;
}

export const DOMAINS: Domain[] = [
  {
    key: 'production', label: 'Production', title: "Production d'énergie",
    membre: 'Wala Rezgui', numero: 1, icon: 'sun',
    classes: ['SourceEnergie', 'SourceRenouvelable', 'Solaire', 'Eolien', 'SourceNonRenouvelable'],
    description: 'Sources solaires, éoliennes et non renouvelables qui injectent dans le réseau.',
  },
  {
    key: 'stockage', label: 'Stockage', title: "Stockage d'énergie",
    membre: 'Takoua Naceur', numero: 2, icon: 'battery',
    classes: ['SystemeStockage', 'Batterie', 'BatterieLithiumIon', 'StockageHydrogene', 'STEP'],
    description: "Batteries, hydrogène et STEP qui gardent l'énergie pour plus tard.",
  },
  {
    key: 'batiments', label: 'Bâtiments', title: 'Bâtiments consommateurs',
    membre: 'Abir Mosrati', numero: 3, icon: 'building',
    classes: ['Batiment', 'BatimentResidentiel', 'BatimentIndustriel', 'BatimentPublic', 'BatimentAutonome'],
    description: 'Résidentiel, industriel et public, au centre du réseau.',
  },
  {
    key: 'reseau', label: 'Réseau', title: 'Réseau de transport',
    membre: 'Nourane Lammouchi', numero: 4, icon: 'pylon',
    classes: ['InfrastructureReseau', 'LigneElectrique', 'LigneHauteTension', 'LigneBasseTension', 'PosteElectrique'],
    description: "Lignes électriques et postes qui transportent l'énergie vers les bâtiments.",
  },
  {
    key: 'mesure', label: 'Mesure', title: 'Gestion et mesure',
    membre: 'Ibtihel Mechergui', numero: 5, icon: 'gauge',
    classes: ['CompteurIntelligent', 'Mesure', 'MesureConsommation', 'MesureProduction', 'OperateurReseau'],
    description: "Compteurs intelligents, mesures et opérateur qui pilote le réseau.",
  },
];

export const domain = (key: Domain['key']) => DOMAINS.find(d => d.key === key)!;
