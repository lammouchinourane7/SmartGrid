import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

const PATHS = {
  sun: 'M12 3v1.5M12 19.5V21M4.6 4.6l1.1 1.1M18.3 18.3l1.1 1.1M3 12h1.5M19.5 12H21M4.6 19.4l1.1-1.1M18.3 5.7l1.1-1.1M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  battery: 'M9 2h6M7 4h10a1 1 0 0 1 1 1v15a1 1 0 0 1-1 1H7a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1zM13 8l-3 5h4l-3 5',
  building: 'M4 21V4a1 1 0 0 1 1-1h8a1 1 0 0 1 1 1v17M14 9h5a1 1 0 0 1 1 1v11M2 21h20M8 7h2M8 11h2M8 15h2M17 13h0M17 17h0',
  pylon: 'M12 2 7 22M12 2l5 20M5 7h14M7 11h10M9.5 15.5 14.5 22M14.5 15.5 9.5 22M4 7v1.5M20 7v1.5',
  gauge: 'M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18zM12 13l4-4M8 17h8M6.5 9l.8.6M17.5 9l-.8.6M12 6v1',
  home: 'M3 10.5 12 3l9 7.5V20a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z',
  plus: 'M12 5v14M5 12h14',
  edit: 'M4 20h4L19 9a2.8 2.8 0 0 0-4-4L4 16v4zM13.5 6.5l4 4',
  trash: 'M4 7h16M10 11v6M14 11v6M5 7l1 13a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1l1-13M9 7V4h6v3',
  search: 'M11 18a7 7 0 1 1 0-14 7 7 0 0 1 0 14zM21 21l-5-5',
  moon: 'M20 14.5A8.5 8.5 0 0 1 9.5 4 8.5 8.5 0 1 0 20 14.5z',
  code: 'M8 7l-5 5 5 5M16 7l5 5-5 5M14 4l-4 16',
  close: 'M6 6l12 12M18 6 6 18',
  graph: 'M6 7a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM18 13a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM6 21a2 2 0 1 0 0-4 2 2 0 0 0 0 4zM7.7 6l8.6 4M7.7 18l8.6-4M6 7v10',
  table: 'M3 5h18v14H3zM3 10h18M3 15h18M9 5v14',
  alert: 'M12 9v4M12 17h0M10.3 3.9 2 18a2 2 0 0 0 1.7 3h16.6a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z',
  refresh: 'M20 11a8 8 0 0 0-14.9-3M4 4v4h4M4 13a8 8 0 0 0 14.9 3M20 20v-4h-4',
  check: 'M5 12l5 5L20 7',
  menu: 'M4 6h16M4 12h16M4 18h16',
  lock: 'M6 11h12v10H6zM8 11V7a4 4 0 0 1 8 0v4',
} as const;

export type IconName = keyof typeof PATHS;

@Component({
  selector: 'app-icon',
  standalone: true,
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <svg [attr.width]="size()" [attr.height]="size()" viewBox="0 0 24 24" fill="none"
         stroke="currentColor" [attr.stroke-width]="stroke()" stroke-linecap="round"
         stroke-linejoin="round" aria-hidden="true">
      <path [attr.d]="d()" />
    </svg>`,
  styles: [':host { display: inline-flex; flex-shrink: 0; }'],
})
export class IconComponent {
  name = input.required<IconName>();
  size = input(18);
  stroke = input(1.8);
  d = computed(() => PATHS[this.name()]);
}
