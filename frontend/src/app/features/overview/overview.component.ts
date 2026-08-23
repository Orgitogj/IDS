import { Component, OnInit, effect, inject, signal, computed } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration } from 'chart.js';
import { AlarmService } from '../../core/services/alarm.service';
import { FlowService } from '../../core/services/flow.service';
import { ModelService } from '../../core/services/model.service';
import { ExperimentService } from '../../core/services/experiment.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { Alarm } from '../../core/models/alarm.model';
import { FlowStats } from '../../core/models/flow-stats.model';
import { AlarmStats } from '../../core/models/alarm-stats.model';
import { MLModel } from '../../core/models/ml-model.model';
import { ExperimentResult } from '../../core/models/experiment-result.model';
import { ToastService } from '../../core/services/toast.service';

const AXIS_COLOR = '#8b93b8';
const GRID_COLOR = '#1d2440';

@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [BaseChartDirective, DatePipe, DecimalPipe],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.css',
})
export class OverviewComponent implements OnInit {
  private alarmService = inject(AlarmService);
  private flowService = inject(FlowService);
  private modelService = inject(ModelService);
  private experimentService = inject(ExperimentService);
  private ws = inject(WebSocketService);
  private toast = inject(ToastService);

  loading = signal(true);
  loadError = signal(false);
  activeModel = signal<MLModel | null>(null);

  private alarms = signal<Alarm[]>([]);
  private flowStats = signal<FlowStats | null>(null);
  private experiments = signal<ExperimentResult[]>([]);

  totalFlows = computed(() => this.flowStats()?.totalFlows ?? 0);
  private alarmStats = signal<AlarmStats | null>(null);

  totalAlarms = computed(() => this.alarmStats()?.totalAlarms ?? 0);
  newAlarms = computed(() => this.alarmStats()?.statusCounts?.['NEW'] ?? 0);
  criticalAlarms = computed(() => this.alarmStats()?.severityCounts?.['CRITICAL'] ?? 0);
  falsePositives = computed(() => this.alarmStats()?.statusCounts?.['FALSE_POSITIVE'] ?? 0);

  reviewedAlarms = computed(() => {
    const counts = this.alarmStats()?.statusCounts ?? {};
    return (counts['FALSE_POSITIVE'] ?? 0) + (counts['CONFIRMED'] ?? 0) + (counts['RESOLVED'] ?? 0);
  });

  falsePositiveRate = computed(() => {
    const reviewed = this.reviewedAlarms();
    return reviewed === 0 ? 0 : (this.falsePositives() / reviewed) * 100;
  });

