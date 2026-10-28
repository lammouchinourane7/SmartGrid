import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { ChipSelectComponent } from '../../shared/chip-select.component';
import { IconComponent } from '../../shared/icon.component';
import { Erreurs, Options, Source, SourceForm, TYPES, TYPE_KEYS, TypeSource, slugify, valider } from './production.models';
import { ProductionService } from './production.service';

@Component({
  selector: 'app-source-form',
  standalone: true,
  imports: [FormsModule, ChipSelectComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouvelle' }} · sg:{{ form.type }}</p>
            <h2>{{ edit ? form.label : "Ajouter une source d'énergie" }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="field">
            <label>Type (classe la plus précise) <span class="req">*</span></label>
            <div class="types" role="radiogroup">
              @for (t of typeKeys; track t) {
                <button type="button" class="type" [class.on]="form.type === t" [style.--c]="types[t].color"
                        [attr.aria-pressed]="form.type === t" (click)="form.type = t; changer('type'); changer('lignes')">
                  <strong>{{ types[t].label }}</strong><small class="mono">{{ t }} ⊑ {{ types[t].parent }}</small>
                </button>
              }
            </div>
            @if (err('type'); as m) { <span class="field-error">{{ m }}</span> }
            <span class="hint">Solaire et Eolien sont des SourceRenouvelable : le type parent est déduit, pas ajouté.</span>
          </div>

          <div class="field">
            <label for="s-label">Libellé (rdfs:label) <span class="req">*</span></label>
            <input id="s-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                   (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                   placeholder="Centrale solaire de Kairouan" autofocus>
            @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label for="s-id">Identifiant de l'individu (URI sg:…) <span class="req">*</span></label>
            <input id="s-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                   (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64"
                   placeholder="CentraleSolaire_Kairouan">
            @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="row">
            <div class="field">
              <label for="s-p">Puissance installée (kW)</label>
              <input id="s-p" class="input" type="number" min="0" step="any" name="puissance" placeholder="non renseignée"
                     [(ngModel)]="form.puissance" (ngModelChange)="changer('puissance')"
                     (blur)="toucher('puissance')" [class.invalid]="err('puissance')">
              @if (err('puissance'); as m) { <span class="field-error">{{ m }}</span> }
              <span class="hint">Puissance (kW), pas énergie (kWh). Vide = non renseignée, jamais 0.</span>
            </div>
            <div class="field">
              <label for="s-d">Date de mise en service</label>
              <input id="s-d" class="input" type="date" min="1900-01-01" [max]="aujourdhui" name="date"
                     [(ngModel)]="form.date" (ngModelChange)="changer('date')"
                     (blur)="toucher('date')" [class.invalid]="err('date')">
              @if (err('date'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="field">
            <label>Injecte dans (injecteDans → LigneElectrique) @if (form.type === 'Eolien') { <span class="req">*</span> }</label>
            <app-chip-select [options]="lignes()" [(value)]="form.lignes" (valueChange)="changer('lignes')"
                             [style.--c]="'var(--reseau)'" [class.invalid]="err('lignes')" empty="Aucune ligne" />
            @if (err('lignes'); as m) { <span class="field-error">{{ m }}</span> }
            <span class="hint">R1 : les bâtiments desservis par ces lignes (transporteVers) seront alimentés par déduction.</span>
          </div>

          <div class="field">
            <label>Alimente directement (produitEnergiePour → Batiment)</label>
            <app-chip-select [options]="options().batiments" [(value)]="form.batiments" (valueChange)="changer('batiments')"
                             [style.--c]="'var(--batiments)'" [class.invalid]="err('batiments')" empty="Aucun bâtiment" />
            @if (err('batiments'); as m) { <span class="field-error">{{ m }}</span> }
            @if (cotesBatiments().length) {
              <div class="lecture">
                <span>Déclarés côté Bâtiments (estAlimentePar, lecture seule) :</span>
                @for (b of cotesBatiments(); track b) { <span class="badge" [style.--c]="'var(--batiments)'">{{ labelBatiment(b) }}</span> }
              </div>
            }
          </div>

          @if (error()) {
            <p class="error"><app-icon name="alert" [size]="16" /> {{ error() }}</p>
          }
        </div>

        <footer class="m-foot">
          <button type="button" class="btn" (click)="closed.emit()">Annuler</button>
          <button type="submit" class="btn primary" [disabled]="saving()">
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : 'Créer la source' }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class SourceFormComponent implements OnInit {
  source = input<Source | null>(null);
  options = input.required<Options>();
  saved = output<string>();
  closed = output<void>();

  private api = inject(ProductionService);
  types = TYPES;
  typeKeys = TYPE_KEYS;
  aujourdhui = new Date().toISOString().slice(0, 10);
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  form: SourceForm = { id: '', label: '', type: 'Solaire', puissance: null, date: '', lignes: [], batiments: [] };

  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  private touches = signal(new Set<string>());
  private envoye = signal(false);

  lignes = computed(() => this.options().lignes.map(l => ({
    id: l.id, label: l.tension != null ? `${l.label} · ${l.tension} kV` : l.label,
  })));
  /** estAlimentePar déclarés par le module Bâtiments : affichés, jamais modifiés ici. */
  cotesBatiments = computed(() => (this.source()?.alimentation ?? [])
    .filter(a => a.chemins.some(c => c.via === 'estAlimentePar')).map(a => a.batiment));
  private labelsPris = computed(() =>
    this.options().sources.filter(s => s.id !== this.source()?.id).map(s => s.label.toLowerCase()));

  ngOnInit() {
    const s = this.source();
    if (s) {
      this.edit = true;
      this.form = {
        id: s.id, label: s.label, type: (s.type ?? 'SourceEnergie') as TypeSource, puissance: s.puissance,
        date: (s.date ?? '').slice(0, 10), lignes: [...s.lignes], batiments: [...s.batimentsDirects],
      };
    }
    this.valider();
  }

  labelBatiment(id: string) { return this.options().batiments.find(b => b.id === id)?.label ?? id; }

  err(champ: string) {
    if (this.serveur()[champ]) return this.serveur()[champ];
    return this.envoye() || this.touches().has(champ) ? this.erreurs()[champ] : undefined;
  }

  toucher(champ: string) { this.touches.update(s => new Set(s).add(champ)); }

  changer(champ: string) {
    this.serveur.update(e => ({ ...e, [champ]: undefined }));
    this.valider();
  }

  private valider() { this.erreurs.set(valider(this.form, this.edit, this.labelsPris())); }

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
    const d = { ...this.form, puissance: (this.form.puissance as unknown) === '' ? null : this.form.puissance };
    const req = this.edit ? this.api.modifier(d.id, d) : this.api.creer(d);
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
