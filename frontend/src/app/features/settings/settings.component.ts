import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe } from '@angular/common';
import { AuthService } from '../../core/services/auth.service';
import { SettingsService } from '../../core/services/settings.service';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-settings',
  standalone: true,
  imports: [FormsModule, DatePipe],
  templateUrl: './settings.component.html',
  styleUrl: './settings.component.css',
})
export class SettingsComponent implements OnInit {
  private settingsService = inject(SettingsService);
  private toast = inject(ToastService);

  isAdmin = inject(AuthService).isAdmin;

  criticalMin = signal(0.95);
  highMin = signal(0.85);
  mediumMin = signal(0.7);
  updatedAt = signal<string | null>(null);

  loading = signal(true);
  loadError = signal(false);
  saving = signal(false);

  validationError = computed(() => {
    const critical = this.criticalMin();
    const high = this.highMin();
    const medium = this.mediumMin();

    for (const value of [critical, high, medium]) {
      if (value === null || value === undefined || isNaN(value)) {
        return 'Të gjitha pragjet duhet të jenë numra.';
      }
      if (value < 0 || value > 1) {
        return 'Pragjet duhet të jenë ndërmjet 0 dhe 1.';
      }
    }

    if (!(critical > high && high > medium)) {
      return 'Pragjet duhet të jenë në rend zbritës: Kritik > I lartë > Mesatar.';
    }
    return null;
  });

  endpoints = [
    { name: 'API e Spring Boot', url: 'http://localhost:8080/api' },
    { name: 'WebSocket i Spring Boot', url: 'ws://localhost:8080/ws' },
    { name: 'Shërbimi ML (Python)', url: 'http://localhost:8000/api' },
    { name: 'PostgreSQL (Docker)', url: 'localhost:5433 / IDS' },
  ];

  stack = [
    { layer: 'Serveri', tech: 'Spring Boot 3.3, Java 17, PostgreSQL, Flyway, WebSocket (STOMP)' },
    { layer: 'Shërbimi ML', tech: 'Python 3.11, FastAPI, XGBoost, scikit-learn, SHAP' },
    { layer: 'Ndërfaqja e përdoruesit', tech: 'Angular, Tailwind CSS v4, Chart.js' },
    { layer: 'Shpjegimet me LLM', tech: 'Claude Sonnet 5' },
  ];

  ngOnInit(): void {
    this.settingsService.getThresholds().subscribe({
      next: (thresholds) => {
        this.criticalMin.set(thresholds.criticalMin);
        this.highMin.set(thresholds.highMin);
        this.mediumMin.set(thresholds.mediumMin);
        this.updatedAt.set(thresholds.updatedAt);
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadError.set(true);
        this.toast.backendError('settings');
      },
    });
  }

  save(): void {
    if (!this.isAdmin() || this.validationError() || this.saving()) return;

    this.saving.set(true);
    this.settingsService
      .updateThresholds(this.criticalMin(), this.highMin(), this.mediumMin())
      .subscribe({
        next: (thresholds) => {
          this.updatedAt.set(thresholds.updatedAt);
          this.saving.set(false);
          this.toast.show(
            'Pragjet u ruajtën',
            'Alarmet e reja do të përdorin këto vlera.',
            'low',
          );
        },
        error: () => {
          this.saving.set(false);
          this.toast.show('Ruajtja dështoi', 'Pragjet mbetën siç ishin.', 'critical');
        },
      });
  }
}
