export interface LoginResponse {
  token: string;
  username: string;
  role: string;
  expiresInSeconds: number;
}

export type UserRole = 'ANALYST' | 'ADMIN' | 'SERVICE';

export interface CurrentUser {
  id: string;
  username: string;
  role: UserRole;
  lastLoginAt: string | null;
}

export interface RegisterRequest {
  username: string;
  password: string;
  confirmPassword: string;
  role: UserRole;
}

export interface ChangePasswordRequest {
  currentPassword: string;
  newPassword: string;
  confirmPassword: string;
}

export interface UserResponse {
  id: string;
  username: string;
  role: UserRole;
  enabled: boolean;
  createdAt: string;
  lastLoginAt: string | null;
  lockedUntil: string | null;
}
