import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { SeverityThresholds } from '../models/severity-thresholds.model';

const BASE_URL = 'http://localhost:8080/api/settings';

@Injectable({ providedIn: 'root' })
export class SettingsService {
  private http = inject(HttpClient);

  getThresholds(): Observable<SeverityThresholds> {
    return this.http.get<SeverityThresholds>(`${BASE_URL}/thresholds`);
  }

  updateThresholds(
    criticalMin: number,
    highMin: number,
    mediumMin: number,
  ): Observable<SeverityThresholds> {
    return this.http.put<SeverityThresholds>(`${BASE_URL}/thresholds`, {
      criticalMin,
      highMin,
      mediumMin,
    });
  }
}
