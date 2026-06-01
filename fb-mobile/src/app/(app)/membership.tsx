import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fetchMembershipStatus, type MembershipRecord } from '@/api/membership';
import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';

function fmtLocal(iso: string | null | undefined): string {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
  } catch {
    return iso;
  }
}

function shortOrderId(id: string | number | null | undefined): string {
  if (id == null || id === '') return '—';
  const s = String(id);
  return s.length > 18 ? `${s.slice(0, 18)}…` : s;
}

function RecordCard({ r }: { r: MembershipRecord }) {
  const pending = r.status === 'pending';
  return (
    <View style={[styles.recordCard, pending && styles.recordCardPending]}>
      <View style={styles.recordStatusRow}>
        <Text style={[styles.statusTag, pending ? styles.statusTagPending : styles.statusTagActive]}>
          {r.status_label || (pending ? '待生效' : '生效中')}
        </Text>
      </View>
      <View style={styles.recordRow}>
        <Text style={styles.recordLabel}>类型</Text>
        <Text style={styles.recordValue}>{r.membership_type_label || r.membership_type || '—'}</Text>
      </View>
      <View style={styles.recordRow}>
        <Text style={styles.recordLabel}>来源</Text>
        <Text style={styles.recordValue}>{r.source_label || r.source || '—'}</Text>
      </View>
      <View style={styles.recordRow}>
        <Text style={styles.recordLabel}>生效时间</Text>
        <Text style={styles.recordValue}>{fmtLocal(r.effective_at ?? undefined)}</Text>
      </View>
      <View style={styles.recordRow}>
        <Text style={styles.recordLabel}>到期时间</Text>
        <Text style={styles.recordValue}>{fmtLocal(r.expires_at ?? undefined)}</Text>
      </View>
      <View style={styles.recordRow}>
        <Text style={styles.recordLabel}>订单号</Text>
        <Text style={styles.recordValueMono}>{shortOrderId(r.order_id)}</Text>
      </View>
    </View>
  );
}

