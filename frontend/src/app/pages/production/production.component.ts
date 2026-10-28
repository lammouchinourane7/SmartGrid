import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { domain } from '../../core/domains';
import { ToastService, apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { SparqlPanelComponent } from '../../shared/sparql-panel.component';
import { ProductionNlpComponent } from './production-nlp.component';
import {
  Categorie, Dependances, FAMILLES, Options, Source, Stats, TYPES, TypeSource, VIA, fmtDate, fmtKW, fmtKWh,
} from './production.models';
import { ProductionService } from './production.service';
import { SourceFormComponent } from './source-form.component';

type Tab = 'sources' | 'tableau' | 'question';

interface Confirm {
  source: Source;
  deps: Dependances | null;
  busy: boolean;
  erreur: string;
}

/** Module Production d'énergie — Membre 1 · Wala Rezgui. */
@Component({
  selector: 'app-production',
  standalone: true,
  imports: [FormsModule, IconComponent, SparqlPanelComponent, SourceFormComponent, ProductionNlpComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './production.component.html',
  styleUrl: './production.component.scss',
})
export class ProductionComponent implements OnInit {
  private api = inject(ProductionService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  d = domain('production');
  types = TYPES;
  familles = FAMILLES;
  via = VIA;
  fmtKW = fmtKW;
  fmtKWh = fmtKWh;
  fmtDate = fmtDate;
  skeletonRows = [1, 2, 3, 4];
  categories: { key: Categorie | ''; label: string }[] = [
    { key: '', label: 'Toutes' }, { key: 'renouvelable', label: 'Renouvelables' }, { key: 'solaire', label: 'Solaire' },
    { key: 'eolien', label: 'Éolien' }, { key: 'non_renouvelable', label: 'Non renouvelables' },
  ];

  tab = signal<Tab>('sources');
  stats = signal<Stats | null>(null);
  options = signal<Options | null>(null);
  sources = signal<Source[] | null>(null);
  sparql = signal<string | null>(null);

  q = signal('');
  categorie = signal<Categorie | ''>('');
  puissanceMin = signal<number | null>(null);
  puissanceMax = signal<number | null>(null);
  sansPuissance = signal(false);
  dateMin = signal('');
  dateMax = signal('');

  form = signal<{ source: Source | null } | null>(null);
  detail = signal<Source | null>(null);
  confirm = signal<Confirm | null>(null);

  private labels = computed(() => {
    const m = new Map<string, string>();
    const o = this.options();
    if (o) for (const list of Object.values(o)) for (const x of list) m.set(x.id, x.label);
    return m;
  });

  filtresActifs = computed(() => !!(this.q() || this.categorie() || this.puissanceMin() != null
    || this.puissanceMax() != null || this.sansPuissance() || this.dateMin() || this.dateMax()));

  maxType = computed(() => Math.max(1, ...(this.stats()?.parType ?? []).map(t => t.puissanceKW)));

  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit() {
    this.loadOptions();
    this.loadStats();
    const t = this.route.snapshot.queryParamMap.get('tab');
    this.setTab(t === 'tableau' || t === 'question' ? t : 'sources');
  }

  label(id: string | null) { return id ? this.labels().get(id) ?? id : '—'; }

  typeLabel(t: string | null) { return t && t in TYPES ? TYPES[t as TypeSource].label : (t ?? 'type ambigu'); }
  typeColor(t: string | null) { return t && t in TYPES ? TYPES[t as TypeSource].color : 'var(--danger)'; }

  setTab(t: Tab) {
    this.tab.set(t);
    this.router.navigate([], { queryParams: { tab: t === 'sources' ? null : t }, queryParamsHandling: 'merge', replaceUrl: true });
    if (t === 'sources' && !this.sources()) this.loadSources();
    if (t === 'tableau' && this.stats()) this.sparql.set(this.stats()!.sparql);
  }

  // ------------------------------------------------------------ chargement

  loadOptions() {
    this.api.options().subscribe({ next: o => this.options.set(o), error: e => this.toast.error(apiError(e)) });
  }

  loadStats() {
    this.api.stats().subscribe({ next: s => this.stats.set(s), error: e => this.toast.error(apiError(e)) });
  }

  loadSources() {
    if (this.dateMin() && this.dateMax() && this.dateMax() < this.dateMin()) {
      this.toast.error('La date maximale précède la date minimale');
      return;
    }
    this.sources.set(null);
    this.api.sources({
      q: this.q().trim(), categorie: this.categorie(), puissanceMin: this.puissanceMin(), puissanceMax: this.puissanceMax(),
      sansPuissance: this.sansPuissance(), dateMin: this.dateMin(), dateMax: this.dateMax(),
    }).subscribe({
      next: r => { this.sources.set(r.items); this.sparql.set(r.sparql); },
      error: e => { this.sources.set([]); this.toast.error(apiError(e)); },
    });
  }

  private refresh() {
    this.loadOptions();
    this.loadStats();
    this.loadSources();
  }

  // --------------------------------------------------------------- filtres

  rechercher(v: string) {
    this.q.set(v);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadSources(), 250);
  }

  setPuissance(which: 'min' | 'max', raw: string) {
    const v = raw === '' ? null : Number(raw);
    (which === 'min' ? this.puissanceMin : this.puissanceMax).set(v != null && Number.isFinite(v) ? v : null);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadSources(), 300);
  }

  setCategorie(c: Categorie | '') { this.categorie.set(c); this.loadSources(); }

  resetFiltres() {
    this.q.set(''); this.categorie.set(''); this.puissanceMin.set(null); this.puissanceMax.set(null);
    this.sansPuissance.set(false); this.dateMin.set(''); this.dateMax.set('');
    this.loadSources();
  }

  // ------------------------------------------------------------------ CRUD

  ouvrirDetail(s: Source) {
    this.detail.set(s);
    this.api.source(s.id).subscribe({
      next: r => { this.detail.set(r.item); this.sparql.set(r.sparql); },
      error: e => this.toast.error(apiError(e)),
    });
  }

  /** Le formulaire a besoin du détail (liens estAlimentePar déclarés côté Bâtiments, affichés en lecture seule). */
  modifier(s: Source) {
    if (s.alimentation) {
      this.detail.set(null);
      this.form.set({ source: s });
      return;
    }
    this.api.source(s.id).subscribe({
      next: r => { this.detail.set(null); this.form.set({ source: r.item }); },
      error: e => this.toast.error(apiError(e)),
    });
  }

  onSaved(edit: boolean) {
    this.form.set(null);
    this.toast.success(`Source ${edit ? 'modifiée' : 'ajoutée'} dans l'ontologie`);
    this.refresh();
  }

  /** Avant toute suppression : dépendances bloquantes et triplets qui partiraient avec la source. */
  demanderSuppression(s: Source) {
    this.confirm.set({ source: s, deps: null, busy: false, erreur: '' });
    this.api.dependances(s.id).subscribe({
      next: deps => this.confirm.update(c => c && { ...c, deps }),
      error: e => this.confirm.update(c => c && { ...c, erreur: apiError(e) }),
    });
  }

  supprimer() {
    const c = this.confirm();
    if (!c) return;
    this.confirm.set({ ...c, busy: true });
    this.api.supprimer(c.source.id).subscribe({
      next: () => {
        this.confirm.set(null);
        this.detail.set(null);
        this.toast.success(`« ${c.source.label} » supprimée`);
        this.refresh();
      },
      error: e => {
        if (e.status === 409) {
          this.confirm.set({ ...c, busy: false, deps: { bloquantes: e.error.dependances, supprimees: [] }, erreur: e.error.error });
        } else {
          this.confirm.set(null);
          this.toast.error(apiError(e));
        }
      },
    });
  }
}
