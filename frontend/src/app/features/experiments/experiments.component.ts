import { Component, OnInit, inject, signal, computed } from '@angular/core';
import { DecimalPipe } from '@angular/common';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration } from 'chart.js';
import { ExperimentService } from '../../core/services/experiment.service';
import { ExperimentResult } from '../../core/models/experiment-result.model';

const FEATURE_COUNT_PATTERN = /^top_(\d+)_features$/;

@Component({
  selector: 'app-experiments',
  standalone: true,
  imports: [DecimalPipe, BaseChartDirective],
  templateUrl: './experiments.component.html',
  styleUrl: './experiments.component.css',
})
export class ExperimentsComponent implements OnInit {
  private experimentService = inject(ExperimentService);

  results = signal<ExperimentResult[]>([]);
  loading = signal(true);

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
        labels: { color: '#8b93b8', font: { size: 11 }, usePointStyle: true },
      },
    },
    scales: {
      x: {
        title: { display: true, text: 'Numri i Features', color: '#8b93b8' },
        ticks: { color: '#8b93b8' },
        grid: { color: '#232b4d' },
      },
      y: {
        type: 'linear',
        position: 'left',
        title: { display: true, text: 'F1-score (%)', color: '#6366f1' },
        ticks: { color: '#8b93b8' },
        grid: { color: '#232b4d' },
      },
      y1: {
        type: 'linear',
        position: 'right',
        title: { display: true, text: 'Latency (ms)', color: '#f97316' },
        ticks: { color: '#8b93b8' },
        grid: { display: false },
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
          maxBarThickness: 24,
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
        ticks: { color: '#8b93b8', callback: (v) => v + '%' },
        grid: { color: '#232b4d' },
      },
      y: {
        ticks: { color: '#e6e9f5', font: { size: 10 } },
        grid: { display: false },
      },
    },
  };

  ngOnInit(): void {
    this.experimentService.getAll().subscribe((results) => {
      this.results.set(results.sort((a, b) => b.f1Score - a.f1Score));
      this.loading.set(false);
    });
  }

  formatPercent(value: number): string {
    return (value * 100).toFixed(2) + '%';
  }
}
