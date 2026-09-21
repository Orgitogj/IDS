import { Component, OnInit, effect, inject, signal, computed } from '@angular/core';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { BaseChartDirective } from 'ng2-charts';
import { ChartConfiguration } from 'chart.js';
import { AlarmService } from '../../core/services/alarm.service';
import { FlowService } from '../../core/services/flow.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { PredictionService, ShapContribution } from '../../core/services/prediction.service';
import { Alarm, AlarmStatus, AlarmSeverity } from '../../core/models/alarm.model';
import { AlarmStats } from '../../core/models/alarm-stats.model';
import { AlarmGroup } from '../../core/models/alarm-group.model';
import { Explanation, ExplanationRating } from '../../core/models/explanation.model';
import { ToastService } from '../../core/services/toast.service';
import { LabelPipe } from '../../shared/pipes/label.pipe';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;
const AXIS_COLOR = '#8b93b8';
const GRID_COLOR = '#1d2440';

@Component({
  selector: 'app-alarms',
  standalone: true,
  imports: [DatePipe, DecimalPipe, FormsModule, BaseChartDirective, LabelPipe],
  templateUrl: './alarms.component.html',
  styleUrl: './alarms.component.css',
})
export class AlarmsComponent implements OnInit {
  private alarmService = inject(AlarmService);
  private flowService = inject(FlowService);
  private predictionService = inject(PredictionService);
  private ws = inject(WebSocketService);
  private toast = inject(ToastService);

  alarms = signal<Alarm[]>([]);
  loading = signal(true);
  loadError = signal(false);
  selectedAlarmId = signal<string | null>(null);
  explanations = signal<Explanation[]>([]);
  explanationLoading = signal(false);
  generating = signal(false);
  selectedFeatureVector = signal<Record<string, number> | null>(null);
  selectedModelId = signal<string | null>(null);
  shapFeatures = signal<ShapContribution[] | null>(null);
  shapLoading = signal(false);

  searchTerm = signal('');
  severityFilter = signal<AlarmSeverity | 'ALL'>('ALL');
  statusFilter = signal<AlarmStatus | 'ALL'>('ALL');

  wsConnected = this.ws.connected;

  stats = signal<AlarmStats | null>(null);

  incidents = signal<AlarmGroup[]>([]);
  incidentsLoading = signal(false);
  showIncidents = signal(false);

  page = signal(0);
  size = signal(PAGE_SIZE);
  totalElements = signal(0);
  totalPages = signal(0);

  rangeStart = computed(() => (this.totalElements() === 0 ? 0 : this.page() * this.size() + 1));
  rangeEnd = computed(() => Math.min((this.page() + 1) * this.size(), this.totalElements()));
  hasPrevious = computed(() => this.page() > 0);
  hasNext = computed(() => this.page() + 1 < this.totalPages());

  severityCounts = computed(() => {
    const counts = this.stats()?.severityCounts ?? {};
    return {
      CRITICAL: counts['CRITICAL'] ?? 0,
      HIGH: counts['HIGH'] ?? 0,
      MEDIUM: counts['MEDIUM'] ?? 0,
      LOW: counts['LOW'] ?? 0,
    };
  });

  totalAlarms = computed(() => this.stats()?.totalAlarms ?? 0);

