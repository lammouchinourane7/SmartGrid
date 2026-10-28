import { Routes } from '@angular/router';

/** Une route par module : chaque membre travaille dans son dossier pages/<domaine>/. */
export const routes: Routes = [
  { path: '', loadComponent: () => import('./pages/accueil/accueil.component').then(m => m.AccueilComponent), title: 'Smart Grid' },
  { path: 'production', loadComponent: () => import('./pages/production/production.component').then(m => m.ProductionComponent), title: 'Production · Smart Grid' },
  { path: 'stockage', loadComponent: () => import('./pages/stockage/stockage.component').then(m => m.StockageComponent), title: 'Stockage · Smart Grid' },
  { path: 'batiments', loadComponent: () => import('./pages/batiments/batiments.component').then(m => m.BatimentsComponent), title: 'Bâtiments · Smart Grid' },
  { path: 'reseau', loadComponent: () => import('./pages/reseau/reseau.component').then(m => m.ReseauComponent), title: 'Réseau · Smart Grid' },
  { path: 'mesure', loadComponent: () => import('./pages/mesure/mesure.component').then(m => m.MesureComponent), title: 'Mesure · Smart Grid' },
  { path: '**', redirectTo: '' },
];
