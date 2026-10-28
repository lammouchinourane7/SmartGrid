import { Injectable, signal } from '@angular/core';

export interface Toast { id: number; kind: 'success' | 'error'; text: string; }

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);
  private next = 0;

  success(text: string) { this.push('success', text); }
  error(text: string) { this.push('error', text); }

  dismiss(id: number) {
    this.toasts.update(list => list.filter(t => t.id !== id));
  }

  private push(kind: Toast['kind'], text: string) {
    const id = ++this.next;
    this.toasts.update(list => [...list, { id, kind, text }]);
    setTimeout(() => this.dismiss(id), 4000);
  }
}

/** Extrait le message d'erreur renvoyé par Flask ({ error: "..." }). */
export function apiError(err: any): string {
  return err?.error?.error ?? (err?.status === 0 ? 'Backend injoignable (python app.py lancé ?)' : 'Erreur inattendue');
}