  recentAlarms = computed(() =>
    [...this.alarms()].sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt)).slice(0, 6),
  );

  timelineChartData = computed<ChartConfiguration<'line'>['data']>(() => {
    const hourly = this.alarmStats()?.hourlyCounts ?? [];
    const sortedKeys = hourly.map((h) => h.hour);
    const buckets = new Map(hourly.map((h) => [h.hour, h.count]));
    return {
      labels: sortedKeys.map((k) => `${new Date(k).getHours()}:00`),
      datasets: [
        {
          label: 'Alarme',
          data: sortedKeys.map((k) => buckets.get(k) ?? 0),
          borderColor: '#6366f1',
          backgroundColor: 'rgba(99, 102, 241, 0.15)',
          fill: true,
          tension: 0.35,
          pointRadius: 2,
          pointBackgroundColor: '#6366f1',
        },
      ],
    };
  });

  timelineChartOptions: ChartConfiguration<'line'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: AXIS_COLOR, font: { size: 10 } }, grid: { color: GRID_COLOR } },
      y: {
        beginAtZero: true,
        ticks: { color: AXIS_COLOR, precision: 0 },
        grid: { color: GRID_COLOR },
      },
    },
  };

  severityChartData = computed<ChartConfiguration<'doughnut'>['data']>(() => {
    const source = this.alarmStats()?.severityCounts ?? {};
    const counts: Record<string, number> = {
      CRITICAL: source['CRITICAL'] ?? 0,
      HIGH: source['HIGH'] ?? 0,
      MEDIUM: source['MEDIUM'] ?? 0,
      LOW: source['LOW'] ?? 0,
    };
    return {
      labels: ['Critical', 'High', 'Medium', 'Low'],
      datasets: [
        {
          data: [counts['CRITICAL'], counts['HIGH'], counts['MEDIUM'], counts['LOW']],
          backgroundColor: ['#ef4444', '#f97316', '#eab308', '#22c55e'],
          borderColor: '#12172a',
          borderWidth: 2,
        },
      ],
    };
  });

  severityChartOptions: ChartConfiguration<'doughnut'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    cutout: '70%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: {
          color: AXIS_COLOR,
          font: { size: 10 },
          padding: 12,
          usePointStyle: true,
          boxWidth: 8,
        },
      },
    },
  };

  attackTypeChartData = computed<ChartConfiguration<'bar'>['data']>(() => {
    const sorted = (this.flowStats()?.attackTypeCounts ?? []).slice(0, 8);
    return {
      labels: sorted.map((c) => c.attackType),
      datasets: [
        {
          label: 'Rastet',
          data: sorted.map((c) => c.count),
          backgroundColor: '#f97316',
          borderRadius: 6,
          maxBarThickness: 22,
        },
      ],
    };
  });

  attackTypeChartOptions: ChartConfiguration<'bar'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: { legend: { display: false } },
    scales: {
      x: {
        beginAtZero: true,
        ticks: { color: AXIS_COLOR, precision: 0 },
        grid: { color: GRID_COLOR },
      },
      y: { ticks: { color: '#e6e9f5', font: { size: 10 } }, grid: { display: false } },
    },
  };

  topModelsChartData = computed<ChartConfiguration<'bar'>['data']>(() => {
    const top = [...this.experiments()].sort((a, b) => b.f1Score - a.f1Score).slice(0, 5);
    return {
      labels: top.map((e) => e.mlModelName),
      datasets: [
        {
          label: 'F1-score',
          data: top.map((e) => +(e.f1Score * 100).toFixed(2)),
          backgroundColor: '#6366f1',
          borderRadius: 6,
          maxBarThickness: 22,
        },
      ],
    };
  });

  topModelsChartOptions: ChartConfiguration<'bar'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: { legend: { display: false } },
    scales: {
      x: {
        min: 0,
        max: 100,
        ticks: { color: AXIS_COLOR, callback: (v) => v + '%' },
        grid: { color: GRID_COLOR },
      },
      y: { ticks: { color: '#e6e9f5', font: { size: 10 } }, grid: { display: false } },
    },
  };

  constructor() {
    effect(() => {
      const live = this.ws.liveAlarms();
      if (live.length === 0) return;
      const [newest] = live;
      this.alarms.update((current) => {
        if (current.some((a) => a.id === newest.id)) return current;
        return [newest, ...current];
      });
    });
  }

  ngOnInit(): void {
    this.flowService.getStats().subscribe({
      next: (stats) => this.flowStats.set(stats),
      error: () => this.handleLoadError('flows'),
    });

    this.alarmService.getPage(0, 6).subscribe({
      next: (result) => {
        this.alarms.set(result.content);
        this.loading.set(false);
      },
      error: () => this.handleLoadError('alarms'),
    });

    this.alarmService.getStats().subscribe({
      next: (stats) => this.alarmStats.set(stats),
      error: () => this.handleLoadError('alarms'),
    });

    this.modelService.getAll().subscribe({
      next: (models: MLModel[]) => {
        const active = models.find((m) => m.active);
        this.activeModel.set(active ?? null);
      },
      error: () => this.handleLoadError('models'),
    });

    this.experimentService.getAll().subscribe({
      next: (results) => this.experiments.set(results),
      error: () => this.handleLoadError('experiments'),
    });
  }

  private handleLoadError(resource: string): void {
    this.loading.set(false);
    this.loadError.set(true);
    this.toast.backendError(resource);
  }

  severityDotClass(severity: string): string {
    const map: Record<string, string> = {
      CRITICAL: 'bg-[var(--color-critical)]',
      HIGH: 'bg-[var(--color-high)]',
      MEDIUM: 'bg-[var(--color-medium)]',
      LOW: 'bg-[var(--color-low)]',
    };
    return map[severity] ?? 'bg-[var(--color-text-muted)]';
  }
}
