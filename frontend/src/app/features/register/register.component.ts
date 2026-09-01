import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UserRole } from '../../core/models/auth.model';
import { UserService } from '../../core/services/user.service';

type Field = 'username' | 'password' | 'confirmPassword';

const USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/;

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './register.component.html',
  styleUrl: './register.component.css',
})
export class RegisterComponent {
  private userService = inject(UserService);

  readonly roles: UserRole[] = ['ANALYST', 'ADMIN', 'SERVICE'];

  username = signal('');
  password = signal('');
  confirmPassword = signal('');
  role = signal<UserRole>('ANALYST');

  submitting = signal(false);
  errorMessage = signal<string | null>(null);
  successMessage = signal<string | null>(null);
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
    this.successMessage.set(null);

    if (!this.formValid()) return;

    this.submitting.set(true);

    this.userService
      .create({
        username: this.username().trim(),
        password: this.password(),
        confirmPassword: this.confirmPassword(),
        role: this.role(),
      })
      .subscribe({
        next: (user) => {
          this.submitting.set(false);
          this.successMessage.set(`Perdoruesi '${user.username}' u krijua si ${user.role}.`);
          this.reset();
        },
        error: (error: { status?: number; error?: { message?: string } }) => {
          this.submitting.set(false);
          this.errorMessage.set(this.describe(error));
        },
      });
  }

  private reset(): void {
    this.username.set('');
    this.password.set('');
    this.confirmPassword.set('');
    this.role.set('ANALYST');
    this.touched.set({ username: false, password: false, confirmPassword: false });
  }

  private describe(error: { status?: number; error?: { message?: string } }): string {
    if (error.status === 0) return 'Lidhja me serverin deshtoi. Kontrollo localhost:8080.';
    if (error.status === 403) return 'Vetem nje administrator mund te krijoje perdorues.';
    if (error.error?.message) return error.error.message;
    return 'Krijimi i perdoruesit deshtoi. Provoni perseri.';
  }
}
