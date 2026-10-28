import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { ChipSelectComponent } from '../../shared/chip-select.component';
import { IconComponent } from '../../shared/icon.component';
import {
  CLASSES, Classe, DEFINIES, Erreurs, Options, Systeme, SystemeForm, deduire, slugify, valider,
} from './stockage.models';
import { StockageService } from './stockage.service';

/** Formulaire de création / modification d'un SystemeStockage (INSERT DATA / DELETE-INSERT). */
@Component({
  selector: 'app-systeme-form',
  standalone: true,
  imports: [FormsModule, ChipSelectComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouveau' }} · SystemeStockage</p>
            <h2>{{ edit ? form.label : 'Ajouter un système de stockage' }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="row">
            <div class="field">
              <label for="s-label">Libellé (rdfs:label) <span class="req">*</span></label>
              <input id="s-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                     (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                     placeholder="Batterie du lycée de Sousse" autofocus>
              @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="s-id">Identifiant de l'individu <span class="req">*</span></label>
              <input id="s-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                     (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64"
                     placeholder="Batterie_Lycee_Sousse">
              @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="row">
            <div class="field">
              <label for="s-classe">Type (classe OWL) <span class="req">*</span></label>
              <select id="s-classe" class="input" name="classe" [(ngModel)]="form.classe"
                      (ngModelChange)="changer('classe'); changer('sources'); changer('poste')"
                      (blur)="toucher('classe')" [class.invalid]="err('classe')">
                <option value="" disabled>Choisir…</option>
                @for (c of classeKeys; track c) { <option [value]="c">{{ classes[c].label }}</option> }
              </select>
              @if (err('classe'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="s-techno">Technologie</label>
              <input id="s-techno" class="input" name="technologie" [(ngModel)]="form.technologie" (ngModelChange)="changer('technologie')"
                     maxlength="80" placeholder="Lithium fer phosphate (LFP)" [class.invalid]="err('technologie')">
              @if (err('technologie'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="row three">
            <div class="field">
              <label for="s-cap">Capacité (kWh) <span class="req">*</span></label>
              <input id="s-cap" class="input" type="number" min="0" step="any" name="capacite"
                     [(ngModel)]="form.capacite" (ngModelChange)="changer('capacite')"
                     (blur)="toucher('capacite')" [class.invalid]="err('capacite')">
              @if (err('capacite'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="s-niv">Niveau de charge (%)</label>
              <input id="s-niv" class="input" type="number" min="0" max="100" step="any" name="niveau"
                     [(ngModel)]="form.niveau" (ngModelChange)="changer('niveau')"
                     (blur)="toucher('niveau')" [class.invalid]="err('niveau')">
              @if (err('niveau'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="s-rdt">Rendement (%)</label>
              <input id="s-rdt" class="input" type="number" min="0" max="100" step="any" name="rendement"
                     [(ngModel)]="form.rendement" (ngModelChange)="changer('rendement')"
                     (blur)="toucher('rendement')" [class.invalid]="err('rendement')">
              @if (err('rendement'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="row three">
            <div class="field">
              <label for="s-pw">Puissance de décharge (kW)</label>
              <input id="s-pw" class="input" type="number" min="0" step="any" name="puissance"
                     [(ngModel)]="form.puissance" (ngModelChange)="changer('puissance')"
                     (blur)="toucher('puissance')" [class.invalid]="err('puissance')">
              @if (err('puissance'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="s-an">Année d'installation</label>
              <input id="s-an" class="input" type="number" min="1900" step="1" name="annee" placeholder="2024"
                     [(ngModel)]="form.annee" (ngModelChange)="changer('annee')"
                     (blur)="toucher('annee')" [class.invalid]="err('annee')">
              @if (err('annee'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="s-poste">Raccordé au poste @if (form.classe === 'VolantInertie') { <span class="req">*</span> }</label>
              <select id="s-poste" class="input" name="poste" [(ngModel)]="form.poste" (ngModelChange)="toucher('poste'); changer('poste')"
                      [class.invalid]="err('poste')">
                <option value="">Aucun</option>
                @for (p of options().postes; track p.id) { <option [value]="p.id">{{ p.label }}</option> }
              </select>
              @if (err('poste'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="field">
            <label>Stocke l'énergie de (sources) <span class="req">*</span></label>
            <app-chip-select [options]="sourcesAffichees()" [(value)]="form.sources" (valueChange)="toucher('sources'); changer('sources')"
                             [style.--c]="'var(--production)'" [class.invalid]="err('sources')" />
            @if (err('sources'); as m) { <span class="field-error">{{ m }}</span> }
            @else { <span class="hint">♻ = SourceRenouvelable</span> }
          </div>

          <div class="field">
            <label>Alimente (bâtiments) — déduit possedeStockage par R2</label>
            <app-chip-select [options]="options().batiments" [(value)]="form.batiments" (valueChange)="changer('batiments')"
                             [style.--c]="'var(--batiments)'" />
          </div>

          @if (apercu().length) {
            <div class="inference" [style.--c]="'var(--stockage)'">
              <app-icon name="check" [size]="16" />
              <div>
                <strong>Classes déduites : {{ apercuLabels() }}</strong>
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
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : 'Créer le stockage' }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class SystemeFormComponent implements OnInit {
  systeme = input<Systeme | null>(null);
  options = input.required<Options>();
  batimentsPublics = input<Set<string>>(new Set());
  saved = output<string>();
  closed = output<void>();

  private api = inject(StockageService);
  classes = CLASSES;
  classeKeys = Object.keys(CLASSES) as Classe[];
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  form: SystemeForm = {
    id: '', label: '', classe: '', capacite: null, niveau: null, rendement: null, puissance: null,
    technologie: '', annee: null, poste: '', sources: [], batiments: [],
  };

  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  apercu = signal<string[]>([]);
  private touches = signal(new Set<string>());
  private envoye = signal(false);

  sourcesAffichees = computed(() =>
    this.options().sources.map(s => ({ id: s.id, label: (s.renouvelable ? '♻ ' : '') + s.label })));

  ngOnInit() {
    const s = this.systeme();
    if (s) {
      this.edit = true;
      this.form = {
        id: s.id, label: s.label, classe: s.classe, capacite: s.capacite, niveau: s.niveau,
        rendement: s.rendement, puissance: s.puissance, technologie: s.technologie ?? '', annee: s.annee,
        poste: s.poste ?? '', sources: [...s.sources], batiments: [...s.batiments],
      };
    }
    this.valider();
  }

  apercuLabels() { return this.apercu().join(', '); }

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
    this.erreurs.set(valider(this.form, this.edit, this.options().sources));
    this.apercu.set(deduire(this.form, this.options().sources, this.batimentsPublics()).map(d => DEFINIES[d].classe));
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
