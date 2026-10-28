import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { Domain, domain } from '../core/domains';
import { IconComponent } from './icon.component';

/** Page provisoire d'un module pas encore implémenté. */
@Component({
  selector: 'app-module-placeholder',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="page" [style.--accent]="'var(--' + d().key + ')'">
      <header class="head">
        <div>
          <p class="eyebrow">Membre {{ d().numero }} · {{ d().membre }}</p>
          <h1 class="page-title">{{ d().title }}</h1>
          <p class="page-sub">{{ d().description }}</p>
        </div>
        <span class="tile"><app-icon [name]="d().icon" [size]="34" [stroke]="1.6" /></span>
      </header>

      <section class="card empty">
        <app-icon name="lock" [size]="22" />
        <h2>Module à implémenter</h2>
        <p>
          Cette page appartient à <strong>{{ d().membre }}</strong>.
          Remplacer le composant <code>pages/{{ d().key }}/{{ d().key }}.component.ts</code>
          et compléter le blueprint <code>backend/modules/{{ d().key }}/</code>.
        </p>
        <div class="classes">
          @for (c of d().classes; track c) { <span class="badge" [style.--c]="'var(--' + d().key + ')'">{{ c }}</span> }
        </div>
      </section>
    </div>`,
  styles: [`
    .page { display: grid; gap: 24px; }
    .head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; }
    .tile {
      width: 72px; height: 72px; border-radius: 18px; display: grid; place-items: center;
      color: var(--accent); background: color-mix(in srgb, var(--accent) 14%, transparent);
    }
    .empty {
      padding: 40px 24px; text-align: center; display: grid; justify-items: center; gap: 8px;
      border-style: dashed; color: var(--muted);
      h2 { margin: 6px 0 0; color: var(--text); font-size: 18px; }
      p { margin: 0; max-width: 60ch; }
      code { font-size: 12.5px; color: var(--accent); }
    }
    .classes { display: flex; flex-wrap: wrap; justify-content: center; gap: 6px; margin-top: 10px; }
    @media (max-width: 600px) { .tile { display: none; } }
  `],
})
export class ModulePlaceholderComponent {
  key = input.required<Domain['key']>();
  d = computed(() => domain(this.key()));
}
