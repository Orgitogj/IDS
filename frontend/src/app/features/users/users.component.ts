import { DatePipe } from '@angular/common';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { UserResponse } from '../../core/models/auth.model';
import { AuthService } from '../../core/services/auth.service';
import { ToastService } from '../../core/services/toast.service';
import { UserService } from '../../core/services/user.service';

@Component({
  selector: 'app-users',
  standalone: true,
  imports: [DatePipe, RouterLink],
  templateUrl: './users.component.html',
})
export class UsersComponent implements OnInit {
  private userService = inject(UserService);
  private auth = inject(AuthService);
  private toast = inject(ToastService);

  users = signal<UserResponse[]>([]);
  loading = signal(true);
  loadError = signal(false);
  pending = signal<string | null>(null);

  currentUsername = computed(() => this.auth.username());

  ngOnInit(): void {
    this.load();
  }

  isSelf(user: UserResponse): boolean {
    return user.username === this.currentUsername();
  }

  isLocked(user: UserResponse): boolean {
    return user.lockedUntil !== null;
  }

  toggleEnabled(user: UserResponse): void {
    if (this.pending() || this.isSelf(user)) return;

    this.pending.set(user.id);
    this.userService.setEnabled(user.id, !user.enabled).subscribe({
      next: (updated) => {
        this.replace(updated);
        this.pending.set(null);
        this.toast.show(
          updated.enabled ? 'Perdoruesi u aktivizua' : 'Perdoruesi u cakivizua',
          updated.enabled
            ? `${updated.username} mund te hyje perseri.`
            : `${updated.username} u shkeput menjehere nga te gjitha sesionet.`,
          updated.enabled ? 'low' : 'high',
        );
      },
      error: () => {
        this.pending.set(null);
        this.toast.show('Veprimi deshtoi', 'Perdoruesi mbeti si me pare.', 'critical');
      },
    });
  }

  unlock(user: UserResponse): void {
    if (this.pending()) return;

    this.pending.set(user.id);
    this.userService.unlock(user.id).subscribe({
      next: (updated) => {
        this.replace(updated);
        this.pending.set(null);
        this.toast.show('Llogaria u zhbllokua', `${updated.username} mund te provoje perseri.`, 'low');
      },
      error: () => {
        this.pending.set(null);
        this.toast.show('Zhbllokimi deshtoi', 'Provoni perseri.', 'critical');
      },
    });
  }

  private load(): void {
    this.loading.set(true);
    this.userService.list().subscribe({
      next: (users) => {
        this.users.set(users);
        this.loading.set(false);
        this.loadError.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.loadError.set(true);
        this.toast.backendError('users');
      },
    });
  }

  private replace(updated: UserResponse): void {
    this.users.update((current) =>
      current.map((user) => (user.id === updated.id ? updated : user)),
    );
  }
}
