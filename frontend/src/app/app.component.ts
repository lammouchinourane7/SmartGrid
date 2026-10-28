import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { NavigationEnd, Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { filter } from 'rxjs';
import { DOMAINS } from './core/domains';
import { ThemeService } from './core/theme.service';
import { ToastService } from './core/toast.service';
import { IconComponent } from './shared/icon.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, RouterLink, RouterLinkActive, IconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="shell">
      <aside class="sidebar" [class.open]="menuOpen()">
        <a class="brand" routerLink="/">
          <span class="bars">
            @for (d of domains; track d.key) { <i [style.background]="'var(--' + d.key + ')'"></i> }
          </span>
          <span class="brand-name">Smart Grid</span>
          <span class="brand-sub">Ontologie · OWL · SPARQL</span>
        </a>

        <nav>
          <a routerLink="/" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }" class="nav-item">
            <app-icon name="home" /> <span>Vue d'ensemble</span>
          </a>
          <p class="nav-label">Modules</p>
          @for (d of domains; track d.key) {
            <a [routerLink]="'/' + d.key" routerLinkActive="active" class="nav-item" [style.--c]="'var(--' + d.key + ')'">
              <app-icon [name]="d.icon" />
              <span class="grow">{{ d.label }}</span>
              <span class="num">M{{ d.numero }}</span>
            </a>
          }
        </nav>

        <button class="theme" (click)="theme.toggle()">
          <app-icon [name]="theme.theme() === 'dark' ? 'sun' : 'moon'" />
          <span>{{ theme.theme() === 'dark' ? 'Mode clair' : 'Mode sombre' }}</span>
        </button>
      </aside>

      @if (menuOpen()) { <div class="scrim" (click)="menuOpen.set(false)"></div> }

      <div class="main">
        <header class="topbar">
          <button class="btn icon ghost" (click)="menuOpen.set(true)" aria-label="Menu"><app-icon name="menu" /></button>
          <span class="brand-name">Smart Grid</span>
          <button class="btn icon ghost" (click)="theme.toggle()" aria-label="Thème">
            <app-icon [name]="theme.theme() === 'dark' ? 'sun' : 'moon'" />
          </button>
        </header>
        <main class="content"><router-outlet /></main>
      </div>
    </div>

    <div class="toasts" aria-live="polite">
      @for (t of toast.toasts(); track t.id) {
        <div class="toast" [class.error]="t.kind === 'error'" (click)="toast.dismiss(t.id)">
          <app-icon [name]="t.kind === 'error' ? 'alert' : 'check'" [size]="16" />
          <span>{{ t.text }}</span>
        </div>
      }
    </div>
  `,
  styles: [`
    .shell { display: flex; min-height: 100vh; }
    .sidebar {
      position: sticky; top: 0; height: 100vh; width: 248px; flex-shrink: 0;
      display: flex; flex-direction: column; gap: 22px;
      padding: 26px 16px 18px;
      background: var(--navy); color: #d9d4ca;
      transition: transform var(--t), background var(--t);
      z-index: 40;
    }
    .brand { display: grid; gap: 2px; padding: 0 10px; text-decoration: none; color: #f4f1eb; }
    .bars { display: flex; gap: 5px; margin-bottom: 14px; }
    .bars i { width: 22px; height: 4px; border-radius: 4px; }
    .brand-name { font-size: 21px; font-weight: 800; letter-spacing: -.01em; }
    .brand-sub { font-size: 12px; color: #8d99a6; }
    nav { display: grid; gap: 2px; flex: 1; align-content: start; }
    .nav-label { margin: 14px 10px 6px; font-size: 11px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; color: #6f7d8b; }
    .nav-item {
      display: flex; align-items: center; gap: 11px;
      padding: 9px 10px; border-radius: 10px;
      color: #c6cdd4; text-decoration: none; font-weight: 500;
      transition: background var(--t), color var(--t);
      app-icon { color: var(--c, #c6cdd4); }
      &:hover { background: rgba(255,255,255,.05); color: #fff; }
      &.active { background: rgba(255,255,255,.08); color: #fff; box-shadow: inset 3px 0 0 var(--c, #f4f1eb); }
    }
    .grow { flex: 1; }
    .num { font-family: var(--mono); font-size: 11px; color: #6f7d8b; }
    .theme {
      display: flex; align-items: center; gap: 10px; padding: 10px; border-radius: 10px;
      border: 1px solid rgba(255,255,255,.08); background: transparent; color: #c6cdd4; cursor: pointer;
      transition: background var(--t);
      &:hover { background: rgba(255,255,255,.05); }
    }
    .main { flex: 1; min-width: 0; display: flex; flex-direction: column; }
    .topbar { display: none; }
    .content { padding: 40px clamp(16px, 4vw, 48px) 64px; max-width: 1280px; width: 100%; margin: 0 auto; }
    .scrim { display: none; }

    .toasts { position: fixed; right: 16px; bottom: 16px; z-index: 60; display: grid; gap: 8px; }
    .toast {
      display: flex; align-items: center; gap: 10px; max-width: 380px;
      padding: 11px 14px; border-radius: 11px; cursor: pointer;
      background: var(--navy); color: #f4f1eb; box-shadow: var(--shadow-lg);
      border-left: 3px solid var(--success); animation: pop 150ms ease;
      &.error { border-left-color: var(--danger); }
    }

    @media (max-width: 900px) {
      .sidebar { position: fixed; left: 0; transform: translateX(-100%); }
      .sidebar.open { transform: none; box-shadow: var(--shadow-lg); }
      .scrim { display: block; position: fixed; inset: 0; background: rgba(10,19,29,.5); z-index: 30; }
      .topbar {
        display: flex; align-items: center; justify-content: space-between; gap: 8px;
        position: sticky; top: 0; z-index: 20; padding: 8px 8px;
        background: var(--navy); color: #f4f1eb;
        .brand-name { font-size: 17px; }
        .btn { color: #f4f1eb; }
        .btn:hover { background: rgba(255,255,255,.08); }
      }
      .content { padding-top: 24px; }
    }
  `],
})
export class AppComponent {
  theme = inject(ThemeService);
  toast = inject(ToastService);
  domains = DOMAINS;
  menuOpen = signal(false);

  constructor() {
    inject(Router).events.pipe(filter(e => e instanceof NavigationEnd)).subscribe(() => this.menuOpen.set(false));
  }
}
