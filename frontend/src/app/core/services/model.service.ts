import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { Observable, tap } from 'rxjs';
import { MLModel } from '../models/ml-model.model';

const BASE_URL = 'http://localhost:8080/api/models';

@Injectable({ providedIn: 'root' })
export class ModelService {
  private http = inject(HttpClient);

  readonly activeModelId = signal<string | null>(null);

  getAll(): Observable<MLModel[]> {
    return this.http.get<MLModel[]>(BASE_URL);
  }

  getActive(): Observable<MLModel> {
    return this.http.get<MLModel>(`${BASE_URL}/active`);
  }

  refreshActive(): void {
    this.getActive().subscribe({
      next: (model) => this.activeModelId.set(model.id),
      error: () => this.activeModelId.set(null),
    });
  }

  getById(id: string): Observable<MLModel> {
    return this.http.get<MLModel>(`${BASE_URL}/${id}`);
  }

  setActive(id: string): Observable<MLModel> {
    return this.http
      .patch<MLModel>(`${BASE_URL}/${id}/activate`, {})
      .pipe(tap((model) => this.activeModelId.set(model.id)));
  }
}
