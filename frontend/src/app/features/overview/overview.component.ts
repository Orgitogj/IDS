import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { DatePipe } from '@angular/common';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration } from 'chart.js';
import { AlarmService } from '../../core/services/alarm.service';
import { FlowService } from '../../core/services/flow.service';
import { ModelService } from '../../core/services/model.service';
import { ExperimentService } from '../../core/services/experiment.service';
import { Alarm } from '../../core/models/alarm.model';
import { NetworkFlow } from '../../core/models/network-flow.model';
import { MLModel } from '../../core/models/ml-model.model';
import { ExperimentResult } from '../../core/models/experiment-result.model';

const AXIS_COLOR = '#8b93b8';
const GRID_COLOR = '#1d2440';

@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [BaseChartDirective, DatePipe],
  templateUrl: './overview.component.html',
  styleUrl: './overview.component.css',
})
export class OverviewComponent implements OnInit {
  private alarmService = inject(AlarmService);
  private flowService = inject(FlowService);
  private modelService = inject(ModelService);
  private experimentService = inject(ExperimentService);

  totalFlows = signal(0);
  totalAlarms = signal(0);
  newAlarms = signal(0);
  criticalAlarms = signal(0);
  activeModel = signal<MLModel | null>(null);
  loading = signal(true);

  private alarms = signal<Alarm[]>([]);
  private flows = signal<NetworkFlow[]>([]);
  private experiments = signal<ExperimentResult[]>([]);

  recentAlarms = computed(() =>
    [...this.alarms()].sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt)).slice(0, 6),
  );

  timelineChartData = computed<ChartConfiguration<'line'>['data']>(() => {
    const buckets = new Map<string, number>();
    for (const a of this.alarms()) {
      const d = new Date(a.createdAt);
      const key = `${d.getFullYear()}-${d.getMonth() + 1}-${d.getDate()} ${d.getHours()}:00`;
      buckets.set(key, (buckets.get(key) ?? 0) + 1);
    }
    const sortedKeys = [...buckets.keys()].sort((a, b) => +new Date(a) - +new Date(b));
    return {
      labels: sortedKeys.map((k) => k.split(' ')[1]),
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
    const counts: Record<string, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const a of this.alarms()) counts[a.severity] = (counts[a.severity] ?? 0) + 1;
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
    const counts = new Map<string, number>();
    for (const f of this.flows()) {
      if (f.attackType) counts.set(f.attackType, (counts.get(f.attackType) ?? 0) + 1);
    }
    const sorted = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 8);
    return {
      labels: sorted.map(([k]) => k),
      datasets: [
        {
          label: 'Rastet',
          data: sorted.map(([, v]) => v),
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

  ngOnInit(): void {
    this.flowService.getAll().subscribe((flows) => {
      this.flows.set(flows);
      this.totalFlows.set(flows.length);
    });

    this.alarmService.getAll().subscribe((alarms: Alarm[]) => {
      this.alarms.set(alarms);
      this.totalAlarms.set(alarms.length);
      this.newAlarms.set(alarms.filter((a) => a.status === 'NEW').length);
      this.criticalAlarms.set(alarms.filter((a) => a.severity === 'CRITICAL').length);
    });

    this.modelService.getAll().subscribe((models: MLModel[]) => {
      const active = models.find((m) => m.active);
      this.activeModel.set(active ?? null);
      this.loading.set(false);
    });

    this.experimentService.getAll().subscribe((results) => this.experiments.set(results));
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
