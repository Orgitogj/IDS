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
    path: 'flows',
    loadComponent: () => import('./features/flows/flows.component').then((m) => m.FlowsComponent),
  },
  {
    path: 'experiments',
    loadComponent: () =>
      import('./features/experiments/experiments.component').then((m) => m.ExperimentsComponent),
  },
  {
    path: 'models',
    loadComponent: () =>
      import('./features/models/models.component').then((m) => m.ModelsComponent),
  },
  {
    path: 'settings',
    loadComponent: () =>
      import('./features/settings/settings.component').then((m) => m.SettingsComponent),
  },
  { path: '**', redirectTo: 'overview' },
];
