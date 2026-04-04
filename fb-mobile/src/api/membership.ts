import { apiFetch } from '@/api/client';

/** 与 /api/membership/status 返回一致（除 ok/message） */
export type MembershipActiveRecord = {
  effective_at?: string | null;
  expires_at?: string | null;
  membership_type?: string | null;
  membership_type_label?: string | null;
  order_id?: string | number | null;
  source?: string | null;
  source_label?: string | null;
};

export type MembershipStatusData = {
  ok?: boolean;
  message?: string;
  is_member?: boolean;
  expires_at?: string | null;
  active_records?: MembershipActiveRecord[];
  free_week_granted_at?: string | null;
};

export async function fetchMembershipStatus(token: string) {
  return apiFetch<MembershipStatusData>('/api/membership/status', { method: 'GET', token });
}
