import { Redirect } from 'expo-router';
import React from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';
import { href } from '@/lib/href';

export default function Index() {
  const { ready, token } = useAuth();

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
  return <Redirect href={href('/login')} />;
}

const styles = StyleSheet.create({
  center: {
    flex: 1,
    backgroundColor: UI.bg,
    alignItems: 'center',
    justifyContent: 'center',
  },
});
