import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { AuthService } from '../../core/services/auth.service';
import { ToastService } from '../../core/services/toast.service';

type Field = 'currentPassword' | 'newPassword' | 'confirmPassword';

@Component({
  selector: 'app-password',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './password.component.html',
})
export class PasswordComponent {
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  currentPassword = signal('');
  newPassword = signal('');
  confirmPassword = signal('');

  submitting = signal(false);
  errorMessage = signal<string | null>(null);

  private touched = signal<Record<Field, boolean>>({
    currentPassword: false,
    newPassword: false,
    confirmPassword: false,
  });

  currentPasswordError = computed(() =>
    this.currentPassword() ? null : 'Fjalekalimi aktual eshte i detyrueshem.',
  );

  newPasswordError = computed(() => {
    const value = this.newPassword();
    if (!value) return 'Fjalekalimi i ri eshte i detyrueshem.';
    if (value.length < 8) return 'Fjalekalimi duhet te kete te pakten 8 karaktere.';
    if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
      return 'Duhet te permbaje te pakten nje shkronje dhe nje numer.';
    }
    if (value === this.currentPassword()) {
      return 'Fjalekalimi i ri duhet te jete i ndryshem nga aktuali.';
    }
    return null;
  });

  confirmPasswordError = computed(() => {
    const value = this.confirmPassword();
    if (!value) return 'Konfirmoni fjalekalimin e ri.';
    if (value !== this.newPassword()) return 'Fjalekalimet nuk perputhen.';
    return null;
  });

  formValid = computed(
    () =>
      !this.currentPasswordError() && !this.newPasswordError() && !this.confirmPasswordError(),
  );

  isTouched(field: Field): boolean {
    return this.touched()[field];
  }

  markTouched(field: Field): void {
    this.touched.update((state) => ({ ...state, [field]: true }));
  }

  submit(): void {
    if (this.submitting()) return;

    this.touched.set({ currentPassword: true, newPassword: true, confirmPassword: true });
    this.errorMessage.set(null);

    if (!this.formValid()) return;

    this.submitting.set(true);

    this.auth
      .changePassword({
        currentPassword: this.currentPassword(),
        newPassword: this.newPassword(),
        confirmPassword: this.confirmPassword(),
      })
      .subscribe({
        next: () => {
          this.submitting.set(false);
          this.toast.show(
            'Fjalekalimi u ndryshua',
            'Te gjitha sesionet u mbyllen. Hyni perseri me fjalekalimin e ri.',
            'low',
          );
          this.auth.forceLogout();
        },
        error: (error: { status?: number; error?: { message?: string } }) => {
          this.submitting.set(false);
          this.errorMessage.set(this.describe(error));
        },
      });
  }

  private describe(error: { status?: number; error?: { message?: string } }): string {
    if (error.status === 0) return 'Lidhja me serverin deshtoi. Kontrollo localhost:8080.';
    if (error.error?.message) return error.error.message;
    return 'Ndryshimi i fjalekalimit deshtoi. Provoni perseri.';
  }
}
