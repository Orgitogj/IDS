import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'overview', pathMatch: 'full' },
  {
    path: 'overview',
    loadComponent: () =>
      import('./features/overview/overview.component').then((m) => m.OverviewComponent),
  },
  {
    path: 'alarms',
    loadComponent: () =>
      import('./features/alarms/alarms.component').then((m) => m.AlarmsComponent),
  },
  {
    path: 'experiments',
    loadComponent: () =>
      import('./features/experiments/experiments.component').then((m) => m.ExperimentsComponent),
  },
  { path: '**', redirectTo: 'overview' },
];
