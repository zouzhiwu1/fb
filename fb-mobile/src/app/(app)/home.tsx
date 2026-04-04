import { useRouter } from 'expo-router';
import React from 'react';
import { Alert, ScrollView, StyleSheet, Text, TouchableOpacity, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';
import { href } from '@/lib/href';

function MenuItem({ title, onPress }: { title: string; onPress: () => void }) {
  return (
    <TouchableOpacity style={styles.item} onPress={onPress} activeOpacity={0.85}>
      <Text style={styles.itemText}>{title}</Text>
      <Text style={styles.chevron}>›</Text>
    </TouchableOpacity>
  );
}

export default function HomeScreen() {
  const router = useRouter();
  const { user, clearSession } = useAuth();

  const logout = () => {
    Alert.alert('退出登录', '确定要退出吗？', [
      { text: '取消', style: 'cancel' },
      {
        text: '退出',
        style: 'destructive',
        onPress: async () => {
          await clearSession();
          router.replace(href('/login'));
        },
      },
    ]);
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>
        <Text style={styles.welcome}>
          你好，{user?.username || user?.phone || '用户'}
        </Text>
        <Text style={styles.hint}>功能与网页端 home 一致</Text>

        <View style={styles.card}>
          <MenuItem title="曲线图查询" onPress={() => router.push(href('/curves'))} />
          <MenuItem title="账户资料" onPress={() => router.push(href('/account'))} />
          <MenuItem title="会员状态" onPress={() => router.push(href('/membership'))} />
          <MenuItem title="充值 / 开通会员" onPress={() => router.push(href('/recharge'))} />
          <MenuItem title="充值记录" onPress={() => router.push(href('/records'))} />
        </View>

        <TouchableOpacity style={styles.logout} onPress={logout}>
          <Text style={styles.logoutText}>退出登录</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  scroll: { padding: 20, paddingTop: 8 },
  welcome: { fontSize: 22, fontWeight: '700', color: UI.text, marginBottom: 6 },
  hint: { fontSize: 13, color: UI.muted, marginBottom: 20 },
  card: {
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
    overflow: 'hidden',
  },
  item: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 16,
    paddingHorizontal: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: UI.border,
  },
  itemText: { color: UI.text, fontSize: 16 },
  chevron: { color: UI.muted, fontSize: 22 },
  logout: {
    marginTop: 28,
    alignItems: 'center',
    paddingVertical: 14,
  },
  logoutText: { color: '#f87171', fontSize: 16 },
});
