import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { ChipSelectComponent } from '../../shared/chip-select.component';
import { IconComponent } from '../../shared/icon.component';
import { Erreurs, Operateur, OperateurForm, Options, slugify, validerOperateur } from './mesure.models';
import { MesureService } from './mesure.service';

@Component({
  selector: 'app-operateur-form',
  standalone: true,
  imports: [FormsModule, ChipSelectComponent, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouvel' }} · OperateurReseau</p>
            <h2>{{ edit ? form.label : 'Ajouter un opérateur' }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="field">
            <label for="o-label">Libellé (rdfs:label) <span class="req">*</span></label>
            <input id="o-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                   (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                   placeholder="Régie de distribution du Sahel" autofocus>
            @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label for="o-id">Identifiant de l'individu <span class="req">*</span></label>
            <input id="o-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                   (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64" placeholder="Regie_Sahel">
            @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label>Gère (gere → InfrastructureReseau)</label>
            <p class="group">Postes électriques</p>
            <app-chip-select [options]="postes()" [(value)]="form.gere" (valueChange)="changer('gere')"
                             [class.invalid]="err('gere')" empty="Aucun poste" />
            <p class="group">Lignes électriques</p>
            <app-chip-select [options]="lignes()" [(value)]="form.gere" (valueChange)="changer('gere')"
                             [class.invalid]="err('gere')" empty="Aucune ligne" />
            @if (err('gere'); as m) { <span class="field-error">{{ m }}</span> }
            <span class="hint">R4 : les lignes reliées à un poste géré sont aussi gérées (déduit, inutile de les cocher).</span>
          </div>

          @if (error()) {
            <p class="error"><app-icon name="alert" [size]="16" /> {{ error() }}</p>
          }
        </div>

        <footer class="m-foot">
          <button type="button" class="btn" (click)="closed.emit()">Annuler</button>
          <button type="submit" class="btn primary" [disabled]="saving()">
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : "Créer l'opérateur" }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class OperateurFormComponent implements OnInit {
  operateur = input<Operateur | null>(null);
  options = input.required<Options>();
  saved = output<string>();
  closed = output<void>();

  private api = inject(MesureService);
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  form: OperateurForm = { id: '', label: '', gere: [] };

  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  private touches = signal(new Set<string>());
  private envoye = signal(false);

  postes = computed(() => this.options().infrastructures.filter(i => i.classe === 'PosteElectrique'));
  lignes = computed(() => this.options().infrastructures.filter(i => i.classe !== 'PosteElectrique'));
  private labelsPris = computed(() =>
    this.options().operateurs.filter(o => o.id !== this.operateur()?.id).map(o => o.label.toLowerCase()));

  ngOnInit() {
    const o = this.operateur();
    if (o) {
      this.edit = true;
      this.form = { id: o.id, label: o.label, gere: [...o.gere] };
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

  private valider() { this.erreurs.set(validerOperateur(this.form, this.edit, this.labelsPris())); }

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
    const req = this.edit ? this.api.modifierOperateur(this.form.id, this.form) : this.api.creerOperateur(this.form);
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
