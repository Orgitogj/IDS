import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { MLModel } from '../models/ml-model.model';

const BASE_URL = 'http://localhost:8080/api/models';

@Injectable({ providedIn: 'root' })
export class ModelService {
  private http = inject(HttpClient);

  getAll(): Observable<MLModel[]> {
    return this.http.get<MLModel[]>(BASE_URL);
  }

  getById(id: string): Observable<MLModel> {
    return this.http.get<MLModel>(`${BASE_URL}/${id}`);
  }

  setActive(id: string): Observable<MLModel> {
    return this.http.patch<MLModel>(`${BASE_URL}/${id}/activate`, {});
  }
}
