import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ModulePlaceholderComponent } from '../../shared/module-placeholder.component';

/**
 * Page du module Mesure — Membre 5 · Ibtihel Mechergui.
 * À remplacer par l'interface du module (voir pages/reseau/ pour un exemple complet).
 */
@Component({
  selector: 'app-mesure',
  standalone: true,
  imports: [ModulePlaceholderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-module-placeholder key="mesure" />`,
})
export class MesureComponent {}
