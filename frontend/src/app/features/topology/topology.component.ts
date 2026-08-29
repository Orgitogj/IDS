import { Component, OnInit, effect, inject, signal, computed } from '@angular/core';
import { DatePipe } from '@angular/common';
import { WebSocketService } from '../../core/services/websocket.service';
import { AlarmService } from '../../core/services/alarm.service';
import { FlowService } from '../../core/services/flow.service';
import { Alarm } from '../../core/models/alarm.model';

@Component({
  selector: 'app-topology',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './topology.component.html',
  styleUrl: './topology.component.css',
})
export class TopologyComponent implements OnInit {
  private ws = inject(WebSocketService);
  private alarmService = inject(AlarmService);
  private flowService = inject(FlowService);

  readonly attackerIp = '192.168.50.10';
  readonly victimIp = '192.168.50.20';

  private flowBaseline = signal(0);
  private flowOffset = signal(0);
  private alarmBaseline = signal(0);
  private alarmOffset = signal(0);
  private lastSeenCount = 0;

  pulsing = signal(false);

  totalFlows = computed(
    () => this.flowBaseline() + Math.max(0, this.ws.liveAlarms().length - this.flowOffset()),
  );

  totalAlarms = computed(
    () => this.alarmBaseline() + Math.max(0, this.ws.liveAlarms().length - this.alarmOffset()),
  );

  lastAlarm = computed<Alarm | null>(() => {
    const live = this.ws.liveAlarms();
    return live.length > 0 ? live[0] : null;
  });

  constructor() {
    this.lastSeenCount = this.ws.liveAlarms().length;

    effect((onCleanup) => {
      const count = this.ws.liveAlarms().length;
      const grew = count > this.lastSeenCount;
      this.lastSeenCount = count;
      if (!grew) return;

      this.pulsing.set(true);
      const timer = setTimeout(() => this.pulsing.set(false), 1500);
      onCleanup(() => clearTimeout(timer));
    });
  }

  ngOnInit(): void {
    this.flowService.getStats().subscribe({
      next: (stats) => {
        this.flowOffset.set(this.ws.liveAlarms().length);
        this.flowBaseline.set(stats.totalFlows);
      },
      error: () => undefined,
    });
    this.alarmService.getStats().subscribe({
      next: (stats) => {
        this.alarmOffset.set(this.ws.liveAlarms().length);
        this.alarmBaseline.set(stats.totalAlarms);
      },
      error: () => undefined,
    });
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
