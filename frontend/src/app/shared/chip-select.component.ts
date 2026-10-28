import { ChangeDetectionStrategy, Component, input, model } from '@angular/core';

/** Sélection multiple sous forme de puces (pour les ObjectProperties multivaluées). */
@Component({
  selector: 'app-chip-select',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="chips" role="group">
      @for (o of options(); track o.id) {
        <button type="button" class="chip" [class.on]="value().includes(o.id)"
                [attr.aria-pressed]="value().includes(o.id)" (click)="toggle(o.id)">
          {{ o.label }}
        </button>
      } @empty {
        <span class="hint">{{ empty() }}</span>
      }
    </div>`,
  styles: [`
    .chips { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      padding: 5px 11px; border-radius: 999px; cursor: pointer;
      border: 1px solid var(--border); background: var(--bg);
      font-size: 12.5px; font-weight: 500;
      transition: background var(--t), border-color var(--t), color var(--t);
      &:hover { border-color: var(--c, var(--accent)); }
      &.on {
        color: var(--c, var(--accent)); border-color: var(--c, var(--accent));
        background: color-mix(in srgb, var(--c, var(--accent)) 13%, transparent); font-weight: 600;
      }
    }
  `],
})
export class ChipSelectComponent {
  options = input.required<{ id: string; label: string }[]>();
  value = model<string[]>([]);
  empty = input('Aucun élément disponible');

  toggle(id: string) {
    const v = this.value();
    this.value.set(v.includes(id) ? v.filter(x => x !== id) : [...v, id]);
  }
}
