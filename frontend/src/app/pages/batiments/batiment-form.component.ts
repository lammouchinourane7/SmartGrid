import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { ChipSelectComponent } from '../../shared/chip-select.component';
import { IconComponent } from '../../shared/icon.component';
import {
  Batiment, BatimentForm, COULEURS_DPE, DEFINIES, DPES, Dpe, Erreurs, Options, TYPES, TypeBatiment,
  deduire, dpeCalcule, slugify, sourcesDeduites, valider,
} from './batiments.models';
import { BatimentsService } from './batiments.service';

/** Formulaire de création / modification d'un Batiment (INSERT DATA / DELETE-INSERT). */
@Component({
  selector: 'app-batiment-form',
  standalone: true,
  imports: [FormsModule, ChipSelectComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouveau' }} · Batiment</p>
            <h2>{{ edit ? form.label : 'Ajouter un bâtiment' }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="row">
            <div class="field">
              <label for="b-label">Libellé (rdfs:label) <span class="req">*</span></label>
              <input id="b-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                     (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                     placeholder="Lycée pilote de Sousse" autofocus>
              @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="b-id">Identifiant de l'individu <span class="req">*</span></label>
              <input id="b-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                     (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64"
                     placeholder="Lycee_Sousse">
              @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="row">
            <div class="field">
              <label for="b-classe">Type (classe OWL, disjointes) <span class="req">*</span></label>
              <select id="b-classe" class="input" name="classe" [(ngModel)]="form.classe"
                      (ngModelChange)="changer('classe'); changer('lignes'); changer('sources')"
                      (blur)="toucher('classe')" [class.invalid]="err('classe')">
                <option value="" disabled>Choisir…</option>
                @for (t of typeKeys; track t) { <option [value]="t">{{ types[t].label }}</option> }
              </select>
              @if (err('classe'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="b-adr">Adresse</label>
              <input id="b-adr" class="input" name="adresse" [(ngModel)]="form.adresse" (ngModelChange)="changer('adresse')"
                     maxlength="160" placeholder="Avenue Habib Bourguiba, Sousse" [class.invalid]="err('adresse')">
              @if (err('adresse'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="row three">
            <div class="field">
              <label for="b-conso">Consommation (kWh/an) <span class="req">*</span></label>
              <input id="b-conso" class="input" type="number" min="0" step="any" name="consommation"
                     [(ngModel)]="form.consommation" (ngModelChange)="changer('consommation')"
                     (blur)="toucher('consommation')" [class.invalid]="err('consommation')">
              @if (err('consommation'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="b-surf">Surface (m²)</label>
              <input id="b-surf" class="input" type="number" min="0" step="any" name="surface"
                     [(ngModel)]="form.surface" (ngModelChange)="changer('surface')"
                     (blur)="toucher('surface')" [class.invalid]="err('surface')">
              @if (err('surface'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="b-dpe">Classe énergétique (DPE)</label>
              <select id="b-dpe" class="input" name="dpe" [(ngModel)]="form.dpe" (ngModelChange)="changer('dpe')">
                <option value="">Non renseignée</option>
                @for (l of dpes; track l) { <option [value]="l">{{ l }}</option> }
              </select>
              @if (dpeSuggere(); as s) {
                @if (s !== form.dpe) {
                  <button type="button" class="suggest" [title]="intensite() + ' kWh/m²·an'" (click)="form.dpe = s; changer('dpe')">
                    <span class="dpe" [style.background]="couleurs[s]">{{ s }}</span> calculée · utiliser
                  </button>
                } @else { <span class="hint">Cohérente avec l'intensité ({{ intensite() }} kWh/m²)</span> }
              }
            </div>
          </div>

          <div class="row three">
            <div class="field">
              <label for="b-occ">Occupants</label>
              <input id="b-occ" class="input" type="number" min="0" step="1" name="occupants"
                     [(ngModel)]="form.occupants" (ngModelChange)="changer('occupants')"
                     (blur)="toucher('occupants')" [class.invalid]="err('occupants')">
              @if (err('occupants'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="b-an">Année de construction</label>
              <input id="b-an" class="input" type="number" min="1800" step="1" name="annee" placeholder="2005"
                     [(ngModel)]="form.annee" (ngModelChange)="changer('annee')"
                     (blur)="toucher('annee')" [class.invalid]="err('annee')">
              @if (err('annee'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="b-pw">Puissance souscrite (kW)</label>
              <input id="b-pw" class="input" type="number" min="0" step="any" name="puissance"
                     [(ngModel)]="form.puissance" (ngModelChange)="changer('puissance')"
                     (blur)="toucher('puissance')" [class.invalid]="err('puissance')">
              @if (err('puissance'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="field">
            <label>Raccordé à (estRaccordeA) <span class="req">*</span></label>
            <app-chip-select [options]="lignesAffichees()" [(value)]="form.lignes" (valueChange)="toucher('lignes'); changer('lignes'); changer('sources')"
                             [style.--c]="'var(--reseau)'" [class.invalid]="err('lignes')" />
            @if (err('lignes'); as m) { <span class="field-error">{{ m }}</span> }
            @else { <span class="hint">HT ≥ 63 kV → BatimentRaccordeHT · R3 déduit le poste qui dessert le bâtiment</span> }
          </div>

          <div class="field">
            <label>Alimenté directement par (estAlimentePar) @if (form.classe === 'BatimentPublic') { <span class="req">* min 2</span> }</label>
            <app-chip-select [options]="sourcesAffichees()" [(value)]="form.sources" (valueChange)="toucher('sources'); changer('sources')"
                             [style.--c]="'var(--production)'" [class.invalid]="err('sources')" />
            @if (err('sources'); as m) { <span class="field-error">{{ m }}</span> }
            @else {
              <span class="hint">♻ = SourceRenouvelable ·
                {{ nbSources() }} source(s) au total avec R7 (lignes) et R6 (stockages)</span>
            }
          </div>

          <div class="field">
            <label>Stockages qui l'alimentent (alimente → possedeStockage par R2)</label>
            <app-chip-select [options]="options().stockages" [(value)]="form.stockages" (valueChange)="changer('stockages'); changer('sources')"
                             [style.--c]="'var(--stockage)'" />
          </div>

          @if (apercu().length) {
            <div class="inference" [style.--c]="'var(--batiments)'">
              <app-icon name="check" [size]="16" />
              <div>
                <strong>Classes déduites : {{ apercu().join(', ') }}</strong>
                <span class="mono">classes définies (≡) évaluées en direct</span>
              </div>
            </div>
          }

          @if (error()) {
            <p class="error"><app-icon name="alert" [size]="16" /> {{ error() }}</p>
          }
        </div>

        <footer class="m-foot">
          <button type="button" class="btn" (click)="closed.emit()">Annuler</button>
          <button type="submit" class="btn primary" [disabled]="saving()">
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : 'Créer le bâtiment' }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class BatimentFormComponent implements OnInit {
  batiment = input<Batiment | null>(null);
  options = input.required<Options>();
  saved = output<string>();
  closed = output<void>();

  private api = inject(BatimentsService);
  types = TYPES;
  typeKeys = Object.keys(TYPES) as TypeBatiment[];
  dpes = DPES;
  couleurs = COULEURS_DPE;
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  form: BatimentForm = {
    id: '', label: '', classe: '', adresse: '', consommation: null, surface: null, occupants: null,
    annee: null, dpe: '', puissance: null, lignes: [], sources: [], stockages: [],
  };

  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  apercu = signal<string[]>([]);
  nbSources = signal(0);
  intensite = signal<number | null>(null);
  dpeSuggere = signal<Dpe | null>(null);
  private compteurs = 0;
  private fixes: string[] = [];   // sources liées hors formulaire (produitEnergiePour, R1 via transporteVers)
  private touches = signal(new Set<string>());
  private envoye = signal(false);

  lignesAffichees = computed(() =>
    this.options().lignes.map(l => ({ id: l.id, label: `${l.label}${l.tension != null ? ` · ${l.tension} kV` : ''}` })));
  sourcesAffichees = computed(() =>
    this.options().sources.map(s => ({ id: s.id, label: (s.renouvelable ? '♻ ' : '') + s.label })));

  ngOnInit() {
    const b = this.batiment();
    if (b) {
      this.edit = true;
      this.compteurs = b.compteurs.length;
      this.fixes = [...new Set(b.sources.filter(s => s.via === 'inverse' || s.via === 'R1').map(s => s.id))];
      this.form = {
        id: b.id, label: b.label, classe: b.classe, adresse: b.adresse ?? '', consommation: b.consommation,
        surface: b.surface, occupants: b.occupants, annee: b.annee, dpe: b.dpe ?? '', puissance: b.puissance,
        lignes: [...new Set(b.lignes.filter(l => l.via === 'estRaccordeA').map(l => l.id))],
        sources: [...new Set(b.sources.filter(s => s.via === 'direct').map(s => s.id))],
        stockages: [...new Set(b.stockages.map(x => x.id))],
      };
    }
    this.valider();
  }

  err(champ: string) {
    if (this.serveur()[champ]) return this.serveur()[champ];
    return this.envoye() || this.touches().has(champ) ? this.erreurs()[champ] : undefined;
  }

  toucher(champ: string) { this.touches.update(s => new Set(s).add(champ)); }

  changer(champ: string) {
    this.serveur.update(e => ({ ...e, [champ]: undefined }));
    this.valider();
  }

  private valider() {
    const o = this.options();
    this.erreurs.set(valider(this.form, this.edit, o, this.fixes));
    this.apercu.set(deduire(this.form, o, this.compteurs, this.fixes).map(d => DEFINIES[d].classe));
    this.nbSources.set(sourcesDeduites(this.form, o, this.fixes).size);
    const c = Number(this.form.consommation), s = Number(this.form.surface);
    const i = this.form.consommation != null && this.form.surface != null && s > 0 && !isNaN(c) ? Math.round((c / s) * 10) / 10 : null;
    this.intensite.set(i);
    this.dpeSuggere.set(dpeCalcule(i));
    if (this.envoye() && !Object.keys(this.erreurs()).length) this.error.set('');
  }

  syncId() {
    if (!this.edit && !this.idTouched) this.form.id = slugify(this.form.label);
  }

  submit() {
    this.envoye.set(true);
    this.valider();
    if (Object.keys(this.erreurs()).length) {
      this.error.set('Corrigez les champs en rouge.');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    const f = this.form;
    const req = this.edit ? this.api.modifier(f.id, f) : this.api.creer(f);
    req.subscribe({
      next: res => this.saved.emit(res.sparql),
      error: err => {
        this.serveur.set(err?.error?.champs ?? {});
        this.error.set(err?.error?.champs ? 'Le serveur a refusé certains champs.' : apiError(err));
        this.saving.set(false);
      },
    });
  }
}