  shapChartData = computed<ChartConfiguration<'bar'>['data']>(() => {
    const features = this.shapFeatures() ?? [];
    const sorted = [...features].sort(
      (a, b) => Math.abs(b.shap_contribution) - Math.abs(a.shap_contribution),
    );
    return {
      labels: sorted.map((f) => f.feature),
      datasets: [
        {
          label: 'Kontributi SHAP',
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

  private debounceHandle: ReturnType<typeof setTimeout> | undefined;
  private skipFirstEffect = true;

  constructor() {
    effect(() => {
      const live = this.ws.liveAlarms();
      if (live.length === 0) return;
      const [newest] = live;

      this.loadStats();

      if (this.page() !== 0 || this.hasActiveFilters()) return;

      this.alarms.update((current) => {
        if (current.some((a) => a.id === newest.id)) return current;
        return [newest, ...current].slice(0, this.size());
      });
      this.totalElements.update((current) => current + 1);
    });

    effect(() => {
      this.searchTerm();
      this.severityFilter();
      this.statusFilter();

      if (this.skipFirstEffect) {
        this.skipFirstEffect = false;
        return;
      }

      clearTimeout(this.debounceHandle);
      this.debounceHandle = setTimeout(() => {
        this.page.set(0);
        this.load();
      }, SEARCH_DEBOUNCE_MS);
    });
  }

  ngOnInit(): void {
    this.load();
    this.loadStats();
  }

  toggleIncidents(): void {
    const next = !this.showIncidents();
    this.showIncidents.set(next);
    if (next && this.incidents().length === 0) {
      this.loadIncidents();
    }
  }

  loadIncidents(): void {
    this.incidentsLoading.set(true);
    this.alarmService.getAlarmGroups().subscribe({
      next: (incidents) => {
        this.incidents.set(incidents);
        this.incidentsLoading.set(false);
      },
      error: () => {
        this.incidentsLoading.set(false);
        this.toast.backendError('incidents');
      },
    });
  }

  private hasActiveFilters(): boolean {
    return (
      this.severityFilter() !== 'ALL' ||
      this.statusFilter() !== 'ALL' ||
      this.searchTerm().trim() !== ''
    );
  }

  load(): void {
    this.loading.set(true);
    const severity = this.severityFilter();
    const status = this.statusFilter();

    this.alarmService
      .getPage(
        this.page(),
        this.size(),
        severity === 'ALL' ? null : severity,
        status === 'ALL' ? null : status,
        this.searchTerm().trim(),
      )
      .subscribe({
        next: (result) => {
          this.alarms.set(result.content);
          this.totalElements.set(result.totalElements);
          this.totalPages.set(result.totalPages);
          this.loading.set(false);
          this.loadError.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.loadError.set(true);
          this.toast.backendError('alarms');
        },
      });
  }

  private loadStats(): void {
    this.alarmService.getStats().subscribe({
      next: (stats) => this.stats.set(stats),
      error: () => undefined,
    });
  }

  previousPage(): void {
    if (!this.hasPrevious()) return;
    this.page.update((current) => current - 1);
    this.load();
  }

  nextPage(): void {
    if (!this.hasNext()) return;
    this.page.update((current) => current + 1);
    this.load();
  }

  selectAlarm(alarm: Alarm): void {
    this.selectedAlarmId.set(alarm.id);
    this.explanations.set([]);
    this.shapFeatures.set(null);
    this.selectedFeatureVector.set(null);
    this.selectedModelId.set(null);
    this.explanationLoading.set(true);
    this.shapLoading.set(true);

    this.loadExplanations(alarm.id);

    this.flowService.getById(alarm.networkFlowId).subscribe({
      next: (flow) => {
        this.selectedFeatureVector.set(flow.featureVector);
        this.selectedModelId.set(flow.modelId);
        this.predictionService.predict(flow.featureVector, flow.modelId).subscribe({
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

  private loadExplanations(alarmId: string): void {
    this.alarmService.getExplanations(alarmId).subscribe({
      next: (list) => {
        this.explanations.set(list);
        this.explanationLoading.set(false);
      },
      error: () => {
        this.explanations.set([]);
        this.explanationLoading.set(false);
      },
    });
  }

  generateExplanation(): void {
    const alarmId = this.selectedAlarmId();
    const featureVector = this.selectedFeatureVector();
    if (!alarmId || !featureVector || this.generating()) return;

    this.generating.set(true);
    this.predictionService.explain(alarmId, featureVector, this.selectedModelId()).subscribe({
      next: (result) => {
        this.generating.set(false);
        this.loadExplanations(alarmId);
        this.toast.show(
          'Shpjegimi u gjenerua',
          result.explanations.length === 1
            ? 'U ruajt 1 shpjegim.'
            : `U ruajtën ${result.explanations.length} shpjegime.`,
          'low',
        );
      },
      error: () => {
        this.generating.set(false);
        this.toast.show(
          'Shpjegimi nuk u gjenerua',
          'Kontrolloni nëse ml-service është i ndezur (localhost:8000).',
          'critical',
        );
      },
    });
  }

  rateExplanation(explanation: Explanation, rating: ExplanationRating): void {
    const alarmId = this.selectedAlarmId();
    if (!alarmId) return;

    this.alarmService.rateExplanation(alarmId, explanation.id, rating).subscribe({
      next: (updated) => {
        this.explanations.update((current) =>
          current.map((e) => (e.id === updated.id ? updated : e)),
        );
      },
      error: () => {
        this.toast.show('Vlerësimi dështoi', 'Provoni përsëri.', 'critical');
      },
    });
  }

  ratingButtonClass(explanation: Explanation, rating: ExplanationRating): string {
    const active: Record<ExplanationRating, string> = {
      HELPFUL: 'bg-[var(--color-low)]/20 text-[var(--color-low)]',
      UNCLEAR: 'bg-[var(--color-medium)]/20 text-[var(--color-medium)]',
      INCORRECT: 'bg-[var(--color-critical)]/20 text-[var(--color-critical)]',
    };
    return explanation.rating === rating
      ? active[rating]
      : 'bg-[var(--color-surface-elevated)] text-[var(--color-text-muted)] hover:text-white';
  }

  updateStatus(alarm: Alarm, status: AlarmStatus): void {
    this.alarmService.updateStatus(alarm.id, status).subscribe({
      next: (updated) => {
        this.alarms.update((current) => current.map((a) => (a.id === updated.id ? updated : a)));
        this.loadStats();
      },
      error: () => {
        this.toast.show(
          'Statusi nuk u ndryshua',
          'Alarmi mbeti në statusin e mëparshëm.',
          'critical',
        );
      },
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
