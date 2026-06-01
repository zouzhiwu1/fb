import { apiFetch } from '@/api/client';

/** 与 /api/membership/status 返回一致（除 ok/message） */
export type MembershipRecord = {
  effective_at?: string | null;
  expires_at?: string | null;
  membership_type?: string | null;
  membership_type_label?: string | null;
  order_id?: string | number | null;
  source?: string | null;
  source_label?: string | null;
  status?: 'active' | 'pending';
  status_label?: string;
};

/** @deprecated 使用 MembershipRecord */
export type MembershipActiveRecord = MembershipRecord;

export type MembershipStatusData = {
  ok?: boolean;
  message?: string;
  is_member?: boolean;
  /** 含待生效在内的最晚到期（ISO） */
  expires_at?: string | null;
  /** 服务端按同一标尺计算的剩余整天数 */
  days_remaining?: number | null;
  /** 当前生效片段的最晚到期 */
  active_expires_at?: string | null;
  active_days_remaining?: number | null;
  active_records?: MembershipRecord[];
  pending_records?: MembershipRecord[];
  free_week_granted_at?: string | null;
};

export async function fetchMembershipStatus(token: string) {
  return apiFetch<MembershipStatusData>('/api/membership/status', { method: 'GET', token });
}
