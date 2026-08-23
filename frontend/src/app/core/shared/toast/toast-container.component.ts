import { Component, inject } from '@angular/core';
import {ToastService} from '../../services/toast.service';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  template: `
    <div class="fixed top-4 right-4 z-50 space-y-2 w-80">
      @for (toast of toastService.toasts(); track toast.id) {
        <div
          class="rounded-lg border p-3.5 shadow-xl backdrop-blur bg-[var(--color-surface-elevated)]/95 cursor-pointer animate-[slideIn_0.2s_ease-out]"
          [class]="borderClass(toast.variant)"
          (click)="toastService.dismiss(toast.id)"
        >
          <div class="flex items-start gap-2.5">
            <span
              class="w-2 h-2 rounded-full mt-1 shrink-0"
              [class]="dotClass(toast.variant)"
            ></span>
            <div class="min-w-0">
              <p class="text-xs font-semibold text-white">{{ toast.title }}</p>
              <p class="text-xs text-[var(--color-text-muted)] mt-0.5">{{ toast.message }}</p>
            </div>
          </div>
        </div>
      }
    </div>
  `,
  styles: [
    `
      @keyframes slideIn {
        from {
          transform: translateX(100%);
          opacity: 0;
        }
        to {
          transform: translateX(0);
          opacity: 1;
        }
      }
    `,
  ],
})
export class ToastContainerComponent {
  toastService = inject(ToastService);

  borderClass(variant: string): string {
    const map: Record<string, string> = {
      critical: 'border-[var(--color-critical)]/40',
      high: 'border-[var(--color-high)]/40',
      medium: 'border-[var(--color-medium)]/40',
      low: 'border-[var(--color-low)]/40',
      info: 'border-[var(--color-primary)]/40',
    };
    return map[variant] ?? 'border-[var(--color-border)]';
  }

  dotClass(variant: string): string {
    const map: Record<string, string> = {
      critical: 'bg-[var(--color-critical)]',
      high: 'bg-[var(--color-high)]',
      medium: 'bg-[var(--color-medium)]',
      low: 'bg-[var(--color-low)]',
      info: 'bg-[var(--color-primary)]',
    };
    return map[variant] ?? 'bg-[var(--color-text-muted)]';
  }
}
