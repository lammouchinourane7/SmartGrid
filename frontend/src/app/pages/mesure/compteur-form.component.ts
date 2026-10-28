import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { Compteur, CompteurForm, Erreurs, Impact, Options, Politique, slugify, validerCompteur } from './mesure.models';
import { MesureService } from './mesure.service';

@Component({
  selector: 'app-compteur-form',
  standalone: true,
  imports: [FormsModule, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouveau' }} · CompteurIntelligent</p>
            <h2>{{ edit ? form.label : 'Ajouter un compteur' }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="field">
            <label for="c-label">Libellé (rdfs:label) <span class="req">*</span></label>
            <input id="c-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                   (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                   placeholder="Compteur de l'école d'Ariana" autofocus>
            @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="row">
            <div class="field">
              <label for="c-id">Identifiant de l'individu <span class="req">*</span></label>
              <input id="c-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                     (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64"
                     placeholder="Compteur_Ecole_Ariana">
              @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="c-ident">sg:identifiant <span class="req">*</span></label>
              <input id="c-ident" class="input mono" name="identifiant" [(ngModel)]="form.identifiant" (ngModelChange)="changer('identifiant')"
                     (blur)="toucher('identifiant')" [class.invalid]="err('identifiant')" maxlength="40" placeholder="CPT-0003">
              @if (err('identifiant'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>

          <div class="field">
            <label for="c-bat">Installé dans (installeDans) <span class="req">*</span></label>
            <select id="c-bat" class="input" name="batiment" [(ngModel)]="form.batiment" (ngModelChange)="changer('batiment'); verifierImpact()"
                    (blur)="toucher('batiment')" [class.invalid]="err('batiment')">
              <option value="">— Choisir un bâtiment —</option>
              @for (b of options().batiments; track b.id) { <option [value]="b.id">{{ b.label }} · {{ b.classe }}</option> }
            </select>
            @if (err('batiment'); as m) { <span class="field-error">{{ m }}</span> }
            <span class="hint">CompteurIntelligent ⊑ installeDans exactly 1 Batiment (propriété fonctionnelle)</span>
          </div>

          @if (impact(); as i) {
            @if (i.mesures.length) {
              <section class="impact" role="alert">
                <h3><app-icon name="alert" [size]="16" /> Conséquence sur {{ i.mesures.length }} mesure{{ i.mesures.length > 1 ? 's' : '' }} de consommation</h3>
                <p>Ces mesures n'ont pas de bâtiment asserté : il est déduit par R5 du bâtiment du compteur
                   ({{ i.anciens.join(', ') || '—' }} → {{ i.nouveau }}).</p>
                <ul>@for (m of i.mesures; track m.id) { <li>{{ m.label }} <span class="mono">sg:{{ m.id }}</span></li> }</ul>
                <label>
                  <input type="radio" name="politique" value="reaffecter" [(ngModel)]="politique">
                  <span><strong>Réaffecter</strong> au nouveau bâtiment
                    <small>les mesures suivent le compteur (le concerne asserté vers un bâtiment est retiré)</small></span>
                </label>
                <label>
                  <input type="radio" name="politique" value="conserver" [(ngModel)]="politique" [disabled]="!i.apercu.conserver.length">
                  <span><strong>Conserver</strong> l'ancien bâtiment
                    <small>concerne est asserté vers l'ancien bâtiment, le lien enregistre est retiré (sinon R5 donnerait
                      deux bâtiments) et une note rdfs:comment garde la trace du compteur</small></span>
                </label>
                @if (politique) {
                  <div class="triplets">
                    @for (a of i.apercu[politique]; track a.mesure) {
                      @for (t of a.retires; track t) { <code class="del">− {{ t }}</code> }
                      @for (t of a.ajoutes; track t) { <code class="add">+ {{ t }}</code> }
                      <small>→ {{ a.resultat }}</small>
                    }
                  </div>
                }
              </section>
            }
          }

          @if (error()) {
            <p class="error"><app-icon name="alert" [size]="16" /> {{ error() }}</p>
          }
        </div>

        <footer class="m-foot">
          <button type="button" class="btn" (click)="closed.emit()">Annuler</button>
          <button type="submit" class="btn primary" [disabled]="saving()">
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : 'Créer le compteur' }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class CompteurFormComponent implements OnInit {
  compteur = input<Compteur | null>(null);
  options = input.required<Options>();
  saved = output<string>();
  closed = output<void>();

  private api = inject(MesureService);
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  impact = signal<Impact | null>(null);
  politique: Politique | '' = '';
  form: CompteurForm = { id: '', label: '', identifiant: '', batiment: '' };

  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  private touches = signal(new Set<string>());
  private envoye = signal(false);
  private batimentInitial = '';

  private labelsPris = computed(() =>
    this.options().compteurs.filter(c => c.id !== this.compteur()?.id).map(c => c.label.toLowerCase()));

  ngOnInit() {
    const c = this.compteur();
    if (c) {
      this.edit = true;
      this.batimentInitial = c.batiments.length === 1 ? c.batiments[0] : '';
      this.form = { id: c.id, label: c.label, identifiant: c.identifiant ?? '', batiment: this.batimentInitial };
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

  private valider() { this.erreurs.set(validerCompteur(this.form, this.edit, this.labelsPris())); }

  syncId() {
    if (!this.edit && !this.idTouched) this.form.id = slugify(this.form.label);
  }

  /** Avant tout enregistrement : quelles mesures changeraient de bâtiment (R5) ? */
  verifierImpact() {
    this.politique = '';
    if (!this.edit || !this.form.batiment || this.form.batiment === this.batimentInitial) {
      this.impact.set(null);
      return;
    }
    this.api.impact(this.form.id, this.form.batiment).subscribe({
      next: i => this.impact.set(i),
      error: e => this.error.set(apiError(e)),
    });
  }

  submit() {
    this.envoye.set(true);
    this.valider();
    if (Object.keys(this.erreurs()).length) {
      this.error.set('Corrigez les champs en rouge.');
      return;
    }
    if (this.impact()?.mesures.length && !this.politique) {
      this.error.set('Choisissez ce que deviennent les mesures de consommation du compteur.');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    const req = this.edit
      ? this.api.modifierCompteur(this.form.id, this.form, this.politique || undefined)
      : this.api.creerCompteur(this.form);
    req.subscribe({
      next: res => this.saved.emit(res.sparql),
      error: err => {
        this.saving.set(false);
        if (err.status === 409 && err.error?.mesures) {  // le serveur a détecté un impact
          this.impact.set({ anciens: err.error.anciens, nouveau: err.error.nouveau, mesures: err.error.mesures,
                            apercu: err.error.apercu });
          this.politique = '';
          this.error.set(err.error.error);
          return;
        }
        this.serveur.set(err?.error?.champs ?? {});
        this.error.set(err?.error?.champs ? 'Le serveur a refusé certains champs.' : apiError(err));
      },
    });
  }
}
