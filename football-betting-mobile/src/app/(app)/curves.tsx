import { Image } from 'expo-image';
import React, { useEffect, useState } from 'react';
import DateTimePicker, { DateTimePickerAndroid, type DateTimePickerEvent } from '@react-native-community/datetimepicker';
import {
  ActivityIndicator,
  Alert,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { curveImageUrl, searchCurves, type CurveItem } from '@/api/curves';
import { fetchMembershipStatus } from '@/api/membership';
import { useAuth } from '@/context/AuthContext';
import { UI } from '@/constants/ui';

export default function CurvesScreen() {
  const { token } = useAuth();
  const [date, setDate] = useState('');
  const [team, setTeam] = useState('');
  const [items, setItems] = useState<CurveItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [showDatePickerIOS, setShowDatePickerIOS] = useState(false);
  const [inlineHint, setInlineHint] = useState('');

  const formatYmd = (d: Date) => {
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const day = String(d.getDate()).padStart(2, '0');
    return `${y}${m}${day}`;
  };

  const ymdToDate = (ymd: string): Date => {
    if (!/^\d{8}$/.test(ymd)) return new Date();
    const y = Number(ymd.slice(0, 4));
    const m = Number(ymd.slice(4, 6)) - 1;
    const d = Number(ymd.slice(6, 8));
    return new Date(y, m, d);
  };

  const formatYmdDisplay = (ymd: string) => {
    if (!/^\d{8}$/.test(ymd)) return '请选择日期';
    return `${ymd.slice(0, 4)}年${ymd.slice(4, 6)}月${ymd.slice(6, 8)}日`;
  };

  useEffect(() => {
    if (!token) return;
    (async () => {
      try {
        const { ok, data } = await fetchMembershipStatus(token);
        const isMember = !!(ok && data?.is_member);
        const d = new Date();
        if (!isMember) d.setDate(d.getDate() - 1);
        const ymd = formatYmd(d);
        setDate(ymd);
        setTeam('');
        await onSearch({ dateOverride: ymd, teamOverride: '' });
      } catch {
        const d = new Date();
        d.setDate(d.getDate() - 1);
        const ymd = formatYmd(d);
        setDate(ymd);
        setTeam('');
        await onSearch({ dateOverride: ymd, teamOverride: '' });
      }
    })();
  }, [token]);

  const onSearch = async (opts?: { dateOverride?: string; teamOverride?: string }) => {
    const tk = token;
    if (!tk) {
      Alert.alert('提示', '请先登录');
      return;
    }
    const d = (opts?.dateOverride ?? date).trim();
    const teamValue = (opts?.teamOverride ?? team).trim();
    if (!/^\d{8}$/.test(d)) {
      Alert.alert('提示', '日期须为 YYYYMMDD');
      return;
    }
    setSearching(true);
    setItems([]);
    setInlineHint('');
    try {
      const { ok, status, data } = await searchCurves(tk, d, teamValue);
      if (status === 401) {
        Alert.alert('提示', data.message || '登录已失效，请重新登录');
        return;
      }
      if (data.error) {
        Alert.alert('查询失败', data.error);
        return;
      }
      if (data.member_only && data.message) {
        setInlineHint(data.message);
      }
      const list = data.items || [];
      setItems(list);
      if (list.length === 0 && !data.member_only) {
        setInlineHint(teamValue ? '该日期下没有与该球队相关的曲线图' : '该日期下没有可展示的曲线图');
      } else if (list.length > 0) {
        setInlineHint('');
      }
    } catch {
      Alert.alert('网络错误', '请检查网络与 API 地址');
    } finally {
      setSearching(false);
    }
  };

  const onDateChangeIOS = (event: DateTimePickerEvent, selectedDate?: Date) => {
    if (event.type !== 'set' || !selectedDate) return;
    setDate(formatYmd(selectedDate));
  };

  const openDatePicker = () => {
    const value = ymdToDate(date);
    if (Platform.OS === 'android') {
      DateTimePickerAndroid.open({
        value,
        mode: 'date',
        is24Hour: true,
        onChange: (event, selectedDate) => {
          if (event.type !== 'set' || !selectedDate) return;
          setDate(formatYmd(selectedDate));
        },
      });
      return;
    }
    setShowDatePickerIOS(true);
  };

  const authHeader = token ? { Authorization: `Bearer ${token}` } : undefined;

  return (
    <SafeAreaView style={styles.safe} edges={['bottom']}>
      <View style={styles.page}>
        <View style={styles.form}>
          <Text style={styles.label}>日期</Text>
          <TouchableOpacity style={styles.datePickerBtn} onPress={openDatePicker}>
            <Text style={styles.datePickerText}>{formatYmdDisplay(date)}</Text>
          </TouchableOpacity>
          {showDatePickerIOS && (
            <View style={styles.iosPickerWrap}>
              <View style={styles.iosPickerHeader}>
                <TouchableOpacity onPress={() => setShowDatePickerIOS(false)}>
                  <Text style={styles.iosPickerDone}>完成</Text>
                </TouchableOpacity>
              </View>
              <DateTimePicker
                value={ymdToDate(date)}
                mode="date"
                display="spinner"
                onChange={onDateChangeIOS}
                locale="zh-CN"
                textColor={UI.text}
              />
            </View>
          )}

          <Text style={styles.label}>球队名（选填，主或客，模糊匹配）</Text>
          <TextInput
            style={styles.input}
            value={team}
            onChangeText={setTeam}
            placeholder="留空则查询当天全部"
            placeholderTextColor={UI.muted}
          />

          <TouchableOpacity
            style={[styles.btn, searching && styles.btnDisabled]}
            onPress={onSearch}
            disabled={searching}>
            {searching ? (
              <ActivityIndicator color="#022c22" />
            ) : (
              <Text style={styles.btnText}>搜索</Text>
            )}
          </TouchableOpacity>
          {!!inlineHint && <Text style={styles.inlineHint}>{inlineHint}</Text>}
        </View>

        <ScrollView
          style={styles.resultsScroll}
          contentContainerStyle={styles.resultsContent}
          keyboardShouldPersistTaps="handled">
          {items.map((it) => {
            const uri = curveImageUrl(it.date, it.filename);
            return (
              <View key={`${it.date}-${it.filename}`} style={styles.card}>
                <Text style={styles.cardTitle}>
                  {it.home} VS {it.away}
                </Text>
                <Image
                  source={{ uri, headers: authHeader }}
                  style={styles.img}
                  contentFit="contain"
                  transition={200}
                />
              </View>
            );
          })}
        </ScrollView>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  page: { flex: 1, padding: 16 },
  form: {
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
    padding: 16,
    marginBottom: 12,
  },
  resultsScroll: { flex: 1 },
  resultsContent: { paddingBottom: 32 },
  label: { fontSize: 13, color: UI.muted, marginBottom: 6 },
  input: {
    backgroundColor: UI.bg,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: UI.border,
    padding: 12,
    color: UI.text,
    fontSize: 16,
    marginBottom: 10,
  },
  datePickerBtn: {
    backgroundColor: UI.bg,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: UI.border,
    padding: 12,
    marginBottom: 10,
  },
  datePickerText: { color: UI.text, fontSize: 16 },
  iosPickerWrap: {
    borderWidth: 1,
    borderColor: UI.border,
    borderRadius: 10,
    marginBottom: 10,
    overflow: 'hidden',
    backgroundColor: UI.card,
  },
  iosPickerHeader: {
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: UI.border,
    alignItems: 'flex-end',
  },
  iosPickerDone: { color: UI.accent, fontSize: 15, fontWeight: '600' },
  btn: {
    marginTop: 8,
    backgroundColor: UI.accent,
    borderRadius: 999,
    paddingVertical: 12,
    alignItems: 'center',
  },
  btnDisabled: { opacity: 0.7 },
  btnText: { color: '#022c22', fontWeight: '600', fontSize: 16 },
  inlineHint: { marginTop: 8, fontSize: 12, color: UI.muted },
  card: {
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
    padding: 12,
    marginBottom: 16,
  },
  cardTitle: { color: UI.text, fontSize: 15, fontWeight: '600', marginBottom: 8 },
  img: { width: '100%', height: 380, backgroundColor: UI.bg },
});
