import { Component, OnInit, effect, inject, signal, computed } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { DatePipe, DecimalPipe } from '@angular/common';
import { FlowService } from '../../core/services/flow.service';
import { NetworkFlow, FlowLabel } from '../../core/models/network-flow.model';
import { ToastService } from '../../core/services/toast.service';

const PAGE_SIZE = 50;
const SEARCH_DEBOUNCE_MS = 300;

@Component({
  selector: 'app-flows',
  standalone: true,
  imports: [FormsModule, DatePipe, DecimalPipe],
  templateUrl: './flows.component.html',
  styleUrl: './flows.component.css',
})
export class FlowsComponent implements OnInit {
  private flowService = inject(FlowService);
  private toast = inject(ToastService);

  flows = signal<NetworkFlow[]>([]);
  loading = signal(true);
  loadError = signal(false);
  selectedFlow = signal<NetworkFlow | null>(null);

  searchTerm = signal('');
  labelFilter = signal<FlowLabel | 'ALL'>('ALL');

  page = signal(0);
  size = signal(PAGE_SIZE);
  totalElements = signal(0);
  totalPages = signal(0);

  rangeStart = computed(() => (this.totalElements() === 0 ? 0 : this.page() * this.size() + 1));
  rangeEnd = computed(() => Math.min((this.page() + 1) * this.size(), this.totalElements()));
  hasPrevious = computed(() => this.page() > 0);
  hasNext = computed(() => this.page() + 1 < this.totalPages());

  private debounceHandle: ReturnType<typeof setTimeout> | undefined;
  private skipFirstEffect = true;

  constructor() {
    effect(() => {
      this.searchTerm();
      this.labelFilter();

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
  }

  load(): void {
    this.loading.set(true);
    const label = this.labelFilter();

    this.flowService
      .getPage(this.page(), this.size(), label === 'ALL' ? null : label, this.searchTerm().trim())
      .subscribe({
        next: (result) => {
          this.flows.set(result.content);
          this.totalElements.set(result.totalElements);
          this.totalPages.set(result.totalPages);
          this.loading.set(false);
          this.loadError.set(false);
        },
        error: () => {
          this.loading.set(false);
          this.loadError.set(true);
          this.toast.backendError('flows');
        },
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

  selectFlow(flow: NetworkFlow): void {
    this.selectedFlow.set(flow);
  }

  labelClass(label: string | null): string {
    if (label === 'ATTACK')
      return 'bg-[var(--color-critical)]/15 text-[var(--color-critical)] border-[var(--color-critical)]/30';
    if (label === 'BENIGN')
      return 'bg-[var(--color-low)]/15 text-[var(--color-low)] border-[var(--color-low)]/30';
    return 'bg-[var(--color-text-muted)]/15 text-[var(--color-text-muted)] border-[var(--color-border)]';
  }

  featureEntries(flow: NetworkFlow): [string, number][] {
    return Object.entries(flow.featureVector).slice(0, 12) as [string, number][];
  }
}
