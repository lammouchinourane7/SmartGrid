import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { domain } from '../../core/domains';
import { ToastService, apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { SparqlPanelComponent } from '../../shared/sparql-panel.component';
import { StockageScenarioComponent } from './scenario.component';
import { StockageNlpComponent } from './stockage-nlp.component';
import {
  BatimentStockage, CLASSES, DEFINIES, DEFINIE_PAR_CLASSE, Definie, Dependance, FAMILLES, Famille,
  Options, SEUIL_CRITIQUE, Stats, Systeme, Triplet, duree, energie, puissance,
} from './stockage.models';
import { StockageService } from './stockage.service';
import { SystemeFormComponent } from './systeme-form.component';

type Tab = 'systemes' | 'batiments' | 'scenario' | 'question';

interface Confirm {
  id: string;
  label: string;
  deps: Dependance[] | null;
  message: string;
  busy: boolean;
}

/** Module Stockage — Membre 2 · Takoua Naceur. */
@Component({
  selector: 'app-stockage',
  standalone: true,
  imports: [FormsModule, IconComponent, SparqlPanelComponent, SystemeFormComponent, StockageScenarioComponent, StockageNlpComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './stockage.component.html',
  styleUrl: './stockage.component.scss',
})
export class StockageComponent implements OnInit {
  private api = inject(StockageService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  d = domain('stockage');
  familles = FAMILLES;
  familleKeys = Object.keys(FAMILLES) as Famille[];
  classes = CLASSES;
  definies = DEFINIES;
  definieKeys = Object.keys(DEFINIES) as Definie[];
  definieParClasse = DEFINIE_PAR_CLASSE;
  seuil = SEUIL_CRITIQUE;
  skeletonRows = [1, 2, 3, 4, 5];
  kwh = energie; kw = puissance; h = duree;

  tab = signal<Tab>('systemes');
  stats = signal<Stats | null>(null);
  options = signal<Options | null>(null);
  systemes = signal<Systeme[] | null>(null);
  batiments = signal<BatimentStockage[] | null>(null);
  sparql = signal<string | null>(null);

  // filtres
  q = signal('');
  famille = signal<Famille | ''>('');
  definie = signal<Definie | ''>('');
  niveauMax = signal<number | null>(null);
  source = signal('');
  poste = signal('');

  form = signal<{ systeme: Systeme | null } | null>(null);
  detail = signal<{ item: Systeme; triplets: Triplet[] | null } | null>(null);
  niveauEdit = signal<number>(50);
  niveauBusy = signal(false);
  confirm = signal<Confirm | null>(null);

  labels = computed(() => {
    const m = new Map<string, string>();
    const o = this.options();
    if (o) for (const list of Object.values(o)) for (const x of list) m.set(x.id, x.label);
    for (const s of this.systemes() ?? []) m.set(s.id, s.label);
    return m;
  });

  batimentsPublics = computed(() => new Set((this.batiments() ?? []).filter(b => b.classe === 'BatimentPublic').map(b => b.id)));

  filtresActifs = computed(() =>
    !!(this.q() || this.famille() || this.definie() || this.niveauMax() != null || this.source() || this.poste()));

  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit() {
    this.loadOptions();
    this.loadStats();
    this.loadBatiments();
    const t = this.route.snapshot.queryParamMap.get('tab');
    this.setTab(t === 'batiments' || t === 'scenario' || t === 'question' ? t : 'systemes');
  }

  label(id: string | null) { return id ? this.labels().get(id) ?? id : '—'; }

  setTab(t: Tab) {
    this.tab.set(t);
    this.router.navigate([], { queryParams: { tab: t === 'systemes' ? null : t }, queryParamsHandling: 'merge', replaceUrl: true });
    if (t === 'systemes' && !this.systemes()) this.loadSystemes();
    if (t === 'batiments' && !this.batiments()) this.loadBatiments();
  }

  // ------------------------------------------------------------ chargement

  loadOptions() {
    this.api.options().subscribe({ next: o => this.options.set(o), error: e => this.toast.error(apiError(e)) });
  }

  loadStats() {
    this.api.stats().subscribe({ next: s => this.stats.set(s), error: e => this.toast.error(apiError(e)) });
  }

  loadSystemes() {
    this.systemes.set(null);
    this.api.systemes({
      q: this.q().trim(), famille: this.famille(), definie: this.definie(),
      niveauMax: this.niveauMax(), source: this.source(), poste: this.poste(),
    }).subscribe({
      next: r => { this.systemes.set(r.items); this.sparql.set(r.sparql); },
      error: e => { this.systemes.set([]); this.toast.error(apiError(e)); },
    });
  }

  loadBatiments() {
    this.api.batiments().subscribe({
      next: r => { this.batiments.set(r.items); if (this.tab() === 'batiments') this.sparql.set(r.sparql); },
      error: e => { this.batiments.set([]); this.toast.error(apiError(e)); },
    });
  }

  /** Recharge tout ce qui dépend des données après une écriture. */
  refresh() {
    this.loadOptions();
    this.loadStats();
    this.loadBatiments();
    if (this.tab() === 'systemes') this.loadSystemes(); else this.systemes.set(null);
  }

  // --------------------------------------------------------------- filtres

  search(value: string) {
    this.q.set(value);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadSystemes(), 250);
  }

  setFamille(f: Famille | '') { this.famille.set(f); this.loadSystemes(); }
  setDefinie(d: Definie | '') { this.definie.set(this.definie() === d ? '' : d); this.loadSystemes(); }
  setSource(s: string) { this.source.set(s); this.loadSystemes(); }
  setPoste(p: string) { this.poste.set(p); this.loadSystemes(); }

  setNiveauMax(raw: string) {
    const v = raw === '' ? null : Number(raw);
    this.niveauMax.set(v != null && !isNaN(v) ? v : null);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadSystemes(), 300);
  }

  filtrerDefinie(d: Definie) {
    this.definie.set(d);
    this.setTab('systemes');
    this.loadSystemes();
  }

  resetFiltres() {
    this.q.set(''); this.famille.set(''); this.definie.set(''); this.niveauMax.set(null);
    this.source.set(''); this.poste.set('');
    this.loadSystemes();
  }

  // ------------------------------------------------------------------ CRUD

  ouvrirDetail(s: Systeme) {
    this.detail.set({ item: s, triplets: null });
    this.niveauEdit.set(s.niveau ?? 0);
    this.api.systeme(s.id).subscribe({
      next: r => this.detail.set({ item: r.item, triplets: r.triplets }),
      error: e => this.toast.error(apiError(e)),
    });
  }

  enregistrerNiveau() {
    const d = this.detail();
    if (!d) return;
    this.niveauBusy.set(true);
    this.api.changerNiveau(d.item.id, this.niveauEdit()).subscribe({
      next: r => {
        this.niveauBusy.set(false);
        this.sparql.set(r.sparql);
        this.toast.success(`Niveau de charge mis à ${r.niveau} %`);
        this.refresh();
        this.ouvrirDetail(d.item);
      },
      error: e => { this.niveauBusy.set(false); this.toast.error(apiError(e)); },
    });
  }

  onSaved(sparql: string) {
    const edit = !!this.form()?.systeme;
    this.form.set(null);
    this.sparql.set(sparql);
    this.toast.success(`Système de stockage ${edit ? 'modifié' : 'ajouté'} dans l'ontologie`);
    this.refresh();
  }

  demanderSuppression(item: { id: string; label: string }) {
    this.confirm.set({
      id: item.id, label: item.label, deps: null, busy: false,
      message: 'Le système de stockage et tous ses triplets seront retirés du graphe RDF.',
    });
  }

  supprimer(force = false) {
    const c = this.confirm();
    if (!c) return;
    this.confirm.set({ ...c, busy: true });
    this.api.supprimer(c.id, force).subscribe({
      next: r => {
        this.confirm.set(null);
        this.detail.set(null);
        this.sparql.set(r.sparql);
        this.toast.success(`${c.label} supprimé`);
        this.refresh();
      },
      error: e => {
        if (e.status === 409) {
          this.confirm.set({ ...c, busy: false, deps: e.error.dependances, message: e.error.error });
        } else {
          this.confirm.set(null);
          this.toast.error(apiError(e));
        }
      },
    });
  }

  // ------------------------------------------------------------ affichage

  couleurCharge(niveau: number | null) {
    if (niveau == null) return 'var(--muted)';
    return niveau < SEUIL_CRITIQUE ? 'var(--danger)' : niveau < 50 ? 'var(--production)' : 'var(--stockage)';
  }

  pctFamille(s: Stats, f: Famille) {
    return s.nb ? ((s.parFamille[f]?.nb ?? 0) / s.nb) * 100 : 0;
  }

  viaLabel(via: string) {
    return { direct: 'estAlimentePar', inverse: 'produitEnergiePour⁻¹', R1: 'règle R1', R6: 'règle R6' }[via] ?? via;
  }
}
