import { ChangeDetectionStrategy, Component, OnInit, inject, output, signal } from '@angular/core';
import { ToastService, apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { SparqlPanelComponent } from '../../shared/sparql-panel.component';
import { COULEURS_DPE, DPES, Diagnostic, TYPES, energie, nombre } from './batiments.models';
import { BatimentsService } from './batiments.service';

/** Diagnostic énergétique : intensité (kWh/m²/an), classe DPE recalculée en SPARQL vs déclarée. */
@Component({
  selector: 'app-diagnostic',
  standalone: true,
  imports: [IconComponent, SparqlPanelComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="intro">
      <div>
        <p class="eyebrow">Diagnostic énergétique</p>
        <p class="txt">
          L'intensité <span class="mono">?conso / ?surface</span> et la classe DPE sont <b>calculées en SPARQL</b> (BIND + IF imbriqués)
          puis comparées à <span class="mono">classeEnergetique</span> (énumération <span class="mono">{{ '{' }}"A", …, "G"{{ '}' }}</span>, fonctionnelle).
          « Corriger » réécrit la valeur par un <b>DELETE/INSERT</b>.
        </p>
      </div>
      @if (data(); as d) {
        <div class="resume">
          <span class="pill ok"><b>{{ d.resume.conforme }}</b> conformes</span>
          <span class="pill ko"><b>{{ d.resume.ecart + d.resume.absent }}</b> à corriger</span>
          @if (d.resume.incomplet) { <span class="pill"><b>{{ d.resume.incomplet }}</b> sans surface</span> }
          <button class="btn primary" [disabled]="busy() || !(d.resume.ecart + d.resume.absent)" (click)="appliquer(null)">
            <app-icon name="refresh" [size]="16" /> Tout corriger
          </button>
        </div>
      }
    </div>

    <div class="scale" aria-label="Barème DPE">
      @for (l of dpes; track l; let i = $index) {
        <div class="step" [style.background]="couleurs[l]" [style.width.%]="40 + i * 10">
          <b>{{ l }}</b><span>{{ bareme(i) }}</span>
        </div>
      }
    </div>

    <div class="table-wrap">
      <table class="data">
        <thead>
          <tr><th>Bâtiment</th><th class="num">Consommation</th><th class="num">Surface</th><th>Intensité (kWh/m²·an)</th><th>Déclarée</th><th>Calculée</th><th></th></tr>
        </thead>
        <tbody>
          @if (data(); as d) {
            @for (x of d.items; track x.id) {
              <tr [class.ecart]="x.statut === 'ecart' || x.statut === 'absent'">
                <td>
                  <button class="link" (click)="ouvrir.emit(x.id)">{{ x.label }}</button>
                  <div class="id mono">{{ types[x.classe].court }} · sg:{{ x.id }}</div>
                </td>
                <td class="num mono">{{ kwh(x.consommation) }}</td>
                <td class="num mono">{{ nb(x.surface, ' m²') }}</td>
                <td>
                  @if (x.intensite != null) {
                    <div class="bar"><i [style.width.%]="largeur(x.intensite, d)" [style.background]="x.dpeCalcule ? couleurs[x.dpeCalcule] : 'var(--muted)'"></i></div>
                    <span class="mono">{{ nb(x.intensite) }}</span>
                  } @else { <span class="muted">surface manquante</span> }
                </td>
                <td>@if (x.dpe) { <span class="dpe" [style.background]="couleurs[x.dpe]">{{ x.dpe }}</span> } @else { <span class="muted">—</span> }</td>
                <td>@if (x.dpeCalcule) { <span class="dpe" [style.background]="couleurs[x.dpeCalcule]">{{ x.dpeCalcule }}</span> } @else { <span class="muted">—</span> }</td>
                <td class="actions">
                  @if (x.statut === 'conforme') { <span class="badge" [style.--c]="'var(--success)'"><app-icon name="check" [size]="13" /> conforme</span> }
                  @else if (x.statut === 'incomplet') { <span class="muted">—</span> }
                  @else {
                    <button class="btn small-btn" [disabled]="busy()" (click)="appliquer([x.id])">
                      Corriger → {{ x.dpeCalcule }}
                    </button>
                  }
                </td>
              </tr>
            }
          } @else {
            @for (i of [1, 2, 3, 4]; track i) {
              <tr><td colspan="7"><span class="skeleton" style="width: 100%; height: 18px"></span></td></tr>
            }
          }
        </tbody>
      </table>
    </div>

    <app-sparql-panel [query]="sparql()" [title]="sparqlTitre()" />`,
  styles: [`
    :host { display: grid; gap: 16px; --accent: var(--batiments); }
    .intro { display: flex; gap: 16px; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; }
    .txt { margin: 0; max-width: 72ch; color: var(--muted); font-size: 13px; b { color: var(--text); } .mono { color: var(--batiments); font-size: 12px; } }
    .resume { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .pill {
      padding: 6px 12px; border-radius: 999px; font-size: 12.5px; font-weight: 600; color: var(--muted); background: var(--bg);
      border: 1px solid var(--border);
      b { font-size: 15px; margin-right: 3px; }
      &.ok { color: var(--success); } &.ko { color: var(--production); }
    }
    .scale { display: grid; gap: 3px; max-width: 460px; }
    .step {
      display: flex; justify-content: space-between; align-items: center; gap: 8px;
      padding: 2px 10px; border-radius: 4px 14px 14px 4px; color: #fff; font-size: 11.5px;
      b { font-size: 13px; } span { opacity: .95; white-space: nowrap; }
    }
    .table-wrap { border: 1px solid var(--border); border-radius: var(--radius-sm); }
    table.data td, table.data th { padding: 10px 12px; }
    tr.ecart { background: color-mix(in srgb, var(--production) 6%, transparent); }
    .num { text-align: right; white-space: nowrap; }
    .id { font-size: 11.5px; color: var(--muted); }
    .muted { color: var(--muted); font-size: 12.5px; }
    .link { padding: 0; border: 0; background: none; cursor: pointer; font-weight: 600; text-align: left; &:hover { color: var(--batiments); text-decoration: underline; } }
    .bar { display: inline-block; vertical-align: middle; width: 110px; height: 7px; border-radius: 4px; background: var(--hover); overflow: hidden; margin-right: 8px;
      i { display: block; height: 100%; border-radius: 4px; } }
    .dpe { display: inline-grid; place-items: center; width: 24px; height: 24px; border-radius: 6px; color: #fff; font-weight: 800; font-size: 13px; }
    .actions { text-align: right; white-space: nowrap; }
    .small-btn { height: 30px; font-size: 12.5px; }
  `],
})
export class DiagnosticComponent implements OnInit {
  applied = output<void>();
  ouvrir = output<string>();

  private api = inject(BatimentsService);
  private toast = inject(ToastService);
  types = TYPES;
  dpes = DPES;
  couleurs = COULEURS_DPE;
  kwh = energie; nb = nombre;

  data = signal<Diagnostic | null>(null);
  sparql = signal<string | null>(null);
  sparqlTitre = signal('Requête SPARQL exécutée');
  busy = signal(false);

  ngOnInit() { this.load(); }

  load() {
    this.api.diagnostic().subscribe({
      next: d => { this.data.set(d); this.sparql.set(d.sparql); this.sparqlTitre.set('Requête SPARQL exécutée (SELECT + BIND)'); },
      error: e => this.toast.error(apiError(e)),
    });
  }

  bareme(i: number) {
    const s = this.data()?.seuils;
    if (!s) return '';
    const min = i === 0 ? 0 : s[i - 1].max;
    const max = s[i].max;
    return max == null ? `> ${min}` : `${min === 0 ? '≤' : min + ' –'} ${max}`;
  }

  largeur(x: number, d: Diagnostic) {
    const max = Math.max(...d.items.map(i => i.intensite ?? 0), 1);
    return Math.max(3, (x / max) * 100);
  }

  appliquer(ids: string[] | null) {
    this.busy.set(true);
    this.api.appliquerDiagnostic(ids).subscribe({
      next: r => {
        this.busy.set(false);
        this.toast.success(`${r.changements.length} classe(s) énergétique(s) corrigée(s)`);
        this.load();
        this.sparql.set(r.sparql);
        this.sparqlTitre.set('Requêtes SPARQL UPDATE exécutées');
        this.applied.emit();
      },
      error: e => { this.busy.set(false); this.toast.error(apiError(e)); },
    });
  }
}
