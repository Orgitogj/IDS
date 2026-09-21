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
      error: (error: { status?: number }) => {
        this.submitting.set(false);
        this.errorMessage.set(
          error.status === 401
            ? 'Përdoruesi ose fjalëkalimi është i pasaktë.'
            : 'Serveri nuk përgjigjet. Kontrolloni nëse është i ndezur (localhost:8080).',
        );
      },
    });
  }
}
