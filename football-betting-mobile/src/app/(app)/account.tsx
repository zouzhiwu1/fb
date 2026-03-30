import React, { useCallback, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { changeEmail, changePassword, changePhone, sendSmsCode } from '@/api/auth';
import { PASSWORD_POLICY_HINT, validatePasswordClient } from '@/lib/passwordPolicy';
import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';

export default function AccountScreen() {
  const { token, user, refreshUser } = useAuth();
  const [refreshing, setRefreshing] = useState(false);
  const [curPwd, setCurPwd] = useState('');
  const [newPwd, setNewPwd] = useState('');
  const [email, setEmail] = useState('');
  const [newPhone, setNewPhone] = useState('');
  const [phoneCode, setPhoneCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [cooldown, setCooldown] = useState(0);

  const onRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await refreshUser();
    } finally {
      setRefreshing(false);
    }
  }, [refreshUser]);

  React.useEffect(() => {
    if (user?.email) setEmail(user.email);
  }, [user?.email]);

  const doChangePassword = async () => {
    if (!token) return;
    const pe = validatePasswordClient(newPwd);
    if (pe) {
      Alert.alert('提示', pe);
      return;
    }
    setBusy(true);
    try {
      const { ok, data } = await changePassword(
        token,
        user?.password_set ? curPwd : undefined,
        newPwd,
      );
      if (!ok || !data.ok) {
        Alert.alert('失败', data.message || '');
        return;
      }
      Alert.alert('成功', data.message || '密码已更新');
      setCurPwd('');
      setNewPwd('');
      await refreshUser();
    } finally {
      setBusy(false);
    }
  };

  const doChangeEmail = async () => {
    if (!token || !email.includes('@')) {
      Alert.alert('提示', '请输入有效邮箱');
      return;
    }
    setBusy(true);
    try {
      const { ok, data } = await changeEmail(token, email);
      if (!ok || !data.ok) {
        Alert.alert('失败', data.message || '');
        return;
      }
      Alert.alert('成功', data.message || '已更新');
      await refreshUser();
    } finally {
      setBusy(false);
    }
  };

  const sendForNewPhone = async () => {
    if (!/^\d{11}$/.test(newPhone.trim())) {
      Alert.alert('提示', '请输入新手机号 11 位');
      return;
    }
    if (cooldown > 0) return;
    setBusy(true);
    try {
      const { ok, data } = await sendSmsCode(newPhone.trim());
      if (!ok || !data.ok) {
        Alert.alert('失败', data.message || '');
        return;
      }
      Alert.alert('提示', data.message || '验证码已发送');
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
    } finally {
      setBusy(false);
    }
  };

  const doChangePhone = async () => {
    if (!token) return;
    if (!/^\d{11}$/.test(newPhone.trim()) || !phoneCode.trim()) {
      Alert.alert('提示', '请填写新手机号与验证码');
      return;
    }
    setBusy(true);
    try {
      const { ok, data } = await changePhone(token, newPhone.trim(), phoneCode.trim());
      if (!ok || !data.ok) {
        Alert.alert('失败', data.message || '');
        return;
      }
      Alert.alert('成功', data.message || '请用新手机号登录');
      setNewPhone('');
      setPhoneCode('');
      await refreshUser();
    } finally {
      setBusy(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={onRefresh} />}>
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>当前资料</Text>
          <Text style={styles.row}>用户名：{user?.username ?? '—'}</Text>
          <Text style={styles.row}>手机：{user?.phone ?? '—'}</Text>
          <Text style={styles.row}>邮箱：{user?.email ?? '—'}</Text>
          <Text style={styles.row}>性别：{user?.gender ?? '—'}</Text>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>修改密码</Text>
          <Text style={styles.policyHint}>{PASSWORD_POLICY_HINT}</Text>
          {user?.password_set ? (
            <TextInput
              style={styles.input}
              placeholder="当前密码"
              placeholderTextColor={UI.muted}
              secureTextEntry
              value={curPwd}
              onChangeText={setCurPwd}
            />
          ) : (
            <Text style={styles.note}>当前账号未设置过密码，可直接设新密码</Text>
          )}
          <TextInput
            style={styles.input}
            placeholder="新密码"
            placeholderTextColor={UI.muted}
            secureTextEntry
            value={newPwd}
            onChangeText={setNewPwd}
          />
          <TouchableOpacity
            style={[styles.btn, busy && styles.btnDisabled]}
            onPress={doChangePassword}
            disabled={busy}>
            {busy ? <ActivityIndicator color="#022c22" /> : <Text style={styles.btnText}>保存密码</Text>}
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>修改邮箱</Text>
          <TextInput
            style={styles.input}
            placeholder="新邮箱"
            placeholderTextColor={UI.muted}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
          />
          <TouchableOpacity style={styles.btn} onPress={doChangeEmail} disabled={busy}>
            <Text style={styles.btnText}>保存邮箱</Text>
          </TouchableOpacity>
        </View>

        <View style={styles.section}>
          <Text style={styles.sectionTitle}>修改手机号</Text>
          <Text style={styles.note}>向新手机号发验证码后提交</Text>
          <TextInput
            style={styles.input}
            placeholder="新手机号"
            placeholderTextColor={UI.muted}
            keyboardType="phone-pad"
            maxLength={11}
            value={newPhone}
            onChangeText={setNewPhone}
          />
          <TouchableOpacity
            style={[styles.secondary, cooldown > 0 && styles.btnDisabled]}
            onPress={sendForNewPhone}
            disabled={busy || cooldown > 0}>
            <Text style={styles.secondaryText}>
              {cooldown > 0 ? `${cooldown}s 后可重发` : '发送验证码到新手机'}
            </Text>
          </TouchableOpacity>
          <TextInput
            style={styles.input}
            placeholder="验证码"
            placeholderTextColor={UI.muted}
            value={phoneCode}
            onChangeText={setPhoneCode}
            keyboardType="number-pad"
          />
          <TouchableOpacity style={styles.btn} onPress={doChangePhone} disabled={busy}>
            <Text style={styles.btnText}>确认换绑手机</Text>
          </TouchableOpacity>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  section: {
    margin: 16,
    padding: 16,
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
  },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: UI.text, marginBottom: 8 },
  policyHint: { fontSize: 11, color: UI.muted, marginBottom: 10, lineHeight: 16 },
  row: { fontSize: 14, color: UI.muted, marginBottom: 6 },
  note: { fontSize: 13, color: UI.muted, marginBottom: 10 },
  input: {
    backgroundColor: UI.bg,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: UI.border,
    padding: 12,
    color: UI.text,
    marginBottom: 10,
  },
  btn: {
    backgroundColor: UI.accent,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: 'center',
    marginTop: 4,
  },
  btnDisabled: { opacity: 0.6 },
  btnText: { color: '#022c22', fontWeight: '600' },
  secondary: {
    backgroundColor: UI.link,
    borderRadius: 10,
    paddingVertical: 12,
    alignItems: 'center',
    marginBottom: 10,
  },
  secondaryText: { color: '#fff', fontWeight: '600' },
});
