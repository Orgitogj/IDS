import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { AuthService } from '../../core/services/auth.service';
import { ModelService } from '../../core/services/model.service';
import { MLModel } from '../../core/models/ml-model.model';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-models',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './models.component.html',
  styleUrl: './models.component.css',
})
export class ModelsComponent implements OnInit {
  private modelService = inject(ModelService);
  private toast = inject(ToastService);

  isAdmin = inject(AuthService).isAdmin;

  models = signal<MLModel[]>([]);
  loading = signal(true);
  loadError = signal(false);
  activating = signal<string | null>(null);

  ngOnInit(): void {
    this.loadModels();
  }

  loadModels(): void {
    this.modelService.getAll().subscribe({
      next: (models) => {
        this.models.set(models.sort((a, b) => +new Date(b.trainedAt) - +new Date(a.trainedAt)));
        this.loading.set(false);
        this.loadError.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadError.set(true);
        this.toast.backendError('models');
      },
    });
  }

  activate(model: MLModel): void {
    if (!this.isAdmin()) return;

    this.activating.set(model.id);
    this.modelService.setActive(model.id).subscribe({
      next: () => {
        this.loadModels();
        this.activating.set(null);
      },
      error: () => {
        this.activating.set(null);
        this.toast.show(
          'Aktivizimi deshtoi',
          `Modeli ${model.name} nuk u aktivizua.`,
          'critical',
        );
      },
    });
  }

  algorithmColor(algorithm: string): string {
    const map: Record<string, string> = {
      XGBoost: 'bg-[var(--color-primary)]',
      RandomForest: 'bg-[var(--color-high)]',
      IsolationForest: 'bg-[var(--color-medium)]',
      NeuralNetwork: 'bg-[var(--color-low)]',
    };
    return map[algorithm] ?? 'bg-[var(--color-text-muted)]';
  }
}
