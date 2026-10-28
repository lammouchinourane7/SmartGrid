import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { domain } from '../../core/domains';
import { ToastService, apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { SparqlPanelComponent } from '../../shared/sparql-panel.component';
import { BatimentFormComponent } from './batiment-form.component';
import { BatimentsNlpComponent } from './batiments-nlp.component';
import {
  Batiment, COULEURS_DPE, DEFINIES, DEFINIE_PAR_CLASSE, DPES, Definie, Dependance, Dpe, Inference, Lien,
  Options, SEUIL_GROS, Stats, TYPES, Triplet, TypeBatiment, VIA, energie, nombre, puissance,
} from './batiments.models';
import { BatimentsService } from './batiments.service';
import { DiagnosticComponent } from './diagnostic.component';

type Tab = 'batiments' | 'inferences' | 'diagnostic' | 'question';

interface Confirm {
  id: string;
  label: string;
  deps: Dependance[] | null;
  message: string;
  busy: boolean;
}

/** Module Bâtiments — Membre 3 · Abir Mosrati. */
@Component({
  selector: 'app-batiments',
  standalone: true,
  imports: [FormsModule, IconComponent, SparqlPanelComponent, BatimentFormComponent, BatimentsNlpComponent, DiagnosticComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './batiments.component.html',
  styleUrl: './batiments.component.scss',
})
export class BatimentsComponent implements OnInit {
  private api = inject(BatimentsService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  d = domain('batiments');
  types = TYPES;
  typeKeys = Object.keys(TYPES) as TypeBatiment[];
  definies = DEFINIES;
  definieKeys = Object.keys(DEFINIES) as Definie[];
  definieParClasse = DEFINIE_PAR_CLASSE;
  dpes = DPES;
  couleursDpe = COULEURS_DPE;
  via = VIA;
  seuilGros = SEUIL_GROS;
  skeletonRows = [1, 2, 3, 4, 5];
  kwh = energie; nb = nombre; kw = puissance;

  tab = signal<Tab>('batiments');
  stats = signal<Stats | null>(null);
  options = signal<Options | null>(null);
  batiments = signal<Batiment[] | null>(null);
  inferences = signal<Inference[] | null>(null);
  sparql = signal<string | null>(null);

  // filtres
  q = signal('');
  type = signal<TypeBatiment | ''>('');
  definie = signal<Definie | ''>('');
  dpe = signal<Dpe | ''>('');
  poste = signal('');
  source = signal('');

  form = signal<{ batiment: Batiment | null } | null>(null);
  detail = signal<{ item: Batiment; triplets: Triplet[] | null } | null>(null);
  consoEdit = signal<number | null>(null);
  consoBusy = signal(false);
  confirm = signal<Confirm | null>(null);

  labels = computed(() => {
    const m = new Map<string, string>();
    const o = this.options();
    if (o) for (const list of Object.values(o)) for (const x of list) m.set(x.id, x.label);
    for (const b of this.batiments() ?? []) m.set(b.id, b.label);
    return m;
  });

  tensions = computed(() => new Map((this.options()?.lignes ?? []).map(l => [l.id, l.tension ?? null])));

  filtresActifs = computed(() =>
    !!(this.q() || this.type() || this.definie() || this.dpe() || this.poste() || this.source()));

  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit() {
    this.loadOptions();
    this.loadStats();
    const t = this.route.snapshot.queryParamMap.get('tab');
    this.setTab(t === 'inferences' || t === 'diagnostic' || t === 'question' ? t : 'batiments');
  }

  label(id: string | null) { return id ? this.labels().get(id) ?? id : '—'; }

  setTab(t: Tab) {
    this.tab.set(t);
    this.router.navigate([], { queryParams: { tab: t === 'batiments' ? null : t }, queryParamsHandling: 'merge', replaceUrl: true });
    if (t === 'batiments') this.loadBatiments();
    if (t === 'inferences') this.loadInferences();
  }

  // ------------------------------------------------------------ chargement

  loadOptions() {
    this.api.options().subscribe({ next: o => this.options.set(o), error: e => this.toast.error(apiError(e)) });
  }

  loadStats() {
    this.api.stats().subscribe({ next: s => this.stats.set(s), error: e => this.toast.error(apiError(e)) });
  }

  loadBatiments() {
    this.batiments.set(null);
    this.api.batiments({
      q: this.q().trim(), type: this.type(), definie: this.definie(), dpe: this.dpe(),
      poste: this.poste(), source: this.source(),
    }).subscribe({
      next: r => { this.batiments.set(r.items); this.sparql.set(r.sparql); },
      error: e => { this.batiments.set([]); this.toast.error(apiError(e)); },
    });
  }

  loadInferences() {
    this.inferences.set(null);
    this.api.inferences().subscribe({
      next: r => { this.inferences.set(r.items); this.sparql.set(r.relationsSparql); },
      error: e => { this.inferences.set([]); this.toast.error(apiError(e)); },
    });
  }

  /** Recharge tout ce qui dépend des données après une écriture. */
  refresh() {
    this.loadOptions();
    this.loadStats();
    if (this.tab() === 'batiments') this.loadBatiments();
    if (this.tab() === 'inferences') this.loadInferences();
  }

  // --------------------------------------------------------------- filtres

  search(value: string) {
    this.q.set(value);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadBatiments(), 250);
  }

  setType(t: TypeBatiment | '') { this.type.set(t); this.loadBatiments(); }
  setDefinie(d: Definie | '') { this.definie.set(this.definie() === d ? '' : d); this.loadBatiments(); }
  setDpe(d: Dpe | '') { this.dpe.set(d); this.loadBatiments(); }
  setPoste(p: string) { this.poste.set(p); this.loadBatiments(); }
  setSource(s: string) { this.source.set(s); this.loadBatiments(); }

  filtrerDefinie(d: Definie) {
    this.definie.set(d);
    if (this.tab() !== 'batiments') this.setTab('batiments'); else this.loadBatiments();
  }

  resetFiltres() {
    this.q.set(''); this.type.set(''); this.definie.set(''); this.dpe.set(''); this.poste.set(''); this.source.set('');
    this.loadBatiments();
  }

  // ------------------------------------------------------------------ CRUD

  ouvrirDetail(b: Batiment | string) {
    const id = typeof b === 'string' ? b : b.id;
    if (typeof b !== 'string') { this.detail.set({ item: b, triplets: null }); this.consoEdit.set(b.consommation); }
    this.api.batiment(id).subscribe({
      next: r => { this.detail.set({ item: r.item, triplets: r.triplets }); this.consoEdit.set(r.item.consommation); },
      error: e => this.toast.error(apiError(e)),
    });
  }

  enregistrerConso() {
    const d = this.detail();
    const v = this.consoEdit();
    if (!d || v == null || isNaN(v) || v < 0) return;
    this.consoBusy.set(true);
    this.api.changerConsommation(d.item.id, v).subscribe({
      next: r => {
        this.consoBusy.set(false);
        this.sparql.set(r.sparql);
        this.toast.success(`Consommation mise à ${energie(r.consommation)}${r.gros ? ' · GrosConsommateur déduit' : ''}`);
        this.refresh();
        this.ouvrirDetail(d.item.id);
      },
      error: e => { this.consoBusy.set(false); this.toast.error(apiError(e)); },
    });
  }

  onSaved(sparql: string) {
    const edit = !!this.form()?.batiment;
    this.form.set(null);
    this.sparql.set(sparql);
    this.toast.success(`Bâtiment ${edit ? 'modifié' : 'ajouté'} dans l'ontologie`);
    this.refresh();
  }

  modifierDepuisDetail(b: Batiment) {
    this.detail.set(null);
    this.form.set({ batiment: b });
  }

  demanderSuppression(item: { id: string; label: string }) {
    this.confirm.set({
      id: item.id, label: item.label, deps: null, busy: false,
      message: 'Le bâtiment et tous ses triplets seront retirés du graphe RDF.',
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

  /** Regroupe les liens par cible : [{id, vias: ['R1', 'R7']}]. */
  grouper(liens: Lien[]) {
    const m = new Map<string, { id: string; vias: string[]; renouvelable?: boolean }>();
    for (const l of liens) {
      const x = m.get(l.id) ?? { id: l.id, vias: [], renouvelable: l.renouvelable };
      if (!x.vias.includes(l.via)) x.vias.push(l.via);
      m.set(l.id, x);
    }
    return [...m.values()];
  }

  vias(vs: string[]) { return vs.map(v => this.via[v] ?? v).join(' · '); }

  pctType(s: Stats, t: TypeBatiment) { return s.nb ? ((s.parType[t]?.nb ?? 0) / s.nb) * 100 : 0; }

  tension(id: string) {
    const t = this.tensions().get(id);
    return t == null ? '' : `${t.toLocaleString('fr-FR')} kV`;
  }

  /** Taux de charge moyen : puissance moyenne appelée / puissance souscrite. */
  charge(b: Batiment) {
    if (!b.consoHoraire || !b.puissance) return null;
    return Math.round((b.consoHoraire / b.puissance) * 100);
  }
}
