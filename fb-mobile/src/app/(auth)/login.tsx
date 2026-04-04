import { Link, useRouter } from 'expo-router';
import React, { useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { loginWithPassword } from '@/api/auth';
import { getApiBaseUrl } from '@/api/config';
import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';
import { href } from '@/lib/href';

/** 是否像本地/内网开发地址（与线上正式 API 区分提示文案） */
function isDevApiBase(base: string): boolean {
  const b = base.toLowerCase();
  if (/127\.0\.0\.1|localhost/.test(b)) return true;
  if (/^https?:\/\/(10\.|192\.168\.|172\.(1[6-9]|2\d|3[01])\.)/.test(b)) return true;
  return false;
}

function networkErrorHint(base: string): string {
  if (isDevApiBase(base)) {
    return (
      '① 本机已启动平台：python run.py（默认 5001）\n' +
      '② 真机不要用 127.0.0.1；请用电脑局域网 IP，例如：\n' +
      'EXPO_PUBLIC_API_BASE_URL=http://192.168.x.x:5001 npx expo start\n' +
      '（环境变量只写到端口，不要加 /login）'
    );
  }
  return (
    '① 正式环境应使用 https://你的域名（走 443），不要用 :5001，除非云安全组已对公网开放 5001\n' +
    '② 确认服务器 Nginx 已反代到 Flask，浏览器能打开同一域名下的网页与接口\n' +
    '③ 重新打包前在 eas.json 的 env 里设置 EXPO_PUBLIC_API_BASE_URL'
  );
}

export default function LoginScreen() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);

  const onLogin = async () => {
    const p = phone.trim();
    if (!/^\d{11}$/.test(p)) {
      Alert.alert('提示', '请输入 11 位手机号');
      return;
    }
    if (!password) {
      Alert.alert('提示', '请输入密码');
      return;
    }
    setLoading(true);
    try {
      const { ok, data, status } = await loginWithPassword(p, password);
      if (!ok || !data.ok || !data.token || !data.user) {
        Alert.alert('登录失败', data.message || `HTTP ${status}`);
        return;
      }
      await setSession(data.token, data.user);
      router.replace(href('/home'));
    } catch (e) {
      const base = getApiBaseUrl();
      const msg = e instanceof Error ? e.message : String(e);
      Alert.alert('网络错误', `当前 API：${base}\n\n${networkErrorHint(base)}\n\n${msg}`);
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}>
        <View style={styles.box}>
          <Text style={styles.title}>足球数据平台</Text>
          <Text style={styles.sub}>使用手机号与密码登录（与网页端同一账号）</Text>

          <Text style={styles.label}>手机号</Text>
          <TextInput
            style={styles.input}
            value={phone}
            onChangeText={setPhone}
            placeholder="11 位手机号"
            keyboardType="phone-pad"
            maxLength={11}
            placeholderTextColor={UI.muted}
            autoCapitalize="none"
          />

          <Text style={styles.label}>密码</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            placeholder="密码"
            secureTextEntry
            placeholderTextColor={UI.muted}
          />

          <TouchableOpacity
            style={[styles.btn, loading && styles.btnDisabled]}
            onPress={onLogin}
            disabled={loading}>
            {loading ? (
              <ActivityIndicator color="#022c22" />
            ) : (
              <Text style={styles.btnText}>登录</Text>
            )}
          </TouchableOpacity>

          <Link href={href('/register')} asChild>
            <TouchableOpacity style={styles.linkWrap}>
              <Text style={styles.link}>没有账号？去注册</Text>
            </TouchableOpacity>
          </Link>
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  flex: { flex: 1 },
  box: { flex: 1, padding: 24, paddingTop: 16 },
  title: { fontSize: 26, fontWeight: '700', color: UI.text, marginBottom: 8 },
  sub: { fontSize: 14, color: UI.muted, marginBottom: 28 },
  label: { fontSize: 13, color: UI.text, marginBottom: 6, marginTop: 12 },
  input: {
    backgroundColor: UI.card,
    borderWidth: 1,
    borderColor: UI.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: UI.text,
    fontSize: 16,
  },
  btn: {
    marginTop: 28,
    backgroundColor: UI.accent,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: 'center',
  },
  btnDisabled: { opacity: 0.7 },
  btnText: { color: '#022c22', fontSize: 16, fontWeight: '600' },
  linkWrap: { marginTop: 20 },
  link: { color: UI.link, fontSize: 15 },
});
