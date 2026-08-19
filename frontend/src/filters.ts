// 어떤 관측치를 보여줄 것인가 — 차트와 타임라인이 같은 판정을 쓴다.
// 둘이 따로 판정하면 차트에는 있는 점이 타임라인에는 없는 일이 생긴다.

import type { CompanyPayload, Point } from "./types";

export type Filter = "all" | "official" | "official_reported" | "estimates" | "derived" | "target";

export const FILTERS: Array<[Filter, string]> = [
  ["all", "전체"], ["official", "공식만"], ["official_reported", "공식+매체"],
  ["estimates", "외부추정 포함"], ["derived", "파생값 포함"], ["target", "목표 포함"],
];

export type SKind =
  | "official_current" | "official_retro" | "reported" | "tickertrends" | "yipit"
  | "sacra" | "funda" | "estimate" | "derived";

export const ESTIMATE_KINDS: SKind[] = ["tickertrends", "yipit", "sacra", "funda", "estimate"];

/** 이 점이 어느 계열인가. 목표는 별도로 다루므로 null. */
export function classify(p: Point): SKind | null {
  if (p.is_derived) return "derived";
  const src = (p.source_name || "").toLowerCase();
  if (p.is_official) return p.source_type === "official_retrospective" ? "official_retro" : "official_current";
  if (p.is_estimate) {
    if (src.includes("tickertrends")) return "tickertrends";
    if (src.includes("yipit")) return "yipit";
    if (src.includes("sacra")) return "sacra";
    if (src.includes("funda")) return "funda";
    return "estimate";
  }
  if (p.is_target) return null;
  return "reported";
}

export function visibleKinds(f: Filter): Set<SKind> {
  if (f === "official") return new Set<SKind>(["official_current", "official_retro"]);
  if (f === "official_reported") return new Set<SKind>(["official_current", "official_retro", "reported"]);
  if (f === "derived") return new Set<SKind>(["official_current", "official_retro", "reported", "derived"]);
  return new Set<SKind>(["official_current", "official_retro", "reported", ...ESTIMATE_KINDS, "derived"]);
}

export function showsTarget(f: Filter): boolean {
  return f === "all" || f === "target";
}

/**
 * 타임라인에 남길 점들. 필터가 먼저고 정렬은 그다음이다 —
 * 걸러 낸 뒤 남은 것에 순서를 매긴다.
 *
 * 월 매출은 연환산 축과 스케일이 달라 차트에서는 빼지만, 타임라인은 목록이라 그대로 싣는다.
 */
export function timelinePoints(cp: CompanyPayload, f: Filter): Point[] {
  const kinds = visibleKinds(f);
  const out: Point[] = [];
  for (const p of [...cp.series.official, ...cp.series.reported, ...cp.series.estimated,
                   ...cp.series.derived, ...cp.series.monthly]) {
    const k = classify(p);
    if (k && kinds.has(k)) out.push(p);
    else if (!k && showsTarget(f)) out.push(p);
  }
  if (showsTarget(f)) out.push(...cp.series.target);
  return out;
}
