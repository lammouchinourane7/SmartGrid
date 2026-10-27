import { ChangeDetectionStrategy, Component } from '@angular/core';
import { ModulePlaceholderComponent } from '../../shared/module-placeholder.component';

/**
 * Page du module Production — Membre 1 · Wala Rezgui.
 * À remplacer par l'interface du module (voir pages/reseau/ pour un exemple complet).
 */
@Component({
  selector: 'app-production',
  standalone: true,
  imports: [ModulePlaceholderComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `<app-module-placeholder key="production" />`,
})
export class ProductionComponent {}
