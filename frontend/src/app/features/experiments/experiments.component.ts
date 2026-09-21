import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration } from 'chart.js';
import { ExperimentService } from '../../core/services/experiment.service';
import { ModelService } from '../../core/services/model.service';
import { ExperimentResult } from '../../core/models/experiment-result.model';
import { ToastService } from '../../core/services/toast.service';

const FEATURE_COUNT_PATTERN = /^top_(\d+)_features$/;
const AXIS_COLOR = '#8b93b8';
const GRID_COLOR = '#1d2440';

@Component({
  selector: 'app-experiments',
  standalone: true,
  imports: [DecimalPipe, BaseChartDirective],
  templateUrl: './experiments.component.html',
  styleUrl: './experiments.component.css',
})
export class ExperimentsComponent implements OnInit {
  private experimentService = inject(ExperimentService);
  private modelService = inject(ModelService);
  private toast = inject(ToastService);

  results = signal<ExperimentResult[]>([]);
  activeModelId = this.modelService.activeModelId;
  loading = signal(true);
  loadError = signal(false);

  bestF1 = computed(() => {
    const r = this.results();
    return r.length ? Math.max(...r.map((e) => e.f1Score)) : 0;
  });
  fastestLatency = computed(() => {
    const r = this.results().filter((e) => e.avgLatencyMs != null);
    return r.length ? Math.min(...r.map((e) => e.avgLatencyMs!)) : 0;
  });

  private rq3Subset = computed(() => {
    return this.results()
      .map((r) => {
        const match = r.featureSetUsed?.match(FEATURE_COUNT_PATTERN);
        return match ? { ...r, nFeatures: +match[1] } : null;
      })
      .filter((r): r is ExperimentResult & { nFeatures: number } => r !== null)
      .sort((a, b) => a.nFeatures - b.nFeatures);
  });

  hasRq3Data = computed(() => this.rq3Subset().length > 1);

  rq3ChartData = computed<ChartConfiguration<'line'>['data']>(() => {
    const subset = this.rq3Subset();
    return {
      labels: subset.map((r) => r.nFeatures.toString()),
      datasets: [
        {
          label: 'F1-score (%)',
          data: subset.map((r) => +(r.f1Score * 100).toFixed(2)),
          borderColor: '#6366f1',
          backgroundColor: '#6366f1',
          tension: 0.3,
          yAxisID: 'y',
          pointRadius: 4,
        },
        {
          label: 'Latency (ms)',
          data: subset.map((r) => r.avgLatencyMs ?? 0),
          borderColor: '#f97316',
          backgroundColor: '#f97316',
          tension: 0.3,
          yAxisID: 'y1',
          pointRadius: 4,
        },
      ],
    };
  });

  rq3ChartOptions: ChartConfiguration<'line'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: {
        position: 'top',
        labels: { color: AXIS_COLOR, font: { size: 10 }, usePointStyle: true },
      },
    },
    scales: {
      x: {
        title: { display: true, text: 'Numri i Features', color: AXIS_COLOR, font: { size: 10 } },
        ticks: { color: AXIS_COLOR },
        grid: { color: GRID_COLOR },
      },
      y: {
        type: 'linear',
        position: 'left',
        title: { display: true, text: 'F1 (%)', color: '#6366f1', font: { size: 10 } },
        ticks: { color: AXIS_COLOR },
        grid: { color: GRID_COLOR },
      },
      y1: {
        type: 'linear',
        position: 'right',
        title: { display: true, text: 'Latency (ms)', color: '#f97316', font: { size: 10 } },
        ticks: { color: AXIS_COLOR },
        grid: { display: false },
      },
    },
  };

  scatterChartData = computed<ChartConfiguration<'scatter'>['data']>(() => {
    const byAlgo = new Map<string, ExperimentResult[]>();
    for (const r of this.results()) {
      const algo = r.mlModelName.split('-')[0];
      if (!byAlgo.has(algo)) byAlgo.set(algo, []);
      byAlgo.get(algo)!.push(r);
    }
    const colors: Record<string, string> = { xgb: '#6366f1', rf: '#f97316' };
    return {
      datasets: [...byAlgo.entries()].map(([algo, items]) => ({
        label: algo.toUpperCase(),
        data: items.map((r) => ({ x: r.avgLatencyMs ?? 0, y: +(r.f1Score * 100).toFixed(2) })),
        backgroundColor: colors[algo] ?? '#8b93b8',
        pointRadius: 6,
        pointHoverRadius: 8,
      })),
    };
  });

  scatterChartOptions: ChartConfiguration<'scatter'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: {
        position: 'top',
        labels: { color: AXIS_COLOR, font: { size: 10 }, usePointStyle: true },
      },
    },
    scales: {
      x: {
        title: { display: true, text: 'Latency (ms)', color: AXIS_COLOR, font: { size: 10 } },
        ticks: { color: AXIS_COLOR },
        grid: { color: GRID_COLOR },
      },
      y: {
        title: { display: true, text: 'F1-score (%)', color: AXIS_COLOR, font: { size: 10 } },
        ticks: { color: AXIS_COLOR },
        grid: { color: GRID_COLOR },
      },
    },
  };

  comparisonChartData = computed<ChartConfiguration<'bar'>['data']>(() => {
    const sorted = [...this.results()].sort((a, b) => b.f1Score - a.f1Score);
    return {
      labels: sorted.map((r) => r.mlModelName),
      datasets: [
        {
          label: 'F1-score (%)',
          data: sorted.map((r) => +(r.f1Score * 100).toFixed(2)),
          backgroundColor: '#6366f1',
          borderRadius: 6,
          maxBarThickness: 20,
        },
      ],
    };
  });

  comparisonChartOptions: ChartConfiguration<'bar'>['options'] = {
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
    this.modelService.refreshActive();

    this.experimentService.getAll().subscribe({
      next: (results) => {
        this.results.set(results.sort((a, b) => b.f1Score - a.f1Score));
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadError.set(true);
        this.toast.backendError('experiments');
      },
    });
  }

  formatPercent(value: number): string {
    return (value * 100).toFixed(2) + '%';
  }
}
