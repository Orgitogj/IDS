import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Alarm, AlarmStatus, AlarmSeverity } from '../models/alarm.model';
import { PageResponse } from '../models/page-response.model';
import { AlarmStats } from '../models/alarm-stats.model';
import { AlarmGroup } from '../models/alarm-group.model';
import { Explanation, ExplanationRating } from '../models/explanation.model';

const BASE_URL = 'http://localhost:8080/api/alarms';

@Injectable({ providedIn: 'root' })
export class AlarmService {
  private http = inject(HttpClient);

  getPage(
    page: number,
    size: number,
    severity: AlarmSeverity | null = null,
    status: AlarmStatus | null = null,
    search = '',
  ): Observable<PageResponse<Alarm>> {
    let params = new HttpParams().set('page', page).set('size', size);

    if (severity) {
      params = params.set('severity', severity);
    }
    if (status) {
      params = params.set('status', status);
    }
    if (search) {
      params = params.set('search', search);
    }

    return this.http.get<PageResponse<Alarm>>(BASE_URL, { params });
  }

  getStats(): Observable<AlarmStats> {
    return this.http.get<AlarmStats>(`${BASE_URL}/stats`);
  }

  getAlarmGroups(limit = 50): Observable<AlarmGroup[]> {
    const params = new HttpParams().set('limit', limit);
    return this.http.get<AlarmGroup[]>(`${BASE_URL}/incidents`, { params });
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
