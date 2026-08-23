import { Component, OnInit, inject, signal, computed } from '@angular/core';
import {FormsModule} from '@angular/forms';
import { DatePipe,DecimalPipe} from '@angular/common';
import { FlowService } from '../../core/services/flow.service';
import { NetworkFlow, FlowLabel } from '../../core/models/network-flow.model';
import { ToastService } from '../../core/services/toast.service';

@Component({
  selector: 'app-flows',
  standalone: true,
  imports: [FormsModule, DatePipe,DecimalPipe],
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

  filteredFlows = computed(() => {
    const term = this.searchTerm().toLowerCase().trim();
    const label = this.labelFilter();
    return this.flows().filter((f) => {
      const matchesLabel = label === 'ALL' || f.predictedLabel === label;
      const matchesSearch =
        !term ||
        f.id.toLowerCase().includes(term) ||
        (f.sourceIp ?? '').toLowerCase().includes(term) ||
        (f.destinationIp ?? '').toLowerCase().includes(term) ||
        (f.attackType ?? '').toLowerCase().includes(term);
      return matchesLabel && matchesSearch;
    });
  });

  ngOnInit(): void {
    this.flowService.getAll().subscribe({
      next: (flows) => {
        this.flows.set(flows.sort((a, b) => +new Date(b.createdAt) - +new Date(a.createdAt)));
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadError.set(true);
        this.toast.backendError('flows');
      },
    });
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
