import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';
import { RegisterRequest, UserResponse } from '../models/auth.model';

const USERS_URL = 'http://localhost:8080/api/users';
const REGISTER_URL = 'http://localhost:8080/api/auth/register';

@Injectable({ providedIn: 'root' })
export class UserService {
  private http = inject(HttpClient);

  list(): Observable<UserResponse[]> {
    return this.http.get<UserResponse[]>(USERS_URL);
  }

  create(payload: RegisterRequest): Observable<UserResponse> {
    return this.http.post<UserResponse>(REGISTER_URL, payload);
  }

  setEnabled(id: string, enabled: boolean): Observable<UserResponse> {
    return this.http.patch<UserResponse>(`${USERS_URL}/${id}/enabled`, { enabled });
  }

  unlock(id: string): Observable<UserResponse> {
    return this.http.patch<UserResponse>(`${USERS_URL}/${id}/unlock`, {});
  }
}
