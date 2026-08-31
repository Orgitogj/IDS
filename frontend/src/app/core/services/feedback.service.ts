import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { AnalystFeedback, FeedbackStats } from '../models/feedback.model';
import { PageResponse } from '../models/page-response.model';

const BASE_URL = 'http://localhost:8080/api/feedback';

@Injectable({ providedIn: 'root' })
export class FeedbackService {
  private http = inject(HttpClient);

  getPage(page: number, size: number): Observable<PageResponse<AnalystFeedback>> {
    const params = new HttpParams().set('page', page).set('size', size);
    return this.http.get<PageResponse<AnalystFeedback>>(BASE_URL, { params });
  }

  getStats(): Observable<FeedbackStats> {
    return this.http.get<FeedbackStats>(`${BASE_URL}/stats`);
  }
}
