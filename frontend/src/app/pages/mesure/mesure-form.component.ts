import { ChangeDetectionStrategy, Component, OnInit, computed, inject, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { apiError } from '../../core/toast.service';
import { IconComponent } from '../../shared/icon.component';
import { Compteur, Erreurs, Mesure, MesureForm, Options, TYPES, TypeMesure, slugify, validerMesure } from './mesure.models';
import { MesureService } from './mesure.service';

@Component({
  selector: 'app-mesure-form',
  standalone: true,
  imports: [FormsModule, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="backdrop" (click)="closed.emit()">
      <form class="modal" (click)="$event.stopPropagation()" (ngSubmit)="submit()" (keydown.escape)="closed.emit()" novalidate>
        <header class="m-head">
          <div>
            <p class="eyebrow">{{ edit ? 'Modifier' : 'Nouvelle' }} · {{ types[form.type].classe }}</p>
            <h2>{{ edit ? form.label : 'Ajouter une mesure' }}</h2>
          </div>
          <button type="button" class="btn icon ghost" (click)="closed.emit()" aria-label="Fermer"><app-icon name="close" /></button>
        </header>

        <div class="m-body">
          <div class="field">
            <label>Type de mesure <span class="req">*</span></label>
            <div class="seg" role="radiogroup">
              @for (t of typeKeys; track t) {
                <button type="button" [class.on]="form.type === t" [style.--c]="types[t].color" (click)="setType(t)">{{ types[t].label }}</button>
              }
            </div>
            <span class="hint">{{ types[form.type].classe }} ⊑ {{ types[form.type].axiome }} · les deux classes sont disjointes</span>
          </div>

          <div class="field">
            <label for="m-label">Libellé (rdfs:label) <span class="req">*</span></label>
            <input id="m-label" class="input" name="label" [(ngModel)]="form.label" (ngModelChange)="syncId(); changer('label')"
                   (blur)="toucher('label')" [class.invalid]="err('label')" maxlength="120"
                   placeholder="Consommation de Maison1 en février 2025" autofocus>
            @if (err('label'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="field">
            <label for="m-id">Identifiant de l'individu <span class="req">*</span></label>
            <input id="m-id" class="input mono" name="id" [(ngModel)]="form.id" (ngModelChange)="idTouched = true; changer('id')"
                   (blur)="toucher('id')" [class.invalid]="err('id')" [disabled]="edit" maxlength="64"
                   placeholder="Mesure_Maison1_Fevrier">
            @if (err('id'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          <div class="row three">
            <div class="field">
              <label for="m-v">valeurKWh <span class="req">*</span></label>
              <input id="m-v" class="input" type="number" min="0" step="any" name="valeur"
                     [(ngModel)]="form.valeur" (ngModelChange)="changer('valeur')"
                     (blur)="toucher('valeur')" [class.invalid]="err('valeur')" placeholder="350">
              @if (err('valeur'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="m-d">dateDebut <span class="req">*</span></label>
              <input id="m-d" class="input" type="date" min="2000-01-01" max="2100-12-31" name="debut"
                     [(ngModel)]="form.debut" (ngModelChange)="changer('debut'); changer('fin')"
                     (blur)="toucher('debut')" [class.invalid]="err('debut')">
              @if (err('debut'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
            <div class="field">
              <label for="m-f">dateFin <span class="req">*</span></label>
              <input id="m-f" class="input" type="date" min="2000-01-01" max="2100-12-31" name="fin"
                     [(ngModel)]="form.fin" (ngModelChange)="changer('fin')"
                     (blur)="toucher('fin')" [class.invalid]="err('fin')">
              @if (err('fin'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          </div>
          <span class="hint">Une date sans heure couvre la journée : début à 00:00:00, fin à 23:59:59.</span>

          <div class="field">
            <label for="m-c">Enregistrée par (enregistre⁻¹)</label>
            <select id="m-c" class="input" name="compteur" [(ngModel)]="form.compteur" (ngModelChange)="changer('compteur'); changer('cible')"
                    [class.invalid]="err('compteur')">
              <option value="">— Aucun compteur —</option>
              @for (c of compteurs(); track c.id) {
                <option [value]="c.id">{{ c.label }} · {{ c.identifiant }}</option>
              }
            </select>
            @if (err('compteur'); as m) { <span class="field-error">{{ m }}</span> }
          </div>

          @if (form.type === 'consommation' && batimentCompteur()) {
            <div class="inference" [style.--c]="'var(--batiments)'">
              <app-icon name="check" [size]="18" />
              <div>
                <strong>Bâtiment déduit par R5 : {{ labelBatiment(batimentCompteur()!) }}</strong>
                <span class="mono">CompteurIntelligent(?c) ^ installeDans(?c, ?b) ^ enregistre(?c, ?m) ^ MesureConsommation(?m) → concerne(?m, ?b)</span>
                <p>Aucun concerne n'est asserté : le bâtiment suit celui du compteur.</p>
              </div>
            </div>
            @if (reaffectation()) {
              <div class="impact" role="alert">
                <h3><app-icon name="alert" [size]="16" /> Réaffectation de bâtiment</h3>
                <p>Cette mesure concerne aujourd'hui <strong>{{ labelBatiment(batimentAssertInitial) }}</strong> (assertion).
                   Rattachée à ce compteur, elle concernera <strong>{{ labelBatiment(batimentCompteur()!) }}</strong> par R5 :
                   l'assertion <code>concerne sg:{{ batimentAssertInitial }}</code> sera retirée.</p>
                <label class="confirm-check">
                  <input type="checkbox" name="confirmer" [(ngModel)]="confirmer"> Je confirme la réaffectation
                </label>
              </div>
            }
          } @else {
            <div class="field">
              <label for="m-t">Concerne {{ form.type === 'consommation' ? '(Batiment)' : '(SourceEnergie)' }} <span class="req">*</span></label>
              <select id="m-t" class="input" name="cible" [(ngModel)]="form.cible" (ngModelChange)="changer('cible')"
                      (blur)="toucher('cible')" [class.invalid]="err('cible')">
                <option value="">— Choisir —</option>
                @for (o of form.type === 'consommation' ? options().batiments : options().sources; track o.id) {
                  <option [value]="o.id">{{ o.label }} · {{ o.classe }}</option>
                }
              </select>
              @if (err('cible'); as m) { <span class="field-error">{{ m }}</span> }
            </div>
          }

          @if (error()) {
            <p class="error"><app-icon name="alert" [size]="16" /> {{ error() }}</p>
          }
        </div>

        <footer class="m-foot">
          <button type="button" class="btn" (click)="closed.emit()">Annuler</button>
          <button type="submit" class="btn primary" [disabled]="saving()">
            {{ saving() ? 'Enregistrement…' : edit ? 'Enregistrer' : 'Créer la mesure' }}
          </button>
        </footer>
      </form>
    </div>`,
  styleUrl: './form.scss',
})
export class MesureFormComponent implements OnInit {
  mesure = input<Mesure | null>(null);
  options = input.required<Options>();
  compteurs = input.required<Compteur[]>();
  saved = output<string>();
  closed = output<void>();

  private api = inject(MesureService);
  types = TYPES;
  typeKeys: TypeMesure[] = ['consommation', 'production'];
  edit = false;
  idTouched = false;
  saving = signal(false);
  error = signal('');
  form: MesureForm = { id: '', label: '', type: 'consommation', valeur: null, debut: '', fin: '', compteur: '', cible: '' };
  private compteurChoisi = signal('');
  /** Dates complètes d'origine : renvoyées telles quelles si le jour n'a pas changé (heure conservée). */
  private origine = { debut: '', fin: '' };

  erreurs = signal<Erreurs>({});
  serveur = signal<Erreurs>({});
  private touches = signal(new Set<string>());
  private envoye = signal(false);
  private labelsPris = signal<string[]>([]);

  batimentCompteur = computed(() => {
    const c = this.compteurs().find(x => x.id === this.compteurChoisi());
    return c && c.batiments.length === 1 ? c.batiments[0] : null;
  });

  /** Bâtiment asserté (concerne) à l'ouverture du formulaire, pour détecter une réaffectation par R5. */
  batimentAssertInitial = '';
  private typeChoisi = signal<TypeMesure>('consommation');
  confirmer = false;
  reaffectation = computed(() => this.edit && this.typeChoisi() === 'consommation' && !!this.batimentAssertInitial
    && !!this.batimentCompteur() && this.batimentCompteur() !== this.batimentAssertInitial);

  ngOnInit() {
    const m = this.mesure();
    if (m) {
      this.edit = true;
      this.origine = { debut: m.debut ?? '', fin: m.fin ?? '' };
      const assertee = m.cibles.find(c => c.via === 'assertion');
      this.form = {
        id: m.id, label: m.label, type: m.type === 'production' ? 'production' : 'consommation',
        valeur: m.valeur, debut: (m.debut ?? '').slice(0, 10), fin: (m.fin ?? '').slice(0, 10),
        compteur: m.compteurs[0] ?? '', cible: assertee?.id ?? '',
      };
      if (this.form.type === 'consommation') this.batimentAssertInitial = assertee?.id ?? '';
    }
    this.compteurChoisi.set(this.form.compteur);
    this.typeChoisi.set(this.form.type);
    this.api.mesures().subscribe({
      next: r => this.labelsPris.set(r.items.filter(x => x.id !== m?.id).map(x => x.label.toLowerCase())),
      error: () => {},
    });
    this.valider();
  }

  labelBatiment(id: string) { return this.options().batiments.find(b => b.id === id)?.label ?? id; }

  setType(t: TypeMesure) {
    if (this.form.type === t) return;
    this.form.type = t;
    this.form.cible = '';
    this.changer('cible');
  }

  err(champ: string) {
    if (this.serveur()[champ]) return this.serveur()[champ];
    return this.envoye() || this.touches().has(champ) ? this.erreurs()[champ] : undefined;
  }

  toucher(champ: string) { this.touches.update(s => new Set(s).add(champ)); }

  changer(champ: string) {
    this.compteurChoisi.set(this.form.compteur);
    this.typeChoisi.set(this.form.type);
    this.serveur.update(e => ({ ...e, [champ]: undefined }));
    this.valider();
  }

  private valider() {
    const cible = this.form.type === 'consommation' && this.batimentCompteur() ? '' : this.form.cible;
    this.erreurs.set(validerMesure({ ...this.form, cible }, this.edit, this.labelsPris(), this.batimentCompteur()));
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
    if (this.reaffectation() && !this.confirmer) {
      this.error.set('Confirmez la réaffectation de bâtiment, ou choisissez « Aucun compteur ».');
      return;
    }
    this.saving.set(true);
    this.error.set('');
    const d: MesureForm = {
      ...this.form,
      confirmerReaffectation: this.reaffectation() && this.confirmer,
      // un bâtiment déduit par R5 n'est pas asserté
      cible: this.form.type === 'consommation' && this.batimentCompteur() ? '' : this.form.cible,
      debut: this.origine.debut.startsWith(this.form.debut) ? this.origine.debut : this.form.debut,
      fin: this.origine.fin.startsWith(this.form.fin) ? this.origine.fin : this.form.fin,
    };
    const req = this.edit ? this.api.modifierMesure(d.id, d) : this.api.creerMesure(d);
    req.subscribe({
      next: res => this.saved.emit(res.sparql),
      error: err => {
        this.serveur.set(err?.error?.champs ?? {});
        // 409 « reaffectation » : le serveur a détecté une assertion que l'interface ne connaissait pas
        if (err.status === 409 && err.error?.reaffectation) this.batimentAssertInitial = err.error.reaffectation.de[0];
        this.error.set(err?.error?.champs ? 'Le serveur a refusé certains champs.' : apiError(err));
        this.saving.set(false);
      },
    });
  }
}
