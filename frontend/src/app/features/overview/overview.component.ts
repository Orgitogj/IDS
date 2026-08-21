import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration } from 'chart.js';
import { AlarmService } from '../../core/services/alarm.service';
import { FlowService } from '../../core/services/flow.service';
import { ModelService } from '../../core/services/model.service';
import { ExperimentService } from '../../core/services/experiment.service';
import { Alarm } from '../../core/models/alarm.model';
import { MLModel } from '../../core/models/ml-model.model';
import { ExperimentResult } from '../../core/models/experiment-result.model';

@Component({
  selector: 'app-overview',
  standalone: true,
  imports: [BaseChartDirective],
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
  activeModel = signal<MLModel | null>(null);
  loading = signal(true);

  private alarms = signal<Alarm[]>([]);
  private experiments = signal<ExperimentResult[]>([]);

  severityChartData = computed<ChartConfiguration<'doughnut'>['data']>(() => {
    const counts: Record<string, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const a of this.alarms()) {
      counts[a.severity] = (counts[a.severity] ?? 0) + 1;
    }
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
    cutout: '68%',
    plugins: {
      legend: {
        position: 'bottom',
        labels: { color: '#8b93b8', font: { size: 11 }, padding: 16, usePointStyle: true },
      },
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
          maxBarThickness: 28,
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
        ticks: { color: '#8b93b8', callback: (v) => v + '%' },
        grid: { color: '#232b4d' },
      },
      y: {
        ticks: { color: '#e6e9f5', font: { size: 11 } },
        grid: { display: false },
      },
    },
  };

  ngOnInit(): void {
    this.flowService.getAll().subscribe((flows) => this.totalFlows.set(flows.length));

    this.alarmService.getAll().subscribe((alarms: Alarm[]) => {
      this.alarms.set(alarms);
      this.totalAlarms.set(alarms.length);
      this.newAlarms.set(alarms.filter((a) => a.status === 'NEW').length);
    });

    this.modelService.getAll().subscribe((models: MLModel[]) => {
      const active = models.find((m) => m.active);
      this.activeModel.set(active ?? null);
      this.loading.set(false);
    });

    this.experimentService.getAll().subscribe((results) => this.experiments.set(results));
  }
}
