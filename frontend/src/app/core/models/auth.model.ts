export interface LoginResponse {
  token: string;
  username: string;
  role: string;
  expiresInSeconds: number;
}

export interface CurrentUser {
  username: string;
  role: string;
}

export interface RegisterRequest {
  username: string;
  password: string;
  confirmPassword: string;
}
