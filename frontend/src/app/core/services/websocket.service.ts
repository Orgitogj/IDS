import { Injectable, inject, signal } from '@angular/core';
import { Client, IMessage } from '@stomp/stompjs';
import SockJS from 'sockjs-client';
import { Alarm } from '../models/alarm.model';
import { Incident } from '../models/incident.model';
import { AuthService } from './auth.service';

const WS_URL = 'http://localhost:8080/ws';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private client: Client | null = null;
  private auth = inject(AuthService);

  readonly connected = signal(false);
  readonly liveAlarms = signal<Alarm[]>([]);
  readonly liveIncidents = signal<Incident[]>([]);

  connect(): void {
    if (this.client?.active) {
      return;
    }

    const token = this.auth.token();
    if (!token) {
      return;
    }

    this.client = new Client({
      webSocketFactory: () => new SockJS(WS_URL) as WebSocket,
      connectHeaders: { Authorization: `Bearer ${token}` },
      reconnectDelay: 5000,
      beforeConnect: () => {
        const current = this.auth.token();
        this.client!.connectHeaders = current ? { Authorization: `Bearer ${current}` } : {};
      },
      onConnect: () => {
        this.connected.set(true);
        this.client!.subscribe('/topic/alarms', (message: IMessage) => {
          const alarm: Alarm = JSON.parse(message.body);
          this.liveAlarms.update((current) => [alarm, ...current]);
        });
        this.client!.subscribe('/topic/incidents', (message: IMessage) => {
          const incident: Incident = JSON.parse(message.body);
          this.liveIncidents.update((current) => [
            incident,
            ...current.filter((existing) => existing.id !== incident.id),
          ]);
        });
      },
      onDisconnect: () => this.connected.set(false),
      onStompError: () => this.connected.set(false),
    });

    this.client.activate();
  }

  disconnect(): void {
    this.client?.deactivate();
    this.connected.set(false);
  }
}
