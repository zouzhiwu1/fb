import AsyncStorage from '@react-native-async-storage/async-storage';
import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';

import type { UserDto } from '@/api/auth';
import { fetchMe } from '@/api/auth';

const TOKEN_KEY = 'football_platform_token';
const USER_KEY = 'football_platform_user';

type AuthContextValue = {
  token: string | null;
  user: UserDto | null;
  ready: boolean;
  setSession: (token: string, user: UserDto) => Promise<void>;
  clearSession: () => Promise<void>;
  refreshUser: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<UserDto | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [t, u] = await Promise.all([
          AsyncStorage.getItem(TOKEN_KEY),
          AsyncStorage.getItem(USER_KEY),
        ]);
        if (cancelled) return;
        setToken(t);
        if (u) {
          try {
            setUser(JSON.parse(u) as UserDto);
          } catch {
            setUser(null);
          }
        }
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const setSession = useCallback(async (newToken: string, newUser: UserDto) => {
    setToken(newToken);
    setUser(newUser);
    await AsyncStorage.multiSet([
      [TOKEN_KEY, newToken],
      [USER_KEY, JSON.stringify(newUser)],
    ]);
  }, []);

  const clearSession = useCallback(async () => {
    setToken(null);
    setUser(null);
    await AsyncStorage.multiRemove([TOKEN_KEY, USER_KEY]);
  }, []);

  const refreshUser = useCallback(async () => {
    if (!token) return;
    const { ok, data } = await fetchMe(token);
    if (ok && data.ok && data.user) {
      setUser(data.user);
      await AsyncStorage.setItem(USER_KEY, JSON.stringify(data.user));
    }
  }, [token]);

  const value = useMemo(
    () => ({
      token,
      user,
      ready,
      setSession,
      clearSession,
      refreshUser,
    }),
    [token, user, ready, setSession, clearSession, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return ctx;
}
