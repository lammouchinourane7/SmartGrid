import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ModulePlaceholderComponent } from '../../shared/module-placeholder.component';

/**
 * Page du module Stockage — Membre 2 · Takoua Naceur.
 * À remplacer par l'interface du module (voir pages/reseau/ pour un exemple complet).
 */
@Component({
  selector: 'app-stockage',
  standalone: true,
  imports: [ModulePlaceholderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-module-placeholder key="stockage" />`,
})
export class StockageComponent {}
