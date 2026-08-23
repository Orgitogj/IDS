import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  title: string;
  message: string;
  variant: 'critical' | 'high' | 'medium' | 'low' | 'info';
}

let nextId = 1;

@Injectable({ providedIn: 'root' })
export class ToastService {
  readonly toasts = signal<Toast[]>([]);

  show(
    title: string,
    message: string,
    variant: Toast['variant'] = 'info',
    durationMs = 6000,
  ): void {
    const toast: Toast = { id: nextId++, title, message, variant };
    this.toasts.update((current) => [toast, ...current].slice(0, 5));
    setTimeout(() => this.dismiss(toast.id), durationMs);
  }

  dismiss(id: number): void {
    this.toasts.update((current) => current.filter((t) => t.id !== id));
  }
}
