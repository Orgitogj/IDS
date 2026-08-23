import { Component, OnInit, effect, inject, signal, computed } from '@angular/core';
import { DatePipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration } from 'chart.js';
import { AlarmService } from '../../core/services/alarm.service';
import { FlowService } from '../../core/services/flow.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { PredictionService, ShapContribution } from '../../core/services/prediction.service';
import { Alarm, AlarmStatus, AlarmSeverity } from '../../core/models/alarm.model';
import { Explanation } from '../../core/models/explanation.model';

const AXIS_COLOR = '#8b93b8';
const GRID_COLOR = '#1d2440';

@Component({
  selector: 'app-alarms',
  standalone: true,
  imports: [DatePipe, FormsModule, BaseChartDirective],
  templateUrl: './alarms.component.html',
  styleUrl: './alarms.component.css',
})
export class AlarmsComponent implements OnInit {
  private alarmService = inject(AlarmService);
  private flowService = inject(FlowService);
  private predictionService = inject(PredictionService);
  private ws = inject(WebSocketService);

  alarms = signal<Alarm[]>([]);
  loading = signal(true);
  selectedAlarmId = signal<string | null>(null);
  explanation = signal<Explanation | null>(null);
  explanationLoading = signal(false);
  shapFeatures = signal<ShapContribution[] | null>(null);
  shapLoading = signal(false);

  searchTerm = signal('');
  severityFilter = signal<AlarmSeverity | 'ALL'>('ALL');
  statusFilter = signal<AlarmStatus | 'ALL'>('ALL');

  wsConnected = this.ws.connected;

  severityCounts = computed(() => {
    const counts = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 };
    for (const a of this.alarms()) counts[a.severity]++;
    return counts;
  });

  filteredAlarms = computed(() => {
    const term = this.searchTerm().toLowerCase().trim();
    const severity = this.severityFilter();
    const status = this.statusFilter();
    return this.alarms().filter((a) => {
      const matchesSeverity = severity === 'ALL' || a.severity === severity;
      const matchesStatus = status === 'ALL' || a.status === status;
      const matchesSearch = !term || a.id.toLowerCase().includes(term);
      return matchesSeverity && matchesStatus && matchesSearch;
    });
  });

  shapChartData = computed<ChartConfiguration<'bar'>['data']>(() => {
    const features = this.shapFeatures() ?? [];
    const sorted = [...features].sort(
      (a, b) => Math.abs(b.shap_contribution) - Math.abs(a.shap_contribution),
    );
    return {
      labels: sorted.map((f) => f.feature),
      datasets: [
        {
          label: 'SHAP contribution',
          data: sorted.map((f) => f.shap_contribution),
          backgroundColor: sorted.map((f) => (f.shap_contribution >= 0 ? '#ef4444' : '#22c55e')),
          borderRadius: 4,
          maxBarThickness: 18,
        },
      ],
    };
  });

  shapChartOptions: ChartConfiguration<'bar'>['options'] = {
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: 'y',
    plugins: { legend: { display: false } },
    scales: {
      x: { ticks: { color: AXIS_COLOR, font: { size: 10 } }, grid: { color: GRID_COLOR } },
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
    this.alarmService.getAll().subscribe((alarms) => {
      this.alarms.set(alarms.sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt)));
      this.loading.set(false);
    });
  }

  selectAlarm(alarm: Alarm): void {
    this.selectedAlarmId.set(alarm.id);
    this.explanation.set(null);
    this.shapFeatures.set(null);
    this.explanationLoading.set(true);
    this.shapLoading.set(true);

    this.alarmService.getExplanation(alarm.id).subscribe({
      next: (exp) => {
        this.explanation.set(exp);
        this.explanationLoading.set(false);
      },
      error: () => {
        this.explanation.set(null);
        this.explanationLoading.set(false);
      },
    });

    this.flowService.getById(alarm.networkFlowId).subscribe({
      next: (flow) => {
        this.predictionService.predict(flow.featureVector).subscribe({
          next: (result) => {
            this.shapFeatures.set(result.top_shap_features);
            this.shapLoading.set(false);
          },
          error: () => this.shapLoading.set(false),
        });
      },
      error: () => this.shapLoading.set(false),
    });
  }

  updateStatus(alarm: Alarm, status: AlarmStatus): void {
    this.alarmService.updateStatus(alarm.id, status).subscribe((updated) => {
      this.alarms.update((current) => current.map((a) => (a.id === updated.id ? updated : a)));
    });
  }

  severityClass(severity: string): string {
    const map: Record<string, string> = {
      CRITICAL:
        'bg-[var(--color-critical)]/15 text-[var(--color-critical)] border-[var(--color-critical)]/30',
      HIGH: 'bg-[var(--color-high)]/15 text-[var(--color-high)] border-[var(--color-high)]/30',
      MEDIUM:
        'bg-[var(--color-medium)]/15 text-[var(--color-medium)] border-[var(--color-medium)]/30',
      LOW: 'bg-[var(--color-low)]/15 text-[var(--color-low)] border-[var(--color-low)]/30',
    };
    return map[severity] ?? '';
  }
}
