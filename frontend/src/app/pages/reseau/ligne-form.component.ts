import { ChangeDetectionStrategy, Component, OnInit, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { ChipSelectComponent } from '../../shared/chip-select.component';
import { IconComponent } from '../../shared/icon.component';
import { CATEGORIES, Erreurs, Ligne, LigneForm, Options, categorieDe, slugify, validerLigne } from './reseau.models';
import { ReseauService } from './reseau.service';

@Component({
  selector: 'app-ligne-form',
  standalone: true,
  imports: [FormsModule, ChipSelectComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouvelle' }} · LigneElectrique</p>
            <h2>{{ edit ? form.label : 'Ajouter une ligne' }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="field">
            <label for="l-label">Libellé (rdfs:label) <span class="req">*</span></label>
            <input id="l-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                   (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                   placeholder="Ligne Bizerte–Ariana" autofocus>
            @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label for="l-id">Identifiant de l'individu <span class="req">*</span></label>
            <input id="l-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                   (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64"
                   placeholder="Ligne_Bizerte_Ariana">
            @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="row three">
            <div class="field">
              <label for="l-t">Tension (kV) <span class="req">*</span></label>
              <input id="l-t" class="input" type="number" min="0" max="1000" step="any" name="tension"
                     [(ngModel)]="form.tension" (ngModelChange)="changer('tension'); changer('postes')"
                     (blur)="toucher('tension')" [class.invalid]="err('tension')">
              @if (err('tension'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="l-l">Longueur (km)</label>
              <input id="l-l" class="input" type="number" min="0" max="2000" step="any" name="longueur"
                     [(ngModel)]="form.longueur" (ngModelChange)="changer('longueur')"
                     (blur)="toucher('longueur')" [class.invalid]="err('longueur')">
              @if (err('longueur'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="l-a">Mise en service</label>
              <input id="l-a" class="input" type="number" min="1900" step="1" name="annee" placeholder="2010"
                     [(ngModel)]="form.annee" (ngModelChange)="changer('annee')"
                     (blur)="toucher('annee')" [class.invalid]="err('annee')">
              @if (err('annee'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          @if (preview(); as c) {
            <div class="inference" [style.--c]="cats[c].color">
              <app-icon name="check" [size]="16" />
              <strong>Classe déduite : {{ cats[c].classe }}</strong>
            </div>
          }

          <div class="field">
            <label>Postes reliés (relie) <span class="req">*</span></label>
            <app-chip-select [options]="options().postes" [(value)]="form.postes" (valueChange)="toucher('postes'); changer('postes')"
                             [class.invalid]="err('postes')" />
            @if (err('postes'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label>Transporte vers (bâtiments)</label>
            <app-chip-select [options]="options().batiments" [(value)]="form.batiments" (valueChange)="changer('batiments')"
                             [style.--c]="'var(--batiments)'" [class.invalid]="err('batiments')" />
            @if (err('batiments'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          @if (error()) {
            <p class="error"><app-icon name="alert" [size]="16" /> {{ error() }}</p>
          }
        </div>

        <footer class="m-foot">
          <button type="button" class="btn" (click)="closed.emit()">Annuler</button>
          <button type="submit" class="btn primary" [disabled]="saving()">
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : 'Créer la ligne' }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class LigneFormComponent implements OnInit {
  ligne = input<Ligne | null>(null);
  options = input.required<Options>();
  saved = output<string>();
  closed = output<void>();

  private api = inject(ReseauService);
  cats = CATEGORIES;
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  form: LigneForm = { id: '', label: '', tension: null, longueur: null, annee: null, postes: [], batiments: [] };

  /** Erreurs locales, affichées une fois le champ quitté ou après un essai d'envoi. */
  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  private touches = signal(new Set<string>());
  private envoye = signal(false);

  ngOnInit() {
    const l = this.ligne();
    if (l) {
      this.edit = true;
      this.form = {
        id: l.id, label: l.label, tension: l.tension, longueur: l.longueur, annee: l.annee,
        postes: [...l.postes], batiments: [...l.batiments],
      };
    }
    this.valider();
  }

  preview() { return categorieDe(this.form.tension); }

  err(champ: string) {
    if (this.serveur()[champ]) return this.serveur()[champ];
    return this.envoye() || this.touches().has(champ) ? this.erreurs()[champ] : undefined;
  }

  toucher(champ: string) { this.touches.update(s => new Set(s).add(champ)); }

  changer(champ: string) {
    this.serveur.update(e => ({ ...e, [champ]: undefined }));
    this.valider();
  }

  private valider() { this.erreurs.set(validerLigne(this.form, this.edit)); }

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
    const req = this.edit ? this.api.modifierLigne(f.id, f) : this.api.creerLigne(f);
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
