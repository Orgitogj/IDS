import { signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { RouterTestingHarness } from '@angular/router/testing';
import { App } from './app';
import { routes } from './app.routes';
import { AuthService } from './core/services/auth.service';
import { LoginComponent } from './features/login/login.component';

function configure(authenticated: boolean, admin = false) {
  TestBed.configureTestingModule({
    imports: [App],
    providers: [
      provideRouter(routes),
      {
        provide: AuthService,
        useValue: { isAuthenticated: signal(authenticated), isAdmin: signal(admin) },
      },
    ],
  });
}

describe('App', () => {
  it('should create the app', () => {
    configure(false);
    const fixture = TestBed.createComponent(App);
    expect(fixture.componentInstance).toBeTruthy();
  });

  it('should render only a router outlet at the root', () => {
    configure(false);
    const fixture = TestBed.createComponent(App);
    fixture.detectChanges();
    const root: HTMLElement = fixture.nativeElement;
    expect(root.children.length).toBe(1);
    expect(root.querySelector('router-outlet')).toBeTruthy();
  });

  it('should send an unauthenticated visitor to the login page', async () => {
    configure(false);
    const harness = await RouterTestingHarness.create();
    const page = await harness.navigateByUrl('/');
    expect(TestBed.inject(Router).url).toBe('/login');
    expect(page).toBeInstanceOf(LoginComponent);
  });

  it('should open the overview for an authenticated user', async () => {
    configure(true);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/');
    expect(router.url).toBe('/overview');
  });

  it('should keep a non-admin user out of admin pages', async () => {
    configure(true, false);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/settings');
    expect(router.url).toBe('/overview');
  });

  it('should let an admin open admin pages', async () => {
    configure(true, true);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/settings');
    expect(router.url).toBe('/settings');
  });
});
