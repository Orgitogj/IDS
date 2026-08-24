import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';

type Field = 'username' | 'password' | 'confirmPassword';

const USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/;

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [FormsModule, RouterLink],
  templateUrl: './register.component.html',
  styleUrl: './register.component.css',
})
export class RegisterComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  username = signal('');
  password = signal('');
  confirmPassword = signal('');

  submitting = signal(false);
  errorMessage = signal<string | null>(null);
  private touched = signal<Record<Field, boolean>>({
    username: false,
    password: false,
    confirmPassword: false,
  });

  usernameError = computed(() => {
    const value = this.username().trim();
    if (!value) return 'Perdoruesi eshte i detyrueshem.';
    if (value.length < 3 || value.length > 50) return 'Perdoruesi duhet te kete 3-50 karaktere.';
    if (!USERNAME_PATTERN.test(value)) {
      return 'Lejohen vetem shkronja, numra, pike, vize dhe nenvize.';
    }
    return null;
  });

  passwordError = computed(() => {
    const value = this.password();
    if (!value) return 'Fjalekalimi eshte i detyrueshem.';
    if (value.length < 8) return 'Fjalekalimi duhet te kete te pakten 8 karaktere.';
    if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
      return 'Duhet te permbaje te pakten nje shkronje dhe nje numer.';
    }
    return null;
  });

  confirmPasswordError = computed(() => {
    const value = this.confirmPassword();
    if (!value) return 'Konfirmoni fjalekalimin.';
    if (value !== this.password()) return 'Fjalekalimet nuk perputhen.';
    return null;
  });

  formValid = computed(
    () => !this.usernameError() && !this.passwordError() && !this.confirmPasswordError(),
  );

  isTouched(field: Field): boolean {
    return this.touched()[field];
  }

  markTouched(field: Field): void {
    this.touched.update((state) => ({ ...state, [field]: true }));
  }

  submit(): void {
    if (this.submitting()) return;

    this.touched.set({ username: true, password: true, confirmPassword: true });
    this.errorMessage.set(null);

    if (!this.formValid()) return;

    this.submitting.set(true);

    this.auth
      .register({
        username: this.username().trim(),
        password: this.password(),
        confirmPassword: this.confirmPassword(),
      })
      .subscribe({
        next: () => {
          this.submitting.set(false);
          this.router.navigate(['/overview']);
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
    return 'Rregjistrimi deshtoi. Provoni perseri.';
  }
}
