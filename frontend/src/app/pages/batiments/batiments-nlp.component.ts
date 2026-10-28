import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute } from '@angular/router';
import { apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { DEFINIES, Definie, NlpReponse } from './batiments.models';
import { BatimentsService } from './batiments.service';

/** Question en français → spaCy → SPARQL → résultats (backend/modules/batiments/nlp.py). */
@Component({
  selector: 'app-batiments-nlp',
  standalone: true,
  imports: [FormsModule, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <form class="ask" (ngSubmit)="envoyer()">
      <label class="search">
        <app-icon name="search" [size]="16" />
        <input class="input" name="q" [(ngModel)]="question" maxlength="300" autocomplete="off"
               placeholder="Ex. : bâtiments publics de plus de 1000 m² raccordés en haute tension">
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
        <p class="interp"><span class="eyebrow">Interprétation</span> {{ r.interpretation }}</p>

        <div class="nlp">
          <div>
            <p class="eyebrow">1 · spaCy fr_core_news_sm — tokens, lemmes, POS</p>
            <div class="tokens">
              @for (t of r.analyse.tokens; track $index) {
                <span class="tok"><b>{{ t.texte }}</b><small>{{ t.lemme }}</small><i>{{ t.pos }}</i></span>
              }
            </div>
          </div>
          <div class="side">
            <div>
              <p class="eyebrow">2 · PhraseMatcher — individus</p>
              <div class="tags">
                @for (e of r.analyse.entites; track e.id) {
                  <span class="badge" [style.--c]="couleur(e.type)">« {{ e.texte }} » → sg:{{ e.id }}</span>
                } @empty { <span class="muted">aucun</span> }
              </div>
            </div>
            <div>
              <p class="eyebrow">3 · Types, classes définies, contraintes</p>
              <div class="tags">
                @for (c of r.analyse.classes; track c) { <span class="badge" [style.--c]="'var(--batiments)'">sg:{{ c }}</span> }
                @for (d of definies(r); track d.cle) {
                  <span class="badge" [style.--c]="d.color">{{ d.valeur ? '' : '¬ ' }}{{ d.classe }}</span>
                }
                @if (r.analyse.dpe; as dpe) { <span class="badge" [style.--c]="'var(--production)'">DPE {{ dpe.op }} {{ dpe.lettre }}</span> }
                @for (l of r.analyse.lieux; track l.texte) {
                  <span class="badge" [style.--c]="'var(--reseau)'">lieu « {{ l.texte }} » · {{ l.source }}</span>
                }
                @if (!r.analyse.classes.length && !definies(r).length && !r.analyse.lieux.length && !r.analyse.dpe) { <span class="muted">aucune</span> }
              </div>
            </div>
            @if (r.analyse.ner.length) {
              <div>
                <p class="eyebrow">NER spaCy</p>
                <div class="tags">
                  @for (e of r.analyse.ner; track $index) { <span class="badge">{{ e.texte }} · {{ e.label }}</span> }
                </div>
              </div>
            }
          </div>
        </div>

        <p class="eyebrow">4 · Requête SPARQL générée</p>
        <pre>{{ r.sparql }}</pre>

        @if (r.booleen !== undefined) {
          <p class="bool" [class.non]="!r.booleen">{{ r.booleen ? 'Oui' : 'Non' }} <small class="mono">ASK → {{ r.booleen }}</small></p>
        } @else {
          <p class="eyebrow">5 · Résultats RDFLib · {{ r.lignes?.length ?? 0 }} ligne(s)</p>
          <div class="table-wrap">
            <table class="data">
              <thead><tr>@for (c of r.colonnes; track c) { <th>{{ c }}</th> }</tr></thead>
              <tbody>
                @for (row of r.lignes; track $index) {
                  <tr>@for (c of r.colonnes; track c) { <td [class.mono]="c !== 'label' && c !== 'source' && c !== 'poste'">{{ fmt(row[c]) }}</td> }</tr>
                } @empty {
                  <tr><td [attr.colspan]="r.colonnes?.length || 1" class="empty">Aucun résultat</td></tr>
                }
              </tbody>
            </table>
          </div>
        }
      </section>
    }`,
  styles: [`
    :host { display: grid; gap: 14px; --accent: var(--batiments); }
    .ask { display: flex; gap: 10px; flex-wrap: wrap; }
    .search {
      position: relative; display: flex; align-items: center; flex: 1 1 260px;
      app-icon { position: absolute; left: 11px; color: var(--muted); pointer-events: none; }
      .input { width: 100%; padding-left: 34px; }
    }
    .field-error { margin: -6px 0 0; font-size: 12px; color: var(--danger); }
    .exemples { display: flex; flex-wrap: wrap; gap: 6px; }
    .chip {
      padding: 5px 11px; border-radius: 999px; cursor: pointer; font-size: 12.5px;
      border: 1px solid var(--border); background: var(--bg); color: var(--muted);
      transition: border-color var(--t), color var(--t);
      &:hover { border-color: var(--batiments); color: var(--batiments); }
    }
    .res { display: grid; gap: 12px; }
    .res > .eyebrow { margin: 4px 0 -4px; }
    .interp { margin: 0; font-weight: 600; .eyebrow { margin-right: 8px; } }
    .nlp { display: grid; gap: 16px; grid-template-columns: minmax(0, 3fr) minmax(0, 2fr); }
    .side { display: grid; gap: 12px; align-content: start; }
    .tokens { display: flex; flex-wrap: wrap; gap: 4px; }
    .tok {
      display: grid; padding: 4px 8px; border-radius: 8px; background: var(--bg);
      border: 1px solid var(--border); line-height: 1.25; text-align: center;
      b { font-size: 13px; } small { font-size: 11px; color: var(--batiments); } i { font-size: 10px; color: var(--muted); font-style: normal; }
    }
    .tags { display: flex; flex-wrap: wrap; gap: 4px; }
    .tags .badge { white-space: normal; }
    .muted { color: var(--muted); }
    pre {
      margin: 0; padding: 14px 16px; overflow-x: auto; border-radius: var(--radius-sm);
      background: var(--navy); color: #e8e4dc; font-size: 12.5px; line-height: 1.6;
    }
    .bool { margin: 0; font-size: 22px; font-weight: 800; color: var(--success);
      &.non { color: var(--danger); } small { font-size: 12px; color: var(--muted); font-weight: 500; } }
    .empty { text-align: center; color: var(--muted); padding: 24px !important; }
    table.data td, table.data th { padding: 10px 12px; }
    @media (max-width: 760px) { .nlp { grid-template-columns: 1fr; } }
  `],
})
export class BatimentsNlpComponent implements OnInit {
  private api = inject(BatimentsService);
  private route = inject(ActivatedRoute);

  question = '';
  exemples = signal<string[]>([]);
  r = signal<NlpReponse | null>(null);
  loading = signal(false);
  erreurSaisie = signal('');

  ngOnInit() {
    this.api.exemples().subscribe({ next: e => this.exemples.set(e), error: () => {} });
    const q = this.route.snapshot.queryParamMap.get('q');  // /batiments?tab=question&q=...
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

  definies(r: NlpReponse) {
    return Object.entries(r.analyse.definies).map(([cle, valeur]) => cle === 'stockage'
      ? { cle, valeur, classe: 'possedeStockage (R2)', color: 'var(--stockage)' }
      : { cle, valeur, classe: DEFINIES[cle as Definie].classe, color: DEFINIES[cle as Definie].color });
  }

  couleur(type: string) {
    return {
      batiment: 'var(--batiments)', source: 'var(--production)', ligne: 'var(--reseau)',
      poste: 'var(--reseau)', stockage: 'var(--stockage)',
    }[type] ?? 'var(--muted)';
  }

  fmt(v: unknown) {
    if (v == null) return '—';
    if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString('fr-FR') : (Math.round(v * 10) / 10).toLocaleString('fr-FR');
    return v;
  }
}
