import type { Point, Qualifier } from "./types";

export function usdBn(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `$${v.toFixed(digits)}B`;
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  return `${v >= 0 ? "+" : ""}${v.toFixed(digits)}%`;
}

const QUALIFIER_LABEL: Record<Qualifier, string> = {
  exact: "정확",
  approximately: "약",
  approaching: "근접",
  over: "이상",
  range: "범위",
  target: "목표",
  estimate: "추정",
  reported: "보도",
  derived: "파생",
};

export function qualifierLabel(q: Qualifier | undefined): string {
  return q ? QUALIFIER_LABEL[q] ?? q : "";
}

// qualifier 를 반영한 값 표기: 범위는 low–high, over 는 '이상', approximately 는 '약'
export function pointValueText(p: Point): string {
  const lo = p.value_low_usd_bn;
  const hi = p.value_high_usd_bn;
  if (lo === null || lo === undefined) return "—";
  if (p.qualifier === "range" && hi != null) return `${usdBn(lo)}–${usdBn(hi)}`;
  if (p.qualifier === "over") return `${usdBn(lo)} 이상`;
  if (p.qualifier === "approaching") return `${usdBn(lo)} 근접`;
  if (p.qualifier === "approximately") return `약 ${usdBn(lo)}`;
  if (p.qualifier === "target") return `목표 ${usdBn(lo)}`;
  if (p.qualifier === "derived") return `${usdBn(lo)} (파생)`;
  return usdBn(lo);
}

export function pointDate(p: Point): string {
  // 월범위(불확실) 기준일은 'YYYY년 M월 중' 으로 표시(임의 단일일로 단정하지 않음)
  if (p.date_precision === "month_range") {
    const ref = p.as_of_start || p.as_of_end;
    if (ref) {
      const [y, mo] = ref.split("-");
      return `${y}년 ${Number(mo)}월 중`;
    }
  }
  if (p.as_of_start && p.as_of_end && p.as_of_start !== p.as_of_end)
    return `${p.as_of_start}~${p.as_of_end}`;
  return p.as_of_end || p.as_of_start || p.published_at || "—";
}
