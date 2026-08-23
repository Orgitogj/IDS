import { Component, OnInit, effect, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';
import { WebSocketService } from '../../core/services/websocket.service';
import { AuthService } from '../../core/services/auth.service';
import { ToastService } from '../../core/services/toast.service';
import { ToastContainerComponent } from '../../shared/toast/toast-container.component';

@Component({
  selector: 'app-shell',
  standalone: true,
  imports: [RouterLink, RouterLinkActive, RouterOutlet, ToastContainerComponent],
  templateUrl: './shell.component.html',
  styleUrl: './shell.component.css',
})
export class ShellComponent implements OnInit {
  private ws = inject(WebSocketService);
  private toast = inject(ToastService);
  private auth = inject(AuthService);

  wsConnected = this.ws.connected;
  username = this.auth.username;

  logout(): void {
    this.ws.disconnect();
    this.auth.logout();
  }

  constructor() {
    effect(() => {
      const live = this.ws.liveAlarms();
      if (live.length === 0) return;
      const [newest] = live;
      this.toast.show(
        `Alarm i ri: ${newest.severity}`,
        `ID: ${newest.id.slice(0, 8)}... - Status: ${newest.status}`,
        newest.severity.toLowerCase() as 'critical' | 'high' | 'medium' | 'low',
      );
    });
  }

  ngOnInit(): void {
    this.ws.connect();
  }
}
