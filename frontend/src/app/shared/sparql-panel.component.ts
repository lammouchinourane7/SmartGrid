import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';
import { IconComponent } from './icon.component';

/** Affiche la dernière requête SPARQL exécutée par le backend (utile pendant la démo). */
@Component({
  selector: 'app-sparql-panel',
  standalone: true,
  imports: [IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (query()) {
      <section class="panel card">
        <button class="head" (click)="open.set(!open())" [attr.aria-expanded]="open()">
          <app-icon name="code" [size]="16" />
          <span class="title">{{ title() }}</span>
          <span class="chev" [class.up]="open()">▾</span>
        </button>
        @if (open()) {
          <pre>{{ query() }}</pre>
        }
      </section>
    }`,
  styles: [`
    .panel { overflow: hidden; }
    .head {
      width: 100%; display: flex; align-items: center; gap: 10px;
      padding: 12px 16px; border: 0; background: transparent; cursor: pointer;
      color: var(--accent, var(--text)); font-weight: 600; text-align: left;
    }
    .title { flex: 1; }
    .chev { transition: transform var(--t); color: var(--muted); }
    .chev.up { transform: rotate(180deg); }
    pre {
      margin: 0; padding: 16px 18px; overflow-x: auto;
      background: var(--navy); color: #e8e4dc;
      font-size: 12.5px; line-height: 1.6;
      border-top: 1px solid var(--border);
    }
  `],
})
export class SparqlPanelComponent {
  query = input<string | null>(null);
  title = input('Requête SPARQL exécutée');
  open = signal(false);
}
