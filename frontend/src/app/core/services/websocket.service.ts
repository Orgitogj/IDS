import { Injectable, signal } from '@angular/core';
import { Client, IMessage } from '@stomp/stompjs';
import SockJS from 'sockjs-client';
import { Alarm } from '../models/alarm.model';

const WS_URL = 'http://localhost:8080/ws';

@Injectable({ providedIn: 'root' })
export class WebSocketService {
  private client: Client | null = null;

  readonly connected = signal(false);
  readonly liveAlarms = signal<Alarm[]>([]);

  connect(): void {
    if (this.client?.active) {
      return;
    }

    this.client = new Client({
      webSocketFactory: () => new SockJS(WS_URL) as WebSocket,
      reconnectDelay: 5000,
      onConnect: () => {
        this.connected.set(true);
        this.client!.subscribe('/topic/alarms', (message: IMessage) => {
          const alarm: Alarm = JSON.parse(message.body);
          this.liveAlarms.update((current) => [alarm, ...current]);
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
