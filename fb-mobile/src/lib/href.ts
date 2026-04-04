import type { Href } from 'expo-router';

/** 规避 expo typed routes 与文件不同步时的 Href / router 校验 */
export function href(path: string): Href {
  return path as unknown as Href;
}
