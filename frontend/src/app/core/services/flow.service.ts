import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { NetworkFlow, FlowLabel } from '../models/network-flow.model';
import { PageResponse } from '../models/page-response.model';
import { FlowStats } from '../models/flow-stats.model';

const BASE_URL = 'http://localhost:8080/api/flows';

@Injectable({ providedIn: 'root' })
export class FlowService {
  private http = inject(HttpClient);

  getPage(
    page: number,
    size: number,
    predictedLabel: FlowLabel | null = null,
    search = '',
  ): Observable<PageResponse<NetworkFlow>> {
    let params = new HttpParams().set('page', page).set('size', size);

    if (predictedLabel) {
      params = params.set('predictedLabel', predictedLabel);
    }
    if (search) {
      params = params.set('search', search);
    }

    return this.http.get<PageResponse<NetworkFlow>>(BASE_URL, { params });
  }

  getStats(): Observable<FlowStats> {
    return this.http.get<FlowStats>(`${BASE_URL}/stats`);
  }

  getById(id: string): Observable<NetworkFlow> {
    return this.http.get<NetworkFlow>(`${BASE_URL}/${id}`);
  }
}
