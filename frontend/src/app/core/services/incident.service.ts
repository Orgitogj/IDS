import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { Alarm, AlarmSeverity, AlarmStatus } from '../models/alarm.model';
import { Incident } from '../models/incident.model';
import { PageResponse } from '../models/page-response.model';

const BASE_URL = 'http://localhost:8080/api/incidents';

@Injectable({ providedIn: 'root' })
export class IncidentService {
  private http = inject(HttpClient);

  getPage(
    page: number,
    size: number,
    severity: AlarmSeverity | null = null,
    status: AlarmStatus | null = null,
    search = '',
  ): Observable<PageResponse<Incident>> {
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

    return this.http.get<PageResponse<Incident>>(BASE_URL, { params });
  }

  getById(id: string): Observable<Incident> {
    return this.http.get<Incident>(`${BASE_URL}/${id}`);
  }

  getAlarms(id: string): Observable<Alarm[]> {
    return this.http.get<Alarm[]>(`${BASE_URL}/${id}/alarms`);
  }

  updateStatus(id: string, status: AlarmStatus): Observable<Incident> {
    return this.http.patch<Incident>(`${BASE_URL}/${id}/status`, { status });
  }
}
