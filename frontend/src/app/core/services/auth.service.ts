import { HttpClient } from '@angular/common/http';
import { Injectable, computed, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Observable, catchError, finalize, map, of, shareReplay, switchMap, tap, throwError } from 'rxjs';
import { ChangePasswordRequest, CurrentUser, LoginResponse } from '../models/auth.model';

const BASE_URL = 'http://localhost:8080/api/auth';
const REFRESH_MARGIN_SECONDS = 60;
const MIN_REFRESH_DELAY_MS = 15_000;

@Injectable({ providedIn: 'root' })
export class AuthService {
  private http = inject(HttpClient);
  private router = inject(Router);

  private tokenSignal = signal<string | null>(null);
  private userSignal = signal<CurrentUser | null>(null);
  private refreshInFlight: Observable<string> | null = null;
  private refreshTimer: ReturnType<typeof setTimeout> | null = null;

  token = this.tokenSignal.asReadonly();
  currentUser = this.userSignal.asReadonly();
  username = computed(() => this.userSignal()?.username ?? null);
  role = computed(() => this.userSignal()?.role ?? null);
  isAuthenticated = computed(() => this.tokenSignal() !== null && this.userSignal() !== null);
  isAdmin = computed(() => this.role() === 'ADMIN');

  login(username: string, password: string): Observable<CurrentUser> {
    return this.http
      .post<LoginResponse>(
        `${BASE_URL}/login`,
        { username, password },
        { withCredentials: true },
      )
      .pipe(
        tap((response) => this.applySession(response)),
        switchMap(() => this.loadCurrentUser()),
      );
  }

  restoreSession(): Observable<CurrentUser | null> {
    return this.refreshAccessToken().pipe(
      switchMap(() => this.loadCurrentUser()),
      catchError(() => {
        this.clearSession();
        return of(null);
      }),
    );
  }

  refreshAccessToken(): Observable<string> {
    if (!this.refreshInFlight) {
      this.refreshInFlight = this.http
        .post<LoginResponse>(`${BASE_URL}/refresh`, {}, { withCredentials: true })
        .pipe(
          tap((response) => this.applySession(response)),
          map((response) => response.token),
          finalize(() => {
            this.refreshInFlight = null;
          }),
          shareReplay({ bufferSize: 1, refCount: false }),
        );
    }

    return this.refreshInFlight;
  }

  loadCurrentUser(): Observable<CurrentUser> {
    return this.http
      .get<CurrentUser>(`${BASE_URL}/me`)
      .pipe(tap((user) => this.userSignal.set(user)));
  }

  changePassword(payload: ChangePasswordRequest): Observable<void> {
    return this.http
      .post<void>(`${BASE_URL}/password`, payload, { withCredentials: true })
      .pipe(catchError((error) => throwError(() => error)));
  }

  logout(): void {
    this.http
      .post<void>(`${BASE_URL}/logout`, {}, { withCredentials: true })
      .subscribe({
        next: () => this.finishLogout(),
        error: () => this.finishLogout(),
      });
  }

  forceLogout(): void {
    this.finishLogout();
  }

  private finishLogout(): void {
    this.clearSession();
    this.router.navigate(['/login']);
  }

  private clearSession(): void {
    this.cancelScheduledRefresh();
    this.tokenSignal.set(null);
    this.userSignal.set(null);
  }

  private applySession(response: LoginResponse): void {
    this.tokenSignal.set(response.token);
    this.scheduleRefresh(response.expiresInSeconds);
  }

  private scheduleRefresh(expiresInSeconds: number): void {
    this.cancelScheduledRefresh();

    const delay = Math.max(
      (expiresInSeconds - REFRESH_MARGIN_SECONDS) * 1000,
      MIN_REFRESH_DELAY_MS,
    );

    this.refreshTimer = setTimeout(() => {
      this.refreshAccessToken().subscribe({ error: () => this.forceLogout() });
    }, delay);
  }

  private cancelScheduledRefresh(): void {
    if (this.refreshTimer !== null) {
      clearTimeout(this.refreshTimer);
      this.refreshTimer = null;
    }
  }
}
