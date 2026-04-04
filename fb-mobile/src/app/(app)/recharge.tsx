import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { createOrder, fetchMembershipOptions, type MembershipOption } from '@/api/pay';
import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';

export default function RechargeScreen() {
  const { token } = useAuth();
  const [options, setOptions] = useState<MembershipOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [buying, setBuying] = useState<string | null>(null);

  const load = useCallback(async () => {
    const { ok, data } = await fetchMembershipOptions();
    if (ok && data.ok && data.options) setOptions(data.options);
    setLoading(false);
  }, []);

  React.useEffect(() => {
    load();
  }, [load]);

  const onRefresh = async () => {
    setRefreshing(true);
    await load();
    setRefreshing(false);
  };

  const buy = async (mtype: string) => {
    if (!token) {
      Alert.alert('提示', '请先登录');
      return;
    }
    setBuying(mtype);
    try {
      const { ok, data } = await createOrder(token, mtype);
      if (!ok || !data.ok) {
        Alert.alert('失败', data.message || '');
        return;
      }
      const hint = data.simulate?.hint || '请在服务器侧完成支付联调或模拟回调';
      Alert.alert(
        '订单已创建',
        `订单号：${data.out_trade_no}\n金额：${data.total_amount}\n${data.subject}\n\n${hint}`,
      );
    } finally {
      setBuying(null);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
        <Text style={styles.intro}>选择会员档位创建订单（与网页端 recharge 一致）</Text>
        {loading ? (
          <ActivityIndicator style={{ marginTop: 24 }} color={UI.accent} />
        ) : (
          options.map((o) => (
            <TouchableOpacity
              key={o.membership_type}
              style={styles.row}
              onPress={() => buy(o.membership_type)}
              disabled={buying !== null}>
              <View>
                <Text style={styles.title}>{o.label}</Text>
                <Text style={styles.price}>¥ {o.price}</Text>
              </View>
              {buying === o.membership_type ? (
                <ActivityIndicator color={UI.accent} />
              ) : (
                <Text style={styles.go}>购买</Text>
              )}
            </TouchableOpacity>
          ))
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  intro: { margin: 16, color: UI.muted, fontSize: 14 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginHorizontal: 16,
    marginBottom: 12,
    padding: 16,
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
  },
  title: { color: UI.text, fontSize: 17, fontWeight: '600' },
  price: { color: UI.accent, marginTop: 4, fontSize: 15 },
  go: { color: UI.link, fontWeight: '600', fontSize: 16 },
});
