import { ChangeDetectionStrategy, Component, OnInit, inject, input, output, signal } from '@angular/core';
import { ToastService, apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { SparqlPanelComponent } from '../../shared/sparql-panel.component';
import { Option, Scenario, ScenarioApplique, Statut, duree, energie, puissance } from './stockage.models';
import { StockageService } from './stockage.service';

/**
 * Scénario « coupure de poste » : quels bâtiments tiennent grâce à leur stockage ?
 * R3 donne les bâtiments desservis par le poste, R2 les stockages qu'ils possèdent ;
 * « Appliquer » décharge réellement les stockages (SPARQL DELETE/INSERT sur niveauCharge).
 */
@Component({
  selector: 'app-stockage-scenario',
  standalone: true,
  imports: [IconComponent, SparqlPanelComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="controls">
      <label class="field">
        <span>Poste en panne</span>
        <select class="input" [value]="poste()" (change)="poste.set($any($event.target).value); charger()">
          <option value="" [selected]="!poste()">Coupure générale (tous les bâtiments)</option>
          @for (p of postes(); track p.id) { <option [value]="p.id" [selected]="p.id === poste()">{{ p.label }}</option> }
        </select>
      </label>
      <label class="field duree">
        <span>Durée de la coupure : <strong>{{ heures() }} h</strong></span>
        <input type="range" min="1" max="24" step="1" [value]="heures()"
               (input)="heures.set(+$any($event.target).value)" (change)="charger()" aria-label="Durée en heures">
      </label>
      <button class="btn primary" [disabled]="!s() || busy() || !aDecharger()" (click)="appliquer()"
              title="Décharge les stockages dans l'ontologie (SPARQL UPDATE)">
        <app-icon name="battery" [size]="16" /> {{ busy() ? 'Application…' : 'Appliquer la coupure' }}
      </button>
    </div>

    @if (s(); as s) {
      <div class="resume">
        <div class="r tient"><strong>{{ s.resume.tient }}</strong><span>tiennent {{ s.heures }} h</span></div>
        <div class="r partiel"><strong>{{ s.resume.partiel }}</strong><span>tiennent en partie</span></div>
        <div class="r coupe"><strong>{{ s.resume.coupe }}</strong><span>sans stockage</span></div>
      </div>

      <div class="table-wrap">
        <table class="data">
          <thead>
            <tr>
              <th>Bâtiment <small>R3</small></th><th>Stockage <small>R2</small></th>
              <th class="num">Appel moyen</th><th class="num">Énergie dispo.</th>
              <th>Autonomie sur {{ s.heures }} h</th><th>Statut</th>
            </tr>
          </thead>
          <tbody>
            @for (b of s.batiments; track b.id) {
              <tr>
                <td><div class="name">{{ b.label }}</div><div class="id mono">sg:{{ b.id }}</div></td>
                <td>
                  @for (x of b.stockages; track x) { <span class="badge" [style.--c]="'var(--stockage)'">{{ label(x) }}</span> }
                  @empty { <span class="muted">—</span> }
                </td>
                <td class="num mono">{{ kw(b.consoHoraire) }}</td>
                <td class="num mono">{{ kwh(b.energie) }}</td>
                <td>
                  <div class="bar" [attr.aria-label]="'Autonomie ' + h(b.autonomie)">
                    <i [style.width.%]="pct(b.autonomie, s.heures)" [class]="b.statut"></i>
                  </div>
                  <span class="mono small">
                    {{ b.stockages.length ? h(b.autonomie) : '0 min' }}
                    @if (b.stockages.length && b.couverture < 100) { · couvre {{ b.couverture }} % de l'appel }
                  </span>
                </td>
                <td><span class="badge" [style.--c]="statuts[b.statut].color">{{ statuts[b.statut].label }}</span></td>
              </tr>
            } @empty {
              <tr><td colspan="6" class="empty">Aucun bâtiment desservi par ce poste.</td></tr>
            }
          </tbody>
        </table>
      </div>

      @if (s.stockagesReseau.length) {
        <p class="note">
          <app-icon name="pylon" [size]="16" />
          Stockage réseau raccordé à ce poste (non dédié à un bâtiment) :
          @for (x of s.stockagesReseau; track x.id) {
            <strong>{{ x.label }}</strong> — {{ kwh(x.energie) }} à {{ kw(x.puissance) }}{{ $last ? '' : ', ' }}
          }
        </p>
      }

      @if (dernier(); as d) {
        <div class="applique card">
          <p class="eyebrow">Coupure appliquée dans l'ontologie</p>
          <ul>
            @for (c of d.changements; track c.id) {
              <li>
                <span>{{ label(c.id) }}</span>
                <span class="mono">{{ c.avant }} % → <b [class.crit]="c.critique">{{ c.apres }} %</b></span>
                @if (c.critique) { <span class="badge" [style.--c]="'var(--danger)'">devient StockageCritique</span> }
              </li>
            }
          </ul>
        </div>
        <app-sparql-panel [query]="d.sparql" title="Requêtes SPARQL UPDATE exécutées" />
      }
      <app-sparql-panel [query]="s.sparql" title="Requête SPARQL du scénario (R3 + R2)" />
    } @else {
      <span class="skeleton" style="width: 100%; height: 260px"></span>
    }`,
  styles: [`
    :host { display: grid; gap: 16px; }
    .controls { display: flex; flex-wrap: wrap; gap: 16px; align-items: flex-end; }
    .field { display: grid; gap: 6px; font-size: 12.5px; font-weight: 600; color: var(--muted);
      strong { color: var(--stockage); } }
    .field select { min-width: 260px; }
    .duree { flex: 1 1 220px; input { accent-color: var(--stockage); width: 100%; } }
    .resume { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; }
    .r {
      display: grid; padding: 12px 16px; border-radius: var(--radius-sm); background: var(--bg);
      border-left: 4px solid var(--c);
      strong { font-size: 26px; font-weight: 800; color: var(--c); line-height: 1.1; }
      span { font-size: 12.5px; color: var(--muted); font-weight: 600; }
      &.tient { --c: var(--stockage); } &.partiel { --c: var(--production); } &.coupe { --c: var(--danger); }
    }
    th small { font-size: 10px; opacity: .7; }
    .name { font-weight: 600; } .id { font-size: 11.5px; color: var(--muted); }
    .num { text-align: right; white-space: nowrap; }
    .muted { color: var(--muted); } .small { font-size: 11.5px; color: var(--muted); }
    .bar { height: 8px; min-width: 140px; border-radius: 4px; background: var(--hover); overflow: hidden; margin-bottom: 4px;
      i { display: block; height: 100%; border-radius: 4px; transition: width 300ms ease; }
      .tient { background: var(--stockage); } .partiel { background: var(--production); } .coupe { background: var(--danger); } }
    .empty { text-align: center; color: var(--muted); padding: 30px 16px !important; }
    .note { margin: 0; display: flex; flex-wrap: wrap; gap: 6px; align-items: center; color: var(--muted); font-size: 13px;
      app-icon { color: var(--reseau); } strong { color: var(--text); } }
    .applique { padding: 14px 18px;
      ul { list-style: none; margin: 0; padding: 0; display: grid; gap: 6px; }
      li { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; }
      li > span:first-child { font-weight: 600; min-width: 220px; }
      .crit { color: var(--danger); } }
    @media (max-width: 600px) { .resume { grid-template-columns: 1fr; } .field select { min-width: 0; width: 100%; } .controls > * { flex: 1 1 100%; } }
  `],
})
export class StockageScenarioComponent implements OnInit {
  postes = input.required<Option[]>();
  labels = input<Map<string, string>>(new Map());
  applied = output<void>();

  private api = inject(StockageService);
  private toast = inject(ToastService);

  poste = signal('Poste_Ariana');
  heures = signal(4);
  s = signal<Scenario | null>(null);
  dernier = signal<ScenarioApplique | null>(null);
  busy = signal(false);

  statuts: Record<Statut, { label: string; color: string }> = {
    tient: { label: 'Tient', color: 'var(--stockage)' },
    partiel: { label: 'Partiel', color: 'var(--production)' },
    coupe: { label: 'Coupé', color: 'var(--danger)' },
  };

  kwh = energie; kw = puissance; h = duree;

  ngOnInit() { this.charger(); }

  label(id: string) { return this.labels().get(id) ?? id; }

  pct(autonomie: number, heures: number) { return Math.min(100, (autonomie / heures) * 100); }

  aDecharger() { return (this.s()?.batiments ?? []).some(b => b.energieFournie > 0); }

  charger() {
    this.api.scenario(this.poste(), this.heures()).subscribe({
      next: s => this.s.set(s),
      error: e => this.toast.error(apiError(e)),
    });
  }

  appliquer() {
    this.busy.set(true);
    this.api.appliquerScenario(this.poste(), this.heures()).subscribe({
      next: r => {
        this.busy.set(false);
        this.dernier.set(r);
        const crit = r.changements.filter(c => c.critique).length;
        this.toast.success(`${r.changements.length} stockage(s) déchargé(s)` + (crit ? `, ${crit} devenu(s) critique(s)` : ''));
        this.applied.emit();
        this.charger();
      },
      error: e => { this.busy.set(false); this.toast.error(apiError(e)); },
    });
  }
}
