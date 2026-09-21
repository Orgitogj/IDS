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
    this.currentPassword() ? null : 'Fjalëkalimi aktual është i detyrueshëm.',
  );

  newPasswordError = computed(() => {
    const value = this.newPassword();
    if (!value) return 'Fjalëkalimi i ri është i detyrueshëm.';
    if (value.length < 8) return 'Fjalëkalimi duhet të ketë të paktën 8 karaktere.';
    if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
      return 'Duhet të përmbajë të paktën një shkronjë dhe një numër.';
    }
    if (value === this.currentPassword()) {
      return 'Fjalëkalimi i ri duhet të jetë i ndryshëm nga ai aktual.';
    }
    return null;
  });

  confirmPasswordError = computed(() => {
    const value = this.confirmPassword();
    if (!value) return 'Konfirmoni fjalëkalimin e ri.';
    if (value !== this.newPassword()) return 'Fjalëkalimet nuk përputhen.';
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
            'Fjalëkalimi u ndryshua',
            'Të gjitha sesionet u mbyllën. Hyni përsëri me fjalëkalimin e ri.',
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
    if (error.status === 0) return 'Serveri nuk përgjigjet. Kontrolloni nëse është i ndezur (localhost:8080).';
    if (error.error?.message) return error.error.message;
    return 'Fjalëkalimi nuk u ndryshua. Provoni përsëri.';
  }
}
