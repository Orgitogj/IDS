import { Injectable, signal } from '@angular/core';

export interface Toast {
  id: number;
  title: string;
  message: string;
  variant: 'critical' | 'high' | 'medium' | 'low' | 'info';
}

const RESOURCE_NAMES: Record<string, string> = {
  alarms: 'Alarmet',
  experiments: 'Eksperimentet',
  flows: 'Të dhënat e trafikut',
  incidents: 'Incidentet',
  models: 'Modelet',
  settings: 'Cilësimet',
  users: 'Përdoruesit',
};

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

  backendError(resource: string): void {
    this.show(
      `${RESOURCE_NAMES[resource] ?? 'Të dhënat'} nuk u ngarkuan`,
      'Serveri nuk përgjigjet. Kontrolloni nëse është i ndezur (localhost:8080).',
      'critical',
    );
  }

  dismiss(id: number): void {
    this.toasts.update((current) => current.filter((t) => t.id !== id));
  }
}
