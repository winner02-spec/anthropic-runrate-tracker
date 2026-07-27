// date-only(YYYY-MM-DD) 값을 '타임존 무관'하게 다룬다.
// 버그: new Date("2026-02-12") 또는 로컬 파싱 후 toISOString() 을 섞으면
//       사용자 타임존(예: KST)에서 하루 밀려 보인다. → 항상 UTC 자정 기준으로 통일.

export function dateToUtcEpoch(d?: string | null): number | null {
  if (!d) return null;
  const t = Date.parse(d.slice(0, 10) + "T00:00:00Z"); // 'Z' = UTC 자정으로 고정
  return Number.isNaN(t) ? null : t;
}

// UTC epoch → 'YYYY-MM-DD' (브라우저 타임존과 무관하게 동일)
export function epochToYmd(e: number): string {
  return new Date(e).toISOString().slice(0, 10);
}

// date-only 문자열은 변환 없이 날짜 자체 보존
export function ymd(d?: string | null): string {
  return d ? d.slice(0, 10) : "—";
}
