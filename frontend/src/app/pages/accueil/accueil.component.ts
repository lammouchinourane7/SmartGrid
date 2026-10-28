import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { DOMAINS } from '../../core/domains';
import { IconComponent } from '../../shared/icon.component';

@Component({
  selector: 'app-accueil',
  standalone: true,
  imports: [RouterLink, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="hero">
      <div class="bars">
        @for (d of domains; track d.key) { <i [style.background]="'var(--' + d.key + ')'"></i> }
      </div>
      <h1>Ontologie<br>Smart Grid</h1>
      <p>Production, stockage, transport et consommation d'énergie, modélisés avec OWL et SWRL, interrogés en SPARQL avec RDFLib.</p>
    </section>

    <p class="eyebrow">Les modules</p>
    <h2 class="section-title">Le bâtiment au centre du réseau</h2>

    <div class="grid">
      @for (d of domains; track d.key) {
        <a class="card module" [routerLink]="'/' + d.key" [style.--c]="'var(--' + d.key + ')'">
          <span class="tile"><app-icon [name]="d.icon" [size]="24" /></span>
          <span class="badge">Membre {{ d.numero }}</span>
          <h3>{{ d.title }}</h3>
          <p>{{ d.description }}</p>
          <span class="who">{{ d.membre }}</span>
        </a>
      }
    </div>
  `,
  styles: [`
    :host { display: block; }
    .hero {
      padding: clamp(28px, 5vw, 48px); border-radius: var(--radius);
      background: var(--navy); color: #f4f1eb; margin-bottom: 40px;
      h1 { margin: 0; font-size: clamp(34px, 6vw, 56px); line-height: 1.02; font-weight: 800; letter-spacing: -.02em; }
      p { margin: 16px 0 0; color: #b6c0ca; max-width: 56ch; font-size: 15px; }
    }
    .bars { display: flex; gap: 8px; margin-bottom: 26px; }
    .bars i { width: 36px; height: 5px; border-radius: 4px; }
    .section-title { margin: 0 0 20px; font-size: 26px; font-weight: 800; letter-spacing: -.01em; }
    .grid { display: grid; gap: 16px; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); }
    .module {
      display: grid; gap: 8px; align-content: start; padding: 20px;
      color: inherit; text-decoration: none; border-top: 3px solid var(--c);
      &:hover { transform: translateY(-2px); }
      h3 { margin: 4px 0 0; font-size: 17px; }
      p { margin: 0; color: var(--muted); font-size: 13.5px; }
      .badge { justify-self: start; }
    }
    .tile {
      width: 46px; height: 46px; border-radius: 12px; display: grid; place-items: center;
      color: var(--c); background: color-mix(in srgb, var(--c) 14%, transparent);
    }
    .who { font-size: 12.5px; font-weight: 600; color: var(--c); }
  `],
})
export class AccueilComponent {
  domains = DOMAINS;
}
