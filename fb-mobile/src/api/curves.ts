import { apiFetch } from '@/api/client';
import { getApiBaseUrl } from '@/api/config';

export type CurveItem = { date: string; home: string; away: string; filename: string };

export async function fetchCurveDates() {
  return apiFetch<{ dates: string[] }>('/api/curves/dates', { method: 'GET' });
}

export async function searchCurves(token: string, date: string, team: string) {
  const q = new URLSearchParams({ date: date.trim(), team: team.trim() });
  return apiFetch<{
    error?: string;
    date?: string;
    items?: CurveItem[];
    member_only?: boolean;
    message?: string;
  }>(`/api/curves/search?${q.toString()}`, { method: 'GET', token });
}

export function curveImageUrl(date: string, filename: string): string {
  const base = getApiBaseUrl();
  return `${base}/api/curves/img/${date}/${encodeURIComponent(filename)}`;
}
