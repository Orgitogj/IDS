import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { ExperimentResult } from '../models/experiment-result.model';

const BASE_URL = 'http://localhost:8080/api/experiments';

@Injectable({ providedIn: 'root' })
export class ExperimentService {
  private http = inject(HttpClient);

  getAll(modelId?: string): Observable<ExperimentResult[]> {
    const url = modelId ? `${BASE_URL}?modelId=${modelId}` : BASE_URL;
    return this.http.get<ExperimentResult[]>(url);
  }

  getById(id: string): Observable<ExperimentResult> {
    return this.http.get<ExperimentResult>(`${BASE_URL}/${id}`);
  }
}
