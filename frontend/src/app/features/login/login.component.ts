import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { AuthService } from '../../core/services/auth.service';

@Component({
  selector: 'app-login',
  standalone: true,
  imports: [FormsModule],
  templateUrl: './login.component.html',
  styleUrl: './login.component.css',
})
export class LoginComponent {
  private auth = inject(AuthService);
  private router = inject(Router);

  username = signal('');
  password = signal('');
  submitting = signal(false);
  errorMessage = signal<string | null>(null);

  submit(): void {
    if (this.submitting()) return;

    const username = this.username().trim();
    const password = this.password();

    if (!username || !password) {
      this.errorMessage.set('Shkruani përdoruesin dhe fjalëkalimin.');
      return;
    }

    this.submitting.set(true);
    this.errorMessage.set(null);

    this.auth.login(username, password).subscribe({
      next: () => {
        this.submitting.set(false);
        this.router.navigate(['/overview']);
      },
      error: (error: { status?: number; error?: { message?: string } }) => {
        this.submitting.set(false);
        this.errorMessage.set(this.messageFor(error));
      },
    });
  }

  private messageFor(error: { status?: number; error?: { message?: string } }): string {
    if (error.status === 401) return 'Përdoruesi ose fjalëkalimi është i pasaktë.';
    if (error.status === 429) {
      return error.error?.message ?? 'Shumë tentativa të dështuara. Provoni përsëri më vonë.';
    }
    if (error.status === 0) return 'Serveri nuk përgjigjet. Kontrolloni nëse është i ndezur (localhost:8080).';
    return 'Hyrja dështoi. Provoni përsëri.';
  }
}
