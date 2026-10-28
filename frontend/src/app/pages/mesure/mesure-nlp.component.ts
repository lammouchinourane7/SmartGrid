import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { NlpCandidat, NlpReponse } from './mesure.models';
import { MesureService } from './mesure.service';

/** Question en français → spaCy → SPARQL → résultats (backend/modules/mesure/nlp.py). Lecture seule. */
@Component({
  selector: 'app-mesure-nlp',
  standalone: true,
  imports: [FormsModule, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <form class="ask" (ngSubmit)="envoyer()">
      <label class="search">
        <app-icon name="search" [size]="16" />
        <input class="input" name="q" [(ngModel)]="question" maxlength="300" autocomplete="off"
               placeholder="Ex. : quelle est la consommation totale de Maison1 en janvier 2025 ?">
      </label>
      <button class="btn primary" type="submit" [disabled]="loading() || question.trim().length < 3">
        {{ loading() ? 'Analyse…' : 'Traduire et exécuter' }}
      </button>
    </form>
    @if (erreurSaisie()) { <p class="field-error">{{ erreurSaisie() }}</p> }

    <div class="exemples">
      @for (e of exemples(); track e) {
        <button type="button" class="chip" (click)="question = e; envoyer()">{{ e }}</button>
      }
    </div>

    @if (r(); as r) {
      <section class="res">
        <p class="q"><span class="eyebrow">Question</span> {{ r.analyse.question }}</p>
        @if (r.interpretation) {
          <p class="interp"><span class="eyebrow">Intention et paramètres</span> {{ r.interpretation }}</p>
        }

        <div class="nlp">
          <div>
            <p class="eyebrow">Analyse spaCy · fr_core_news_sm (token / lemme / POS)</p>
            <div class="tokens">
              @for (t of r.analyse.tokens; track $index) {
                <span class="tok"><b>{{ t.texte }}</b><small>{{ t.lemme }}</small><i>{{ t.pos }}</i></span>
              }
            </div>
          </div>
          <div>
            <p class="eyebrow">Entités de l'ontologie (PhraseMatcher)</p>
            <div class="tags">
              @for (e of r.analyse.entites; track e.id) {
                <span class="badge" [style.--c]="couleur(e.type)">« {{ e.texte }} » → sg:{{ e.id }}</span>
              } @empty { <span class="muted">aucune</span> }
            </div>
            <p class="eyebrow mt">Valeurs et période (Matcher)</p>
            <div class="tags">
              @for (c of r.analyse.comparaisons; track $index) {
                <span class="badge" [style.--c]="'var(--mesure)'">
                  {{ c.op === 'entre' ? c.min + ' – ' + c.max : c.op + ' ' + c.valeur }} kWh
                </span>
              }
              @if (r.analyse.periode; as p) {
                <span class="badge" [style.--c]="'var(--reseau)'">{{ p.debut ?? '…' }} → {{ p.fin ?? '…' }}</span>
              }
              @if (!r.analyse.comparaisons.length && !r.analyse.periode) { <span class="muted">aucune</span> }
            </div>
          </div>
        </div>

        @if (r.precision; as p) {
          <div class="precision">
            <p><app-icon name="alert" [size]="16" /> {{ p.message }}</p>
            @if (p.candidats.length) {
              <div class="tags">
                @for (c of p.candidats; track c.id) {
                  <button type="button" class="chip" (click)="preciser(c)">{{ c.label }} <small class="mono">sg:{{ c.id }} · {{ c.type }}</small></button>
                }
              </div>
            }
          </div>
        } @else if (r.erreur) {
          <p class="error"><app-icon name="alert" [size]="16" /> {{ r.erreur }}</p>
        } @else {
          <p class="eyebrow">Requête SPARQL générée</p>
          <pre>{{ r.sparql }}</pre>

          @for (n of r.notes; track n) { <p class="note"><app-icon name="alert" [size]="14" /> {{ n }}</p> }

          @if (r.booleen !== undefined) {
            <p class="bool" [class.non]="!r.booleen">{{ r.booleen ? 'Oui' : 'Non' }} <small class="mono">ASK → {{ r.booleen }}</small></p>
          } @else {
            <div class="table-wrap">
              <table class="data">
                <thead><tr>@for (c of r.colonnes; track c) { <th>{{ c }}</th> }</tr></thead>
                <tbody>
                  @for (row of r.lignes; track $index) {
                    <tr>@for (c of r.colonnes; track c) { <td [class.mono]="c !== 'label'">{{ fmt(row[c]) }}</td> }</tr>
                  } @empty {
                    <tr><td [attr.colspan]="r.colonnes?.length || 1" class="empty">Aucun résultat</td></tr>
                  }
                </tbody>
              </table>
            </div>
          }
        }
      </section>
    }`,
  styles: [`
    :host { display: grid; gap: 14px; }
    .ask { display: flex; gap: 10px; flex-wrap: wrap; }
    .search {
      position: relative; display: flex; align-items: center; flex: 1 1 260px;
      app-icon { position: absolute; left: 11px; color: var(--muted); pointer-events: none; }
      .input { width: 100%; padding-left: 34px; }
    }
    .field-error { margin: -6px 0 0; font-size: 12px; color: var(--danger); }
    .exemples, .tags { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      padding: 5px 11px; border-radius: 999px; cursor: pointer; font-size: 12.5px;
      border: 1px solid var(--border); background: var(--bg); color: var(--muted);
      transition: border-color var(--t), color var(--t);
      &:hover { border-color: var(--mesure); color: var(--mesure); }
    }
    .res { display: grid; gap: 14px; }
    .q, .interp { margin: 0; font-weight: 600; .eyebrow { margin-right: 8px; } }
    .q { font-weight: 500; color: var(--muted); }
    .nlp { display: grid; gap: 14px; grid-template-columns: minmax(0, 2fr) minmax(0, 1fr); }
    .mt { margin-top: 12px; }
    .tokens { display: flex; flex-wrap: wrap; gap: 4px; }
    .tok {
      display: grid; padding: 4px 8px; border-radius: 8px; background: var(--bg);
      border: 1px solid var(--border); line-height: 1.25; text-align: center;
      b { font-size: 13px; } small { font-size: 11px; color: var(--mesure); } i { font-size: 10px; color: var(--muted); font-style: normal; }
    }
    .muted { color: var(--muted); }
    pre {
      margin: 0; padding: 14px 16px; overflow-x: auto; border-radius: var(--radius-sm);
      background: var(--navy); color: #e8e4dc; font-size: 12.5px; line-height: 1.6;
    }
    .note { display: flex; align-items: center; gap: 8px; margin: 0; font-size: 13px; color: var(--muted); }
    .bool { margin: 0; font-size: 22px; font-weight: 800; color: var(--stockage);
      &.non { color: var(--danger); } small { font-size: 12px; color: var(--muted); font-weight: 500; } }
    .empty { text-align: center; color: var(--muted); padding: 24px !important; }
    .error, .precision p {
      display: flex; align-items: center; gap: 8px; margin: 0; padding: 10px 12px; border-radius: var(--radius-sm);
      color: var(--danger); background: color-mix(in srgb, var(--danger) 10%, transparent);
    }
    .precision { display: grid; gap: 10px; }
    .precision p { color: var(--mesure); background: color-mix(in srgb, var(--mesure) 10%, transparent); }
    @media (max-width: 760px) { .nlp { grid-template-columns: 1fr; } }
  `],
})
export class MesureNlpComponent implements OnInit {
  private api = inject(MesureService);
  private route = inject(ActivatedRoute);

  question = '';
  exemples = signal<string[]>([]);
  r = signal<NlpReponse | null>(null);
  loading = signal(false);
  erreurSaisie = signal('');

  ngOnInit() {
    this.api.exemples().subscribe({ next: e => this.exemples.set(e), error: () => {} });
    const q = this.route.snapshot.queryParamMap.get('q');  // /mesure?tab=question&q=...
    if (q) { this.question = q; this.envoyer(); }
  }

  envoyer() {
    const q = this.question.trim();
    if (q.length < 3) return this.erreurSaisie.set('Au moins 3 caractères.');
    this.erreurSaisie.set('');
    this.loading.set(true);
    this.api.question(q).subscribe({
      next: r => { this.r.set(r); this.loading.set(false); },
      error: e => { this.erreurSaisie.set(apiError(e)); this.loading.set(false); },
    });
  }

  /** Remplace le nom ambigu par l'identifiant choisi, puis relance la traduction. */
  preciser(c: NlpCandidat) {
    const r = this.r();
    const ambigu = r?.precision ? r.precision.message.match(/« (.+?) »/)?.[1] : null;
    const original = r?.analyse.question ?? this.question;
    const i = ambigu ? original.toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '').indexOf(ambigu) : -1;
    this.question = i >= 0 ? original.slice(0, i) + c.id + original.slice(i + ambigu!.length) : `${original} (${c.id})`;
    this.envoyer();
  }

  couleur(type: string) {
    return {
      compteur: 'var(--mesure)', mesure: 'var(--mesure)', operateur: 'var(--mesure)', batiment: 'var(--batiments)',
      source: 'var(--production)', poste: 'var(--reseau)', ligne: 'var(--reseau)',
    }[type] ?? 'var(--muted)';
  }

  fmt(v: unknown) {
    if (v == null || v === '') return '—';
    if (typeof v === 'number') return Number.isInteger(v) ? v : Math.round(v * 100) / 100;
    return v;
  }
}
