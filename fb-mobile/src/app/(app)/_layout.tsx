import { Redirect, Stack } from 'expo-router';
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';
import { href } from '@/lib/href';

export default function AppStackLayout() {
  const { token, ready } = useAuth();

  if (!ready) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={UI.accent} />
      </View>
    );
  }
  if (!token) {
    return <Redirect href={href('/login')} />;
  }

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: UI.bg },
        headerTintColor: UI.text,
        headerTitleStyle: { fontWeight: '600' },
        headerShadowVisible: false,
        contentStyle: { backgroundColor: UI.bg },
      }}>
      <Stack.Screen name="home" options={{ title: '首页' }} />
      <Stack.Screen name="curves" options={{ title: '曲线图查询' }} />
      <Stack.Screen name="account" options={{ title: '账户资料' }} />
      <Stack.Screen name="membership" options={{ title: '会员状态' }} />
      <Stack.Screen name="recharge" options={{ title: '充值 / 开通会员' }} />
      <Stack.Screen name="records" options={{ title: '充值记录' }} />
    </Stack>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: UI.bg, alignItems: 'center', justifyContent: 'center' },
});
