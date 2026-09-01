import { HttpErrorResponse, HttpInterceptorFn, HttpRequest } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, switchMap, throwError } from 'rxjs';
import { AuthService } from '../services/auth.service';

const PUBLIC_ENDPOINTS = ['/api/auth/login', '/api/auth/refresh', '/api/auth/logout'];
const CREDENTIALED_PREFIX = '/api/auth';

export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const auth = inject(AuthService);
  const isPublic = PUBLIC_ENDPOINTS.some((endpoint) => request.url.includes(endpoint));

  const prepare = (source: HttpRequest<unknown>, token: string | null) => {
    const headers = token && !isPublic ? { Authorization: `Bearer ${token}` } : undefined;

    return source.clone({
      ...(headers ? { setHeaders: headers } : {}),
      withCredentials: source.url.includes(CREDENTIALED_PREFIX),
    });
  };

  return next(prepare(request, auth.token())).pipe(
    catchError((error: HttpErrorResponse) => {
      if (error.status !== 401 || isPublic) {
        return throwError(() => error);
      }

      return auth.refreshAccessToken().pipe(
        switchMap((token) => next(prepare(request, token))),
        catchError((refreshError) => {
          auth.forceLogout();
          return throwError(() => refreshError);
        }),
      );
    }),
  );
};
