// 관측치를 화면에 어떤 순서로 놓을 것인가 — 차트 위치와 타임라인 정렬이 같은 규칙을 쓴다.
//
// 날짜 필드가 넷이라 헷갈리기 쉽다.
//   as_of_start / as_of_end  그 수치가 가리키는 실제 기간
//   published_at             그 수치가 세상에 나온 날
// 기준일 정렬·차트 위치는 기간의 끝(canonical)을 쓰고, 발표일 정렬은 published_at 을 쓴다.
// month_range·year 처럼 기간이 뭉뚱그려진 값도 화면에는 범위로 보여주되,
// 정렬에는 canonical 한 날짜 하나만 쓴다 — 임의의 하루를 만들어 표시하지 않는다.

import type { Point } from "./types";
import { dateToUtcEpoch } from "./dateutil";

/** 정렬·배치에 쓰는 canonical 날짜(문자열). 표시용이 아니다. */
export function canonicalDate(p: Point): string | null {
  return p.as_of_end || p.as_of_start || p.published_at || null;
}

/** 정렬·배치에 쓰는 canonical epoch. 타임존에 밀리지 않게 UTC 자정으로 고정한다. */
export function canonicalEpoch(p: Point): number | null {
  return dateToUtcEpoch(canonicalDate(p));
}

export type SortKey = "as_of" | "published";
export type SortDir = "desc" | "asc";

function keyOf(p: Point, key: SortKey): string {
  return (key === "published" ? p.published_at : canonicalDate(p)) || "";
}

/**
 * 같은 날짜가 겹칠 때 순서가 흔들리지 않게 한다.
 * 1차 선택한 기준 → 발표일 → created_at 순으로 보고, 그래도 같으면 원래 순서를 지킨다
 * (Array.prototype.sort 는 안정 정렬이다).
 */
export function sortPoints(points: Point[], key: SortKey, dir: SortDir): Point[] {
  const sign = dir === "asc" ? 1 : -1;
  return [...points].sort((a, b) => {
    const primary = keyOf(a, key).localeCompare(keyOf(b, key));
    if (primary !== 0) return primary * sign;
    const pub = (a.published_at || "").localeCompare(b.published_at || "");
    if (pub !== 0) return pub * sign;
    return ((a.created_at || "").localeCompare(b.created_at || "")) * sign;
  });
}
