import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Alarm, AlarmStatus } from '../models/alarm.model';
import { Explanation, ExplanationRating } from '../models/explanation.model';

const BASE_URL = 'http://localhost:8080/api/alarms';

@Injectable({ providedIn: 'root' })
export class AlarmService {
  private http = inject(HttpClient);

  getAll(status?: AlarmStatus): Observable<Alarm[]> {
    const url = status ? `${BASE_URL}?status=${status}` : BASE_URL;
    return this.http.get<Alarm[]>(url);
  }

  getById(id: string): Observable<Alarm> {
    return this.http.get<Alarm>(`${BASE_URL}/${id}`);
  }

  updateStatus(id: string, status: AlarmStatus): Observable<Alarm> {
    return this.http.patch<Alarm>(`${BASE_URL}/${id}/status`, { status });
  }

  getExplanations(alarmId: string): Observable<Explanation[]> {
    return this.http.get<Explanation[]>(`${BASE_URL}/${alarmId}/explanations`);
  }

  rateExplanation(
    alarmId: string,
    explanationId: string,
    rating: ExplanationRating,
  ): Observable<Explanation> {
    return this.http.patch<Explanation>(
      `${BASE_URL}/${alarmId}/explanations/${explanationId}/rating`,
      { rating },
    );
  }
}
