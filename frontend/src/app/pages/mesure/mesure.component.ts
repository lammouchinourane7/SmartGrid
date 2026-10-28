import { ChangeDetectionStrategy, Component, OnInit, WritableSignal, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { domain } from '../../core/domains';
import { ToastService, apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { SparqlPanelComponent } from '../../shared/sparql-panel.component';
import { CompteurFormComponent } from './compteur-form.component';
import { MesureFormComponent } from './mesure-form.component';
import { MesureNlpComponent } from './mesure-nlp.component';
import {
  Anomalie, Bilan, Compteur, Dependance, Mesure, Operateur, Options, Stats, TYPES, TypeMesure, fmtDate, fmtKWh,
} from './mesure.models';
import { MesureService } from './mesure.service';
import { OperateurFormComponent } from './operateur-form.component';

type Tab = 'compteurs' | 'mesures' | 'operateurs' | 'bilan' | 'question';
type Kind = 'compteur' | 'mesure' | 'operateur';

interface Confirm {
  kind: Kind;
  id: string;
  label: string;
  deps: Dependance[] | null;
  bloquant: boolean;
  message: string;
  busy: boolean;
}

/** Module Gestion et mesure — Membre 5 · Ibtihel Mechergui. */
@Component({
  selector: 'app-mesure',
  standalone: true,
  imports: [FormsModule, IconComponent, SparqlPanelComponent, CompteurFormComponent, MesureFormComponent,
            OperateurFormComponent, MesureNlpComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './mesure.component.html',
  styleUrl: './mesure.component.scss',
})
export class MesureComponent implements OnInit {
  private api = inject(MesureService);
  private toast = inject(ToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);

  d = domain('mesure');
  types = TYPES;
  typeKeys: TypeMesure[] = ['consommation', 'production'];
  skeletonRows = [1, 2, 3];
  fmtDate = fmtDate;
  fmtKWh = fmtKWh;

  tab = signal<Tab>('compteurs');
  stats = signal<Stats | null>(null);
  options = signal<Options | null>(null);
  compteurs = signal<Compteur[] | null>(null);
  mesures = signal<Mesure[] | null>(null);
  operateurs = signal<Operateur[] | null>(null);
  bilan = signal<Bilan | null>(null);
  anomalies = signal<Anomalie[] | null>(null);
  sparql = signal<string | null>(null);

  // filtres
  qCompteurs = signal('');
  batimentFiltre = signal('');
  qMesures = signal('');
  type = signal<TypeMesure | ''>('');
  compteurFiltre = signal('');
  cible = signal('');
  valeurMin = signal<number | null>(null);
  valeurMax = signal<number | null>(null);
  debut = signal('');
  fin = signal('');
  mode = signal<'chevauchement' | 'inclusion'>('chevauchement');
  qOperateurs = signal('');
  bilanDebut = signal('');
  bilanFin = signal('');

  compteurForm = signal<{ compteur: Compteur | null } | null>(null);
  mesureForm = signal<{ mesure: Mesure | null } | null>(null);
  operateurForm = signal<{ operateur: Operateur | null } | null>(null);
  detailCompteur = signal<Compteur | null>(null);
  detailMesure = signal<Mesure | null>(null);
  confirm = signal<Confirm | null>(null);

  private labels = computed(() => {
    const o = this.options();
    const m = new Map<string, string>();
    if (o) for (const list of Object.values(o)) for (const x of list) m.set(x.id, x.label);
    for (const x of this.mesures() ?? []) m.set(x.id, x.label);
    return m;
  });

  filtresMesures = computed(() => !!(this.qMesures() || this.type() || this.compteurFiltre() || this.cible()
    || this.valeurMin() != null || this.valeurMax() != null || this.debut() || this.fin()));

  private timer?: ReturnType<typeof setTimeout>;

  ngOnInit() {
    this.loadOptions();
    this.loadStats();
    this.loadCompteurs();  // aussi utilisé par le formulaire de mesure (bâtiment du compteur pour R5)
    const t = this.route.snapshot.queryParamMap.get('tab') as Tab | null;
    this.setTab(t && ['mesures', 'operateurs', 'bilan', 'question'].includes(t) ? t : 'compteurs');
  }

  label(id: string) { return this.labels().get(id) ?? id; }

  setTab(t: Tab) {
    this.tab.set(t);
    this.router.navigate([], { queryParams: { tab: t === 'compteurs' ? null : t }, queryParamsHandling: 'merge', replaceUrl: true });
    if (t === 'mesures' && !this.mesures()) this.loadMesures();
    if (t === 'operateurs' && !this.operateurs()) this.loadOperateurs();
    if (t === 'bilan' && !this.bilan()) this.loadBilan();
  }

  // ------------------------------------------------------------ chargement

  loadOptions() {
    this.api.options().subscribe({ next: o => this.options.set(o), error: e => this.toast.error(apiError(e)) });
  }

  loadStats() {
    this.api.stats().subscribe({ next: s => this.stats.set(s), error: e => this.toast.error(apiError(e)) });
  }

  loadCompteurs() {
    this.compteurs.set(null);
    this.api.compteurs(this.qCompteurs().trim(), this.batimentFiltre()).subscribe({
      next: r => { this.compteurs.set(r.items); if (this.tab() === 'compteurs') this.sparql.set(r.sparql); },
      error: e => { this.compteurs.set([]); this.toast.error(apiError(e)); },
    });
  }

  loadMesures() {
    this.mesures.set(null);
    this.api.mesures({
      q: this.qMesures().trim(), type: this.type(), compteur: this.compteurFiltre(), cible: this.cible(),
      valeurMin: this.valeurMin(), valeurMax: this.valeurMax(), debut: this.debut(), fin: this.fin(), mode: this.mode(),
    }).subscribe({
      next: r => { this.mesures.set(r.items); this.sparql.set(r.sparql); },
      error: e => { this.mesures.set([]); this.toast.error(apiError(e)); },
    });
  }

  loadOperateurs() {
    this.operateurs.set(null);
    this.api.operateurs(this.qOperateurs().trim()).subscribe({
      next: r => { this.operateurs.set(r.items); this.sparql.set(r.sparql); },
      error: e => { this.operateurs.set([]); this.toast.error(apiError(e)); },
    });
  }

  loadBilan() {
    if (this.bilanDebut() && this.bilanFin() && this.bilanFin() < this.bilanDebut()) {
      this.toast.error('La date de fin précède la date de début');
      return;
    }
    this.bilan.set(null);
    this.api.bilan(this.bilanDebut(), this.bilanFin()).subscribe({
      next: b => { this.bilan.set(b); this.sparql.set(b.sparql); },
      error: e => this.toast.error(apiError(e)),
    });
    this.api.coherence().subscribe({ next: c => this.anomalies.set(c.anomalies), error: () => this.anomalies.set([]) });
  }

  /** Recharge tout ce qui dépend des données après une écriture. */
  private refresh() {
    this.loadOptions();
    this.loadStats();
    this.loadCompteurs();
    this.bilan.set(null);
    if (this.tab() === 'mesures') this.loadMesures(); else this.mesures.set(null);
    if (this.tab() === 'operateurs') this.loadOperateurs(); else this.operateurs.set(null);
  }

  // --------------------------------------------------------------- filtres

  private debounce(fn: () => void, ms = 250) {
    clearTimeout(this.timer);
    this.timer = setTimeout(fn, ms);
  }

  rechercher(champ: WritableSignal<string>, valeur: string, liste: 'compteurs' | 'mesures' | 'operateurs') {
    champ.set(valeur);
    const charger = { compteurs: () => this.loadCompteurs(), mesures: () => this.loadMesures(), operateurs: () => this.loadOperateurs() };
    this.debounce(charger[liste]);
  }

  setNombre(which: 'min' | 'max', raw: string) {
    const v = raw === '' ? null : Number(raw);
    (which === 'min' ? this.valeurMin : this.valeurMax).set(v != null && !isNaN(v) ? v : null);
    this.debounce(() => this.loadMesures(), 300);
  }

  setPeriode(which: 'debut' | 'fin', v: string) {
    (which === 'debut' ? this.debut : this.fin).set(v);
    if (this.debut() && this.fin() && this.fin() < this.debut()) {
      this.toast.error('La date de fin du filtre précède la date de début');
      return;
    }
    this.loadMesures();
  }

  resetFiltres() {
    this.qMesures.set(''); this.type.set(''); this.compteurFiltre.set(''); this.cible.set('');
    this.valeurMin.set(null); this.valeurMax.set(null); this.debut.set(''); this.fin.set('');
    this.mode.set('chevauchement');
    this.loadMesures();
  }

  voirMesuresDuCompteur(id: string) {
    this.resetFiltresSansCharger();
    this.compteurFiltre.set(id);
    this.detailCompteur.set(null);
    this.setTab('mesures');
    this.loadMesures();
  }

  private resetFiltresSansCharger() {
    this.qMesures.set(''); this.type.set(''); this.cible.set(''); this.valeurMin.set(null); this.valeurMax.set(null);
    this.debut.set(''); this.fin.set('');
  }

  // ------------------------------------------------------------------ CRUD

  ouvrirCompteur(c: Compteur) {
    this.detailCompteur.set(c);
    this.api.compteur(c.id).subscribe({
      next: r => this.detailCompteur.set(r.item),
      error: e => this.toast.error(apiError(e)),
    });
  }

  ouvrirMesure(m: Mesure) {
    this.detailMesure.set(m);
    this.api.mesure(m.id).subscribe({
      next: r => this.detailMesure.set(r.item),
      error: e => this.toast.error(apiError(e)),
    });
  }

  onSaved(kind: Kind, edit: boolean) {
    this.compteurForm.set(null);
    this.mesureForm.set(null);
    this.operateurForm.set(null);
    const nom = { compteur: 'Compteur', mesure: 'Mesure', operateur: 'Opérateur' }[kind];
    const e = kind === 'mesure' ? 'e' : '';
    this.toast.success(`${nom} ${edit ? 'modifié' + e : 'ajouté' + e} dans l'ontologie`);
    this.refresh();
  }

  demanderSuppression(kind: Kind, item: { id: string; label: string }) {
    const message = {
      compteur: 'Le compteur et son installation seront retirés du graphe RDF. Le bâtiment n\'est pas modifié.',
      mesure: 'La mesure, ses valeurs et son lien enregistre seront retirés du graphe RDF.',
      operateur: 'L\'opérateur et ses relations gere seront retirés. Les infrastructures restent intactes.',
    }[kind];
    this.confirm.set({ kind, id: item.id, label: item.label, deps: null, bloquant: false, busy: false, message });
  }

  supprimer(force = false) {
    const c = this.confirm();
    if (!c) return;
    this.confirm.set({ ...c, busy: true });
    const req = c.kind === 'compteur' ? this.api.supprimerCompteur(c.id, force)
      : c.kind === 'mesure' ? this.api.supprimerMesure(c.id) : this.api.supprimerOperateur(c.id, force);
    req.subscribe({
      next: () => {
        this.confirm.set(null);
        this.detailCompteur.set(null);
        this.detailMesure.set(null);
        this.toast.success(`« ${c.label} » supprimé${c.kind === 'mesure' ? 'e' : ''}`);
        this.refresh();
      },
      error: e => {
        if (e.status === 409) {
          this.confirm.set({ ...c, busy: false, deps: e.error.dependances, bloquant: !!e.error.bloquant, message: e.error.error });
        } else {
          this.confirm.set(null);
          this.toast.error(apiError(e));
        }
      },
    });
  }

  maxCible(b: Bilan, t: TypeMesure) {
    return Math.max(1, ...b.parCible.filter(x => x.type === t).map(x => x.totalKWh));
  }

  parType(b: Bilan, t: TypeMesure) { return b.parCible.filter(x => x.type === t); }
}
