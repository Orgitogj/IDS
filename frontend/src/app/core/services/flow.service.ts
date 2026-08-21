import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { NetworkFlow } from '../models/network-flow.model';

const BASE_URL = 'http://localhost:8080/api/flows';

@Injectable({ providedIn: 'root' })
export class FlowService {
  private http = inject(HttpClient);

  getAll(): Observable<NetworkFlow[]> {
    return this.http.get<NetworkFlow[]>(BASE_URL);
  }

  getById(id: string): Observable<NetworkFlow> {
    return this.http.get<NetworkFlow>(`${BASE_URL}/${id}`);
  }
}
