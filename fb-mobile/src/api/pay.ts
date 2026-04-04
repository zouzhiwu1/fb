import { apiFetch } from '@/api/client';

export type MembershipOption = {
  membership_type: string;
  label: string;
  price: string;
};

export type OrderItem = {
  id: number;
  out_trade_no: string;
  membership_type: string;
  membership_type_label: string;
  total_amount: string;
  subject: string;
  status: string;
  status_label: string;
  trade_no: string | null;
  created_at: string | null;
  paid_at: string | null;
};

export async function fetchMembershipOptions() {
  return apiFetch<{ ok: boolean; options?: MembershipOption[] }>(
    '/api/pay/membership-options',
    { method: 'GET' },
  );
}

export async function createOrder(token: string, membership_type: string) {
  return apiFetch<{
    ok: boolean;
    message?: string;
    out_trade_no?: string;
    total_amount?: string;
    subject?: string;
    simulate?: { hint?: string };
  }>('/api/pay/orders', {
    method: 'POST',
    token,
    body: JSON.stringify({ membership_type }),
  });
}

export async function fetchOrders(token: string, limit = 50) {
  return apiFetch<{ ok: boolean; message?: string; orders?: OrderItem[] }>(
    `/api/pay/orders?limit=${limit}`,
    { method: 'GET', token },
  );
}
