import { ChangeDetectionStrategy, Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { domain } from '../../core/domains';
import { ToastService, apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { LigneFormComponent } from './ligne-form.component';
import { PosteFormComponent } from './poste-form.component';
import { ReseauGrapheComponent } from './reseau-graphe.component';
import { ReseauNlpComponent } from './reseau-nlp.component';
import {
  CATEGORIES, Categorie, Dependance, Graphe, Ligne, Options, Poste, Stats,
} from './reseau.models';
import { ReseauService } from './reseau.service';

type Tab = 'lignes' | 'postes' | 'graphe' | 'question';

interface Confirm {
  kind: 'ligne' | 'poste';
  id: string;
  label: string;
  deps: Dependance[] | null;
  message: string;
  busy: boolean;
}

/** Module Réseau — Membre 4 · Nourane Lammouchi. */
@Component({
  selector: 'app-reseau',
  standalone: true,
  imports: [FormsModule, IconComponent, LigneFormComponent, PosteFormComponent, ReseauGrapheComponent, ReseauNlpComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './reseau.component.html',
  styleUrl: './reseau.component.scss',
})
export class ReseauComponent implements OnInit {
  private api = inject(ReseauService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  d = domain('reseau');
  cats = CATEGORIES;
  catKeys: Categorie[] = ['HT', 'MT', 'BT'];
  skeletonRows = [1, 2, 3, 4];

  tab = signal<Tab>('lignes');
  stats = signal<Stats | null>(null);
  options = signal<Options | null>(null);
  lignes = signal<Ligne[] | null>(null);
  postes = signal<Poste[] | null>(null);
  graphe = signal<Graphe | null>(null);

  // filtres (lignes)
  q = signal('');
  categorie = signal<Categorie | ''>('');
  tensionMin = signal<number | null>(null);
  tensionMax = signal<number | null>(null);
  poste = signal('');
  qPostes = signal('');

  ligneForm = signal<{ ligne: Ligne | null } | null>(null);
  posteForm = signal<{ poste: Poste | null } | null>(null);
  detail = signal<Ligne | null>(null);
  confirm = signal<Confirm | null>(null);

  private labels = computed(() => {
    const o = this.options();
    const m = new Map<string, string>();
    if (o) for (const list of Object.values(o)) for (const x of list) m.set(x.id, x.label);
    for (const l of this.lignes() ?? []) m.set(l.id, l.label);
    return m;
  });

  filtresActifs = computed(() =>
    !!(this.q() || this.categorie() || this.tensionMin() != null || this.tensionMax() != null || this.poste()));

  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit() {
    this.loadOptions();
    this.loadStats();
    const t = this.route.snapshot.queryParamMap.get('tab');
    this.setTab(t === 'postes' || t === 'graphe' || t === 'question' ? t : 'lignes');
  }

  label(id: string) { return this.labels().get(id) ?? id; }

  setTab(t: Tab) {
    this.tab.set(t);
    this.router.navigate([], { queryParams: { tab: t === 'lignes' ? null : t }, queryParamsHandling: 'merge', replaceUrl: true });
    if (t === 'postes' && !this.postes()) this.loadPostes();
    if (t === 'graphe' && !this.graphe()) this.loadGraphe();
    if (t === 'lignes' && !this.lignes()) this.loadLignes();
  }

  // ------------------------------------------------------------ chargement

  loadOptions() {
    this.api.options().subscribe({ next: o => this.options.set(o), error: e => this.toast.error(apiError(e)) });
  }

  loadStats() {
    this.api.stats().subscribe({ next: s => this.stats.set(s), error: e => this.toast.error(apiError(e)) });
  }

  loadLignes() {
    this.lignes.set(null);
    this.api.lignes({
      q: this.q().trim(), categorie: this.categorie(), poste: this.poste(),
      tensionMin: this.tensionMin(), tensionMax: this.tensionMax(),
    }).subscribe({
      next: r => this.lignes.set(r.items),
      error: e => { this.lignes.set([]); this.toast.error(apiError(e)); },
    });
  }

  loadPostes() {
    this.postes.set(null);
    this.api.postes(this.qPostes().trim()).subscribe({
      next: r => this.postes.set(r.items),
      error: e => { this.postes.set([]); this.toast.error(apiError(e)); },
    });
  }

  loadGraphe() {
    this.graphe.set(null);
    this.api.graphe().subscribe({
      next: g => this.graphe.set(g),
      error: e => this.toast.error(apiError(e)),
    });
  }

  /** Recharge tout ce qui dépend des données après une écriture. */
  private refresh() {
    this.loadOptions();
    this.loadStats();
    this.graphe.set(null);
    if (this.tab() === 'lignes') { this.loadLignes(); this.postes.set(null); }
    if (this.tab() === 'postes') { this.loadPostes(); this.lignes.set(null); }
  }

  // --------------------------------------------------------------- filtres

  search(value: string) {
    this.q.set(value);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadLignes(), 250);
  }

  searchPostes(value: string) {
    this.qPostes.set(value);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadPostes(), 250);
  }

  setCategorie(c: Categorie | '') { this.categorie.set(c); this.loadLignes(); }
  setPoste(p: string) { this.poste.set(p); this.loadLignes(); }

  setTension(which: 'min' | 'max', raw: string) {
    const v = raw === '' ? null : Number(raw);
    (which === 'min' ? this.tensionMin : this.tensionMax).set(v != null && !isNaN(v) ? v : null);
    clearTimeout(this.timer);
    this.timer = setTimeout(() => this.loadLignes(), 300);
  }

  resetFiltres() {
    this.q.set(''); this.categorie.set(''); this.poste.set('');
    this.tensionMin.set(null); this.tensionMax.set(null);
    this.loadLignes();
  }

  filtrerParPoste(id: string) {
    this.poste.set(id);
    this.setTab('lignes');
    this.loadLignes();
  }

  // ------------------------------------------------------------------ CRUD

  ouvrirDetail(l: Ligne) {
    this.detail.set(l);
    this.api.ligne(l.id).subscribe({
      next: r => this.detail.set(r.item),
      error: e => this.toast.error(apiError(e)),
    });
  }

  onSaved(kind: 'ligne' | 'poste') {
    const edit = kind === 'ligne' ? !!this.ligneForm()?.ligne : !!this.posteForm()?.poste;
    this.ligneForm.set(null);
    this.posteForm.set(null);
    this.toast.success(`${kind === 'ligne' ? 'Ligne' : 'Poste'} ${edit ? 'modifié' + (kind === 'ligne' ? 'e' : '') : 'ajouté' + (kind === 'ligne' ? 'e' : '')} dans l'ontologie`);
    this.refresh();
  }

  demanderSuppression(kind: 'ligne' | 'poste', item: { id: string; label: string }) {
    this.confirm.set({
      kind, id: item.id, label: item.label, deps: null, busy: false,
      message: kind === 'ligne'
        ? 'La ligne et tous ses triplets seront retirés du graphe RDF.'
        : 'Le poste, ses connexions et sa gestion seront retirés du graphe RDF.',
    });
  }

  supprimer(force = false) {
    const c = this.confirm();
    if (!c) return;
    this.confirm.set({ ...c, busy: true });
    const req = c.kind === 'ligne' ? this.api.supprimerLigne(c.id, force) : this.api.supprimerPoste(c.id, force);
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.detail.set(null);
        this.toast.success(`${c.label} supprimé${c.kind === 'ligne' ? 'e' : ''}`);
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
}
