import { Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { UserRole } from '../../core/models/auth.model';
import { UserService } from '../../core/services/user.service';
import { LabelPipe, label } from '../../shared/pipes/label.pipe';

type Field = 'username' | 'password' | 'confirmPassword';

const USERNAME_PATTERN = /^[A-Za-z0-9._-]+$/;

@Component({
  selector: 'app-register',
  standalone: true,
  imports: [FormsModule, LabelPipe],
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
    if (!value) return 'Përdoruesi është i detyrueshëm.';
    if (value.length < 3 || value.length > 50) return 'Përdoruesi duhet të ketë 3–50 karaktere.';
    if (!USERNAME_PATTERN.test(value)) {
      return 'Lejohen vetëm shkronja, numra, pika, viza dhe nënviza.';
    }
    return null;
  });

  passwordError = computed(() => {
    const value = this.password();
    if (!value) return 'Fjalëkalimi është i detyrueshëm.';
    if (value.length < 8) return 'Fjalëkalimi duhet të ketë të paktën 8 karaktere.';
    if (!/[A-Za-z]/.test(value) || !/\d/.test(value)) {
      return 'Duhet të përmbajë të paktën një shkronjë dhe një numër.';
    }
    return null;
  });

  confirmPasswordError = computed(() => {
    const value = this.confirmPassword();
    if (!value) return 'Konfirmoni fjalëkalimin.';
    if (value !== this.password()) return 'Fjalëkalimet nuk përputhen.';
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
          this.successMessage.set(`Përdoruesi „${user.username}“ u krijua me rolin ${label('role', user.role)}.`);
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
    if (error.status === 0) return 'Serveri nuk përgjigjet. Kontrolloni nëse është i ndezur (localhost:8080).';
    if (error.status === 403) return 'Vetëm administratori mund të krijojë përdorues.';
    if (error.error?.message) return error.error.message;
    return 'Përdoruesi nuk u krijua. Provoni përsëri.';
  }
}
