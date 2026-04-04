import { Image } from 'expo-image';
import { useRouter } from 'expo-router';
import React, { useEffect, useState } from 'react';
import DateTimePicker, { DateTimePickerAndroid, type DateTimePickerEvent } from '@react-native-community/datetimepicker';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  Platform,
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
  const PAGE_SIZE = 3;
  const router = useRouter();
  const { token, clearSession } = useAuth();
  const [date, setDate] = useState('');
  const [team, setTeam] = useState('');
  const [items, setItems] = useState<CurveItem[]>([]);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);
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
    setVisibleCount(PAGE_SIZE);
    setInlineHint('');
    try {
      const { ok, status, data } = await searchCurves(tk, d, teamValue);
      if (status === 401) {
        await clearSession();
        Alert.alert('提示', '账号已在其他设备登录或登录已过期，请重新登录', [
          { text: '确定', onPress: () => router.replace('/(auth)/login') },
        ]);
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
      setVisibleCount(Math.min(PAGE_SIZE, list.length || PAGE_SIZE));
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
  const visibleItems = items.slice(0, visibleCount);
  const hasMore = visibleCount < items.length;

  const loadMore = () => {
    if (!hasMore || searching) return;
    setVisibleCount((prev) => Math.min(prev + PAGE_SIZE, items.length));
  };

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

        <FlatList
          style={styles.resultsScroll}
          contentContainerStyle={styles.resultsContent}
          data={visibleItems}
          keyExtractor={(it) => `${it.date}-${it.filename}`}
          keyboardShouldPersistTaps="handled"
          onEndReachedThreshold={0.35}
          onEndReached={loadMore}
          initialNumToRender={PAGE_SIZE}
          windowSize={4}
          removeClippedSubviews={false}
          renderItem={({ item: it }) => {
            const uri = curveImageUrl(it.date, it.filename);
            return (
              <View style={styles.card}>
                <Text style={styles.cardTitle}>
                  {it.home} VS {it.away}
                </Text>
                <View style={styles.imgWrap}>
                  <Image
                    source={{ uri, headers: authHeader }}
                    style={styles.img}
                    contentFit="contain"
                    transition={200}
                  />
                </View>
              </View>
            );
          }}
          ListFooterComponent={
            hasMore ? (
              <TouchableOpacity style={styles.loadMoreBtn} onPress={loadMore}>
                <Text style={styles.loadMoreText}>继续加载更多...</Text>
              </TouchableOpacity>
            ) : null
          }
        />
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: UI.bg },
  page: { flex: 1, paddingHorizontal: 8, paddingTop: 10, paddingBottom: 8 },
  form: {
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
    paddingHorizontal: 12,
    paddingVertical: 10,
    marginBottom: 8,
  },
  resultsScroll: { flex: 1 },
  resultsContent: { paddingBottom: 16 },
  label: { fontSize: 12, color: UI.muted, marginBottom: 4 },
  input: {
    backgroundColor: UI.bg,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: UI.border,
    paddingHorizontal: 10,
    paddingVertical: 9,
    color: UI.text,
    fontSize: 15,
    marginBottom: 8,
  },
  datePickerBtn: {
    backgroundColor: UI.bg,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: UI.border,
    paddingHorizontal: 10,
    paddingVertical: 9,
    marginBottom: 8,
  },
  datePickerText: { color: UI.text, fontSize: 15 },
  iosPickerWrap: {
    borderWidth: 1,
    borderColor: UI.border,
    borderRadius: 10,
    marginBottom: 8,
    overflow: 'hidden',
    backgroundColor: UI.card,
  },
  iosPickerHeader: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderBottomWidth: 1,
    borderBottomColor: UI.border,
    alignItems: 'flex-end',
  },
  iosPickerDone: { color: UI.accent, fontSize: 15, fontWeight: '600' },
  btn: {
    marginTop: 4,
    backgroundColor: UI.accent,
    borderRadius: 999,
    paddingVertical: 9,
    alignItems: 'center',
  },
  btnDisabled: { opacity: 0.7 },
  btnText: { color: '#022c22', fontWeight: '600', fontSize: 15 },
  inlineHint: { marginTop: 6, fontSize: 11, color: UI.muted },
  card: {
    backgroundColor: UI.card,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: UI.border,
    padding: 8,
    marginBottom: 10,
    alignItems: 'stretch',
    overflow: 'visible',
  },
  cardTitle: { color: UI.text, fontSize: 16, fontWeight: '600', marginBottom: 8, alignSelf: 'stretch' },
  imgWrap: {
    width: '100%',
    alignSelf: 'stretch',
    overflow: 'visible',
  },
  img: {
    width: '100%',
    aspectRatio: 9 / 17,
    backgroundColor: UI.bg,
  },
  loadMoreBtn: {
    alignSelf: 'center',
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 999,
    borderWidth: 1,
    borderColor: UI.border,
    marginTop: 2,
    marginBottom: 10,
  },
  loadMoreText: { color: UI.muted, fontSize: 12 },
});