export default function MembershipScreen() {
  const { token } = useAuth();
  const [data, setData] = useState<{
    is_member?: boolean;
    expires_at?: string | null;
    days_remaining?: number | null;
    active_expires_at?: string | null;
    active_days_remaining?: number | null;
    active_records?: MembershipRecord[];
    pending_records?: MembershipRecord[];
    free_week_granted_at?: string | null;
  } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!token) {
      setData(null);
      setErr('未登录');
      setLoading(false);
      return;
    }
    const { ok, data: body } = await fetchMembershipStatus(token);
    if (ok && body.ok) {
      setErr(null);
      setData({
        is_member: body.is_member,
        expires_at: body.expires_at,
        days_remaining: body.days_remaining,
        active_expires_at: body.active_expires_at,
        active_days_remaining: body.active_days_remaining,
        active_records: body.active_records,
        pending_records: body.pending_records,
        free_week_granted_at: body.free_week_granted_at,
      });
    } else {
      setData(null);
      setErr(body.message || '加载失败');
    }
    setLoading(false);
  }, [token]);

  React.useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const isMember = !!data?.is_member;
  const totalDays = data?.days_remaining ?? null;
  const activeDays = data?.active_days_remaining ?? null;
  const hasPending = !!(data?.pending_records && data.pending_records.length > 0);
  const allRecords = [...(data?.active_records ?? []), ...(data?.pending_records ?? [])];

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={UI.accent} />}>
        {loading ? (
          <ActivityIndicator style={{ marginTop: 40 }} color={UI.accent} />
        ) : err ? (
          <View style={styles.card}>
            <Text style={styles.errorText}>{err}</Text>
          </View>
        ) : (
          <>
            <View style={[styles.statusCard, isMember ? styles.statusMember : styles.statusNotMember]}>
              <Text style={styles.statusHint}>当前状态</Text>
              <View style={[styles.badge, isMember ? styles.badgeYes : styles.badgeNo]}>
                <Text style={styles.badgeText}>{isMember ? '会员有效' : '非会员'}</Text>
              </View>
              {data?.expires_at ? (
                <>
                  <Text style={styles.expireLine}>
                    权益总到期（含待生效）：
                    <Text style={styles.expireStrong}>{fmtLocal(data.expires_at)}</Text>
                  </Text>
                  {totalDays !== null ? (
                    <Text style={styles.daysLeft}>
                      {totalDays > 0
                        ? `总剩余约 ${totalDays} 天（至上述日期止）`
                        : '总权益即将到期，请以到期时刻为准'}
                    </Text>
                  ) : null}
                  {hasPending && data.active_expires_at ? (
                    <>
                      <Text style={styles.segmentLine}>
                        当前生效至：
                        <Text style={styles.segmentStrong}>{fmtLocal(data.active_expires_at)}</Text>
                      </Text>
                      {activeDays !== null ? (
                        <Text style={styles.daysLeftSegment}>
                          {activeDays > 0
                            ? `本段剩余约 ${activeDays} 天；续期权益将在生效后继续累计`
                            : '本段即将结束，续期权益将接续生效'}
                        </Text>
                      ) : null}
                    </>
                  ) : null}
                </>
              ) : null}
            </View>

            <Text style={styles.sectionTitle}>权益明细</Text>
            <Text style={styles.sectionHint}>
              已购会员在上一段到期后顺延生效；「待生效」表示已付款、尚未到生效时刻的权益。
            </Text>

            {!allRecords.length ? (
              <View style={styles.card}>
                <Text style={styles.emptyHint}>当前没有未过期的会员权益记录。</Text>
              </View>
            ) : (
              allRecords.map((r, i) => <RecordCard key={`${r.status}-${i}`} r={r} />)
            )}

            {data?.free_week_granted_at ? (
              <View style={styles.giftBox}>
                <Text style={styles.giftText}>
                  注册赠送周会员已发放过（记录时间：{fmtLocal(data.free_week_granted_at)}）。是否仍在有效期内见上表。
                </Text>
              </View>
            ) : null}
          </>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  card: {
    margin: 16,
    padding: 16,
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
  },
  errorText: { color: '#f87171', fontSize: 15 },
  statusCard: {
    marginHorizontal: 16,
    marginTop: 8,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
  },
  statusMember: {
    backgroundColor: '#052e16',
    borderColor: '#166534',
  },
  statusNotMember: {
    backgroundColor: '#450a0a',
    borderColor: '#7f1d1d',
  },
  statusHint: { color: UI.muted, fontSize: 14, marginBottom: 8 },
  badge: {
    alignSelf: 'flex-start',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
    marginBottom: 4,
  },
  badgeYes: { backgroundColor: '#16a34a' },
  badgeNo: { backgroundColor: '#64748b' },
  badgeText: { color: '#fff', fontSize: 14, fontWeight: '700' },
  expireLine: { marginTop: 10, fontSize: 15, color: UI.text, lineHeight: 22 },
  expireStrong: { color: UI.accent, fontWeight: '700' },
  daysLeft: { marginTop: 6, fontSize: 13, color: UI.muted, lineHeight: 20 },
  segmentLine: { marginTop: 12, fontSize: 14, color: UI.text, lineHeight: 20 },
  segmentStrong: { color: '#fbbf24', fontWeight: '600' },
  daysLeftSegment: { marginTop: 4, fontSize: 12, color: UI.muted, lineHeight: 18 },
  sectionTitle: {
    marginHorizontal: 16,
    marginTop: 24,
    fontSize: 17,
    fontWeight: '700',
    color: UI.text,
  },
  sectionHint: {
    marginHorizontal: 16,
    marginTop: 8,
    fontSize: 13,
    color: UI.muted,
    lineHeight: 20,
  },
  emptyHint: { fontSize: 14, color: UI.muted, lineHeight: 22 },
  recordCard: {
    marginHorizontal: 16,
    marginTop: 12,
    padding: 14,
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
  },
  recordCardPending: {
    borderColor: '#854d0e',
    backgroundColor: '#1c1917',
  },
  recordStatusRow: { marginBottom: 8 },
  statusTag: {
    alignSelf: 'flex-start',
    fontSize: 12,
    fontWeight: '700',
    paddingHorizontal: 8,
    paddingVertical: 3,
    borderRadius: 6,
    overflow: 'hidden',
  },
  statusTagActive: { color: '#86efac', backgroundColor: '#14532d' },
  statusTagPending: { color: '#fde68a', backgroundColor: '#422006' },
  recordRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    paddingVertical: 8,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: UI.border,
  },
  recordLabel: { fontSize: 13, color: UI.muted, width: '28%' },
  recordValue: { fontSize: 14, color: UI.text, flex: 1, textAlign: 'right' },
  recordValueMono: { fontSize: 13, color: UI.text, flex: 1, textAlign: 'right', fontVariant: ['tabular-nums'] },
  giftBox: {
    marginHorizontal: 16,
    marginTop: 20,
    marginBottom: 32,
    paddingTop: 14,
    borderTopWidth: 1,
    borderTopColor: UI.border,
  },
  giftText: { fontSize: 13, color: UI.muted, lineHeight: 20 },
});
