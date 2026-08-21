import { Component, OnDestroy, OnInit, effect, inject, signal } from '@angular/core';
import { DatePipe } from '@angular/common';
import { AlarmService } from '../../core/services/alarm.service';
import { WebSocketService } from '../../core/services/websocket.service';
import { Alarm, AlarmStatus } from '../../core/models/alarm.model';
import { Explanation } from '../../core/models/explanation.model';

@Component({
  selector: 'app-alarms',
  standalone: true,
  imports: [DatePipe],
  templateUrl: './alarms.component.html',
  styleUrl: './alarms.component.css',
})
export class AlarmsComponent implements OnInit, OnDestroy {
  private alarmService = inject(AlarmService);
  private ws = inject(WebSocketService);

  alarms = signal<Alarm[]>([]);
  loading = signal(true);
  selectedAlarmId = signal<string | null>(null);
  explanation = signal<Explanation | null>(null);
  explanationLoading = signal(false);

  wsConnected = this.ws.connected;

  constructor() {
    effect(() => {
      const live = this.ws.liveAlarms();
      if (live.length === 0) return;
      const [newest, ...rest] = live;
      this.alarms.update((current) => {
        if (current.some((a) => a.id === newest.id)) return current;
        return [newest, ...current];
      });
    });
  }

  ngOnInit(): void {
    this.alarmService.getAll().subscribe((alarms) => {
      this.alarms.set(alarms);
      this.loading.set(false);
    });
    this.ws.connect();
  }

  ngOnDestroy(): void {
    this.ws.disconnect();
  }

  selectAlarm(alarm: Alarm): void {
    this.selectedAlarmId.set(alarm.id);
    this.explanation.set(null);
    this.explanationLoading.set(true);

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
  }

  updateStatus(alarm: Alarm, status: AlarmStatus): void {
    this.alarmService.updateStatus(alarm.id, status).subscribe((updated) => {
      this.alarms.update((current) =>
        current.map((a) => (a.id === updated.id ? updated : a))
      );
    });
  }

  severityClass(severity: string): string {
    const map: Record<string, string> = {
      CRITICAL: 'bg-[var(--color-critical)]/15 text-[var(--color-critical)] border-[var(--color-critical)]/30',
      HIGH: 'bg-[var(--color-high)]/15 text-[var(--color-high)] border-[var(--color-high)]/30',
      MEDIUM: 'bg-[var(--color-medium)]/15 text-[var(--color-medium)] border-[var(--color-medium)]/30',
      LOW: 'bg-[var(--color-low)]/15 text-[var(--color-low)] border-[var(--color-low)]/30',
    };
    return map[severity] ?? '';
  }
}
