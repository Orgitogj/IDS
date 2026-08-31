import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { DriftReport } from '../models/drift.model';
import { PageResponse } from '../models/page-response.model';

const BASE_URL = 'http://localhost:8080/api/drift';

@Injectable({ providedIn: 'root' })
export class DriftService {
  private http = inject(HttpClient);

  getStatus(): Observable<DriftReport | null> {
    return this.http.get<DriftReport | null>(`${BASE_URL}/status`);
  }

  getHistory(page: number, size: number): Observable<PageResponse<DriftReport>> {
    const params = new HttpParams().set('page', page).set('size', size);
    return this.http.get<PageResponse<DriftReport>>(`${BASE_URL}/history`, { params });
  }
}
