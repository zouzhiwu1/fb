import { Link, useRouter } from 'expo-router';
import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { register, sendSmsCode } from '@/api/auth';
import { PASSWORD_POLICY_HINT, validatePasswordClient } from '@/lib/passwordPolicy';
import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';
import { href } from '@/lib/href';

const GENDERS = ['男', '女', '其他'] as const;

export default function RegisterScreen() {
  const router = useRouter();
  const { setSession } = useAuth();
  const [username, setUsername] = useState('');
  const [gender, setGender] = useState<string>('');
  const [password, setPassword] = useState('');
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  const tickCooldown = useCallback(() => {
    setCooldown(60);
    const t = setInterval(() => {
      setCooldown((c) => {
        if (c <= 1) {
          clearInterval(t);
          return 0;
        }
        return c - 1;
      });
    }, 1000);
  }, []);

  const onSendCode = async () => {
    const p = phone.trim();
    if (!/^\d{11}$/.test(p)) {
      Alert.alert('提示', '请先输入 11 位手机号');
      return;
    }
    if (cooldown > 0) return;
    setSending(true);
    try {
      const { ok, data } = await sendSmsCode(p);
      if (!ok || !data.ok) {
        Alert.alert('发送失败', data.message || '请稍后重试');
        return;
      }
      Alert.alert('提示', data.message || '验证码已发送（开发环境请看平台终端日志）');
      tickCooldown();
    } catch {
      Alert.alert('网络错误', '无法连接平台');
    } finally {
      setSending(false);
    }
  };

  const onSubmit = async () => {
    if (!username.trim()) {
      Alert.alert('提示', '请输入用户名');
      return;
    }
    if (!gender) {
      Alert.alert('提示', '请选择性别');
      return;
    }
    const pe = validatePasswordClient(password);
    if (pe) {
      Alert.alert('提示', pe);
      return;
    }
    if (!/^\d{11}$/.test(phone.trim())) {
      Alert.alert('提示', '请输入有效手机号');
      return;
    }
    if (!code.trim()) {
      Alert.alert('提示', '请输入验证码');
      return;
    }
    if (!email.includes('@')) {
      Alert.alert('提示', '请输入有效邮箱');
      return;
    }
    setLoading(true);
    try {
      const { ok, data, status } = await register({
        username: username.trim(),
        gender,
        password,
        phone: phone.trim(),
        email: email.trim(),
        code: code.trim(),
      });
      if (!ok || !data.ok) {
        Alert.alert('注册失败', data.message || `HTTP ${status}`);
        return;
      }
      if (data.token && data.user) {
        await setSession(data.token, data.user);
        router.replace(href('/home'));
        return;
      }
      Alert.alert('成功', data.message || '请登录');
      router.replace(href('/login'));
    } catch {
      Alert.alert('网络错误', '无法连接平台');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
        style={styles.flex}>
        <ScrollView
          keyboardShouldPersistTaps="handled"
          contentContainerStyle={styles.scroll}>
          <Text style={styles.label}>用户名</Text>
          <TextInput
            style={styles.input}
            value={username}
            onChangeText={setUsername}
            placeholder="用户名"
            placeholderTextColor={UI.muted}
          />

          <Text style={styles.label}>性别</Text>
          <View style={styles.row}>
            {GENDERS.map((g) => (
              <TouchableOpacity
                key={g}
                style={[styles.chip, gender === g && styles.chipOn]}
                onPress={() => setGender(g)}>
                <Text style={[styles.chipText, gender === g && styles.chipTextOn]}>{g}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <Text style={styles.label}>密码</Text>
          <Text style={styles.hint}>{PASSWORD_POLICY_HINT}</Text>
          <TextInput
            style={styles.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholderTextColor={UI.muted}
          />

          <Text style={styles.label}>手机号</Text>
          <View style={styles.phoneRow}>
            <TextInput
              style={[styles.input, styles.phoneInput]}
              value={phone}
              onChangeText={setPhone}
              keyboardType="phone-pad"
              maxLength={11}
              placeholderTextColor={UI.muted}
            />
            <TouchableOpacity
              style={[styles.codeBtn, (sending || cooldown > 0) && styles.btnDisabled]}
              onPress={onSendCode}
              disabled={sending || cooldown > 0}>
              <Text style={styles.codeBtnText}>
                {cooldown > 0 ? `${cooldown}s` : sending ? '…' : '验证码'}
              </Text>
            </TouchableOpacity>
          </View>

          <Text style={styles.label}>短信验证码</Text>
          <TextInput
            style={styles.input}
            value={code}
            onChangeText={setCode}
            keyboardType="number-pad"
            maxLength={8}
            placeholderTextColor={UI.muted}
          />

          <Text style={styles.label}>邮箱</Text>
          <TextInput
            style={styles.input}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            placeholderTextColor={UI.muted}
          />

          <TouchableOpacity
            style={[styles.btn, loading && styles.btnDisabled]}
            onPress={onSubmit}
            disabled={loading}>
            {loading ? (
              <ActivityIndicator color="#022c22" />
            ) : (
              <Text style={styles.btnText}>注册</Text>
            )}
          </TouchableOpacity>

          <Link href={href('/login')} asChild>
            <TouchableOpacity style={styles.linkWrap}>
              <Text style={styles.link}>已有账号？去登录</Text>
            </TouchableOpacity>
          </Link>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  flex: { flex: 1 },
  scroll: { padding: 24, paddingBottom: 40 },
  label: { fontSize: 13, color: UI.text, marginBottom: 6, marginTop: 10 },
  hint: { fontSize: 11, color: UI.muted, marginBottom: 4, lineHeight: 16 },
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
  row: { flexDirection: 'row', gap: 10, flexWrap: 'wrap' },
  chip: {
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: UI.border,
    backgroundColor: UI.card,
  },
  chipOn: { backgroundColor: UI.accent, borderColor: UI.accent },
  chipText: { color: UI.muted },
  chipTextOn: { color: '#022c22', fontWeight: '600' },
  phoneRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  phoneInput: { flex: 1 },
  codeBtn: {
    backgroundColor: UI.link,
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
  },
  codeBtnText: { color: '#fff', fontWeight: '600' },
  btn: {
    marginTop: 24,
    backgroundColor: UI.accent,
    borderRadius: 999,
    paddingVertical: 14,
    alignItems: 'center',
  },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#022c22', fontSize: 16, fontWeight: '600' },
  linkWrap: { marginTop: 20, marginBottom: 8 },
  link: { color: UI.link, fontSize: 15 },
});
