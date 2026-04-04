import { Redirect, Stack } from 'expo-router';
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';
import { href } from '@/lib/href';

export default function AuthLayout() {
  const { token, ready } = useAuth();

  if (!ready) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={UI.accent} />
      </View>
    );
  }
  if (token) {
    return <Redirect href={href('/home')} />;
  }

  return (
    <Stack
      screenOptions={{
        headerStyle: { backgroundColor: UI.bg },
        headerTintColor: UI.text,
        headerTitleStyle: { fontWeight: '600' },
        contentStyle: { backgroundColor: UI.bg },
      }}>
      <Stack.Screen name="login" options={{ title: '登录' }} />
      <Stack.Screen name="register" options={{ title: '注册' }} />
    </Stack>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, backgroundColor: UI.bg, alignItems: 'center', justifyContent: 'center' },
});
