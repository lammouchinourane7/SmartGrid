import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ModulePlaceholderComponent } from '../../shared/module-placeholder.component';

/**
 * Page du module Bâtiments — Membre 3 · Abir Mosrati.
 * À remplacer par l'interface du module (voir pages/reseau/ pour un exemple complet).
 */
@Component({
  selector: 'app-batiments',
  standalone: true,
  imports: [ModulePlaceholderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-module-placeholder key="batiments" />`,
})
export class BatimentsComponent {}
