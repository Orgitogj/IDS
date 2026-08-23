import { Component, OnInit, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { ModelService } from '../../core/services/model.service';
import { MLModel } from '../../core/models/ml-model.model';

@Component({
  selector: 'app-models',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './models.component.html',
  styleUrl: './models.component.css',
})
export class ModelsComponent implements OnInit {
  private modelService = inject(ModelService);

  models = signal<MLModel[]>([]);
  loading = signal(true);
  activating = signal<string | null>(null);

  ngOnInit(): void {
    this.loadModels();
  }

  loadModels(): void {
    this.modelService.getAll().subscribe((models) => {
      this.models.set(models.sort((a, b) => +new Date(b.trainedAt) - +new Date(a.trainedAt)));
      this.loading.set(false);
    });
  }

  activate(model: MLModel): void {
    this.activating.set(model.id);
    this.modelService.setActive(model.id).subscribe({
      next: () => {
        this.loadModels();
        this.activating.set(null);
      },
      error: () => this.activating.set(null),
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
