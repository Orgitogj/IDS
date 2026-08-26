import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';
import { LoginResponse, RegisterRequest } from '../models/auth.model';

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
  role = computed(() => this.decodeRole(this.tokenSignal()));
  isAdmin = computed(() => this.role() === 'ADMIN');

  login(username: string, password: string): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`${BASE_URL}/login`, { username, password })
      .pipe(tap((response) => this.persist(response)));
  }

  register(payload: RegisterRequest): Observable<LoginResponse> {
    return this.http
      .post<LoginResponse>(`${BASE_URL}/register`, payload)
      .pipe(tap((response) => this.persist(response)));
  }

  logout(): void {
    this.clear(TOKEN_KEY);
    this.clear(USER_KEY);
    this.tokenSignal.set(null);
    this.usernameSignal.set(null);
    this.router.navigate(['/login']);
  }

  private persist(response: LoginResponse): void {
    this.store(TOKEN_KEY, response.token);
    this.store(USER_KEY, response.username);
    this.tokenSignal.set(response.token);
    this.usernameSignal.set(response.username);
  }

  private decodeRole(token: string | null): string | null {
    if (!token) return null;

    try {
      const payload = token.split('.')[1];
      if (!payload) return null;

      const base64 = payload.replace(/-/g, '+').replace(/_/g, '/');
      const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=');

      return JSON.parse(atob(padded)).role ?? null;
    } catch {
      return null;
    }
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
