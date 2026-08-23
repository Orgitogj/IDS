import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { LoginResponse } from '../models/auth.model';

const BASE_URL = 'http://localhost:8080/api/auth';
const TOKEN_KEY = 'ids_token';
const USER_KEY = 'ids_user';

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private tokenSignal = signal<string | null>(this.readStored(TOKEN_KEY));
  private usernameSignal = signal<string | null>(this.readStored(USER_KEY));

  token = this.tokenSignal.asReadonly();
  username = this.usernameSignal.asReadonly();
  isAuthenticated = computed(() => this.tokenSignal() !== null);

  login(username: string, password: string): Observable<LoginResponse> {
    return this.http.post<LoginResponse>(`${BASE_URL}/login`, { username, password }).pipe(
      tap((response) => {
        this.store(TOKEN_KEY, response.token);
        this.store(USER_KEY, response.username);
        this.tokenSignal.set(response.token);
        this.usernameSignal.set(response.username);
      }),
    );
  }

  logout(): void {
    this.clear(TOKEN_KEY);
    this.clear(USER_KEY);
    this.tokenSignal.set(null);
    this.usernameSignal.set(null);
    this.router.navigate(['/login']);
  }

  private readStored(key: string): string | null {
    try {
      return localStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private store(key: string, value: string): void {
    try {
      localStorage.setItem(key, value);
    } catch {
      return;
    }
  }

  private clear(key: string): void {
    try {
      localStorage.removeItem(key);
    } catch {
      return;
    }
  }
}
