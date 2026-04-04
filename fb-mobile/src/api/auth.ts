import { apiFetch } from '@/api/client';

export type UserDto = {
  id: number;
  username: string;
  gender: string;
  phone: string;
  email: string | null;
  created_at: string | null;
  password_set: boolean;
};

export async function loginWithPassword(phone: string, password: string) {
  return apiFetch<{ ok: boolean; message?: string; token?: string; user?: UserDto }>(
    '/api/auth/login',
    {
      method: 'POST',
      body: JSON.stringify({ phone: phone.trim(), password }),
    },
  );
}

export async function sendSmsCode(phone: string) {
  return apiFetch<{ ok: boolean; message?: string }>('/api/auth/send-code', {
    method: 'POST',
    body: JSON.stringify({ phone: phone.trim() }),
  });
}

export async function register(body: {
  username: string;
  gender: string;
  password: string;
  phone: string;
  email: string;
  code: string;
}) {
  return apiFetch<{ ok: boolean; message?: string; token?: string; user?: UserDto }>(
    '/api/auth/register',
    {
      method: 'POST',
      body: JSON.stringify(body),
    },
  );
}

export async function fetchMe(token: string) {
  return apiFetch<{ ok: boolean; message?: string; user?: UserDto }>('/api/auth/me', {
    method: 'GET',
    token,
  });
}

export async function changePassword(
  token: string,
  current_password: string | undefined,
  new_password: string,
) {
  return apiFetch<{ ok: boolean; message?: string }>('/api/auth/change-password', {
    method: 'POST',
    token,
    body: JSON.stringify({ current_password: current_password || '', new_password }),
  });
}

export async function changeEmail(token: string, email: string) {
  return apiFetch<{ ok: boolean; message?: string; user?: UserDto }>(
    '/api/auth/change-email',
    {
      method: 'POST',
      token,
      body: JSON.stringify({ email: email.trim() }),
    },
  );
}

export async function changePhone(token: string, new_phone: string, code: string) {
  return apiFetch<{ ok: boolean; message?: string; user?: UserDto }>(
    '/api/auth/change-phone',
    {
      method: 'POST',
      token,
      body: JSON.stringify({ new_phone: new_phone.trim(), code: code.trim() }),
    },
  );
}
