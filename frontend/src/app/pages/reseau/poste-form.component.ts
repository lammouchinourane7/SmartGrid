import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { ChipSelectComponent } from '../../shared/chip-select.component';
import { IconComponent } from '../../shared/icon.component';
import { Erreurs, Options, Poste, PosteForm, slugify, validerPoste } from './reseau.models';
import { ReseauService } from './reseau.service';

@Component({
  selector: 'app-poste-form',
  standalone: true,
  imports: [FormsModule, ChipSelectComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouveau' }} · PosteElectrique</p>
            <h2>{{ edit ? form.label : 'Ajouter un poste' }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="field">
            <label for="p-label">Libellé (rdfs:label) <span class="req">*</span></label>
            <input id="p-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                   (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                   placeholder="Poste de Bizerte" autofocus>
            @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label for="p-id">Identifiant de l'individu <span class="req">*</span></label>
            <input id="p-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                   (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64"
                   placeholder="Poste_Bizerte">
            @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="row three">
            <div class="field">
              <label for="p-v">Ville</label>
              <input id="p-v" class="input" name="ville" [(ngModel)]="form.ville" (ngModelChange)="changer('ville')"
                     (blur)="toucher('ville')" [class.invalid]="err('ville')" maxlength="60" placeholder="Bizerte">
              @if (err('ville'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="p-c">Capacité (MVA)</label>
              <input id="p-c" class="input" type="number" min="0" max="5000" step="any" name="capacite"
                     [(ngModel)]="form.capacite" (ngModelChange)="changer('capacite')"
                     (blur)="toucher('capacite')" [class.invalid]="err('capacite')">
              @if (err('capacite'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="p-a">Mise en service</label>
              <input id="p-a" class="input" type="number" min="1900" step="1" name="annee" placeholder="2010"
                     [(ngModel)]="form.annee" (ngModelChange)="changer('annee')"
                     (blur)="toucher('annee')" [class.invalid]="err('annee')">
              @if (err('annee'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="field">
            <label>Connecté à (estConnecteA)</label>
            <app-chip-select [options]="autresPostes()" [(value)]="form.connexions" (valueChange)="changer('connexions')"
                             [class.invalid]="err('connexions')" empty="Aucun autre poste" />
            @if (err('connexions'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label>Sert de secours à (secourt)</label>
            <app-chip-select [options]="autresPostes()" [(value)]="form.secours" (valueChange)="changer('secours')"
                             [class.invalid]="err('secours')" empty="Aucun autre poste" />
            @if (err('secours'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label>Géré par (gere)</label>
            <app-chip-select [options]="options().operateurs" [(value)]="form.gestionnaires" (valueChange)="changer('gestionnaires')"
                             [style.--c]="'var(--mesure)'" [class.invalid]="err('gestionnaires')" />
            @if (err('gestionnaires'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          @if (error()) {
            <p class="error"><app-icon name="alert" [size]="16" /> {{ error() }}</p>
          }
        </div>

        <footer class="m-foot">
          <button type="button" class="btn" (click)="closed.emit()">Annuler</button>
          <button type="submit" class="btn primary" [disabled]="saving()">
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : 'Créer le poste' }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class PosteFormComponent implements OnInit {
  poste = input<Poste | null>(null);
  options = input.required<Options>();
  saved = output<string>();
  closed = output<void>();

  private api = inject(ReseauService);
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  form: PosteForm = { id: '', label: '', ville: '', capacite: null, annee: null, connexions: [], secours: [], gestionnaires: [] };

  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  private touches = signal(new Set<string>());
  private envoye = signal(false);

  autresPostes = computed(() => this.options().postes.filter(p => p.id !== this.poste()?.id));

  /** Libellés des autres postes, pour refuser un doublon avant même d'appeler le serveur. */
  private labelsPris = computed(() =>
    this.options().postes.filter(p => p.id !== this.poste()?.id).map(p => p.label.toLowerCase()));

  ngOnInit() {
    const p = this.poste();
    if (p) {
      this.edit = true;
      this.form = {
        id: p.id, label: p.label, ville: p.ville ?? '', capacite: p.capacite, annee: p.annee,
        connexions: [...p.connexions], secours: [...p.secours], gestionnaires: [...p.gestionnaires],
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

  private valider() { this.erreurs.set(validerPoste(this.form, this.edit, this.labelsPris())); }

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
    const req = this.edit ? this.api.modifierPoste(this.form.id, this.form) : this.api.creerPoste(this.form);
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
