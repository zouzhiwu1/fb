import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  RefreshControl,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { fetchOrders, type OrderItem } from '@/api/pay';
import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';

export default function RecordsScreen() {
  const { token } = useAuth();
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(async () => {
    if (!token) {
      setOrders([]);
      setLoading(false);
      return;
    }
    const { ok, data } = await fetchOrders(token, 50);
    if (ok && data.ok && data.orders) setOrders(data.orders);
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

  const renderItem = ({ item }: { item: OrderItem }) => (
    <View style={styles.card}>
      <Text style={styles.subject}>{item.subject}</Text>
      <Text style={styles.meta}>状态：{item.status_label}</Text>
      <Text style={styles.meta}>金额：¥ {item.total_amount}</Text>
      <Text style={styles.meta}>单号：{item.out_trade_no}</Text>
      <Text style={styles.meta}>创建：{item.created_at ?? '—'}</Text>
      {item.paid_at ? <Text style={styles.meta}>支付：{item.paid_at}</Text> : null}
    </View>
  );

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      {loading ? (
        <ActivityIndicator style={{ marginTop: 40 }} color={UI.accent} />
      ) : (
        <FlatList
          data={orders}
          keyExtractor={(it) => String(it.id)}
          renderItem={renderItem}
          contentContainerStyle={styles.list}
          ListEmptyComponent={
            <Text style={styles.empty}>{token ? '暂无订单' : '请先登录'}</Text>
          }
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  list: { padding: 16, paddingBottom: 32 },
  card: {
    padding: 14,
    marginBottom: 12,
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
  },
  subject: { color: UI.text, fontSize: 16, fontWeight: '600', marginBottom: 8 },
  meta: { color: UI.muted, fontSize: 13, marginBottom: 4 },
  empty: { textAlign: 'center', color: UI.muted, marginTop: 40 },
});
