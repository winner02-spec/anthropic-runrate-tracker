import { describe, it, expect } from "vitest";
import { usdBn, pct, pointValueText, pointDate, qualifierLabel } from "../format";
import type { Point } from "../types";

const mk = (over: Partial<Point>): Point => ({
  value_low_usd_bn: 14, value_high_usd_bn: null, qualifier: "exact", ...over,
});

describe("format", () => {
  it("usdBn / pct", () => {
    expect(usdBn(14)).toBe("$14.0B");
    expect(usdBn(null)).toBe("—");
    expect(pct(44.25)).toBe("+44.3%");
    expect(pct(-3)).toBe("-3.0%");
  });

  it("qualifier 반영 값 표기", () => {
    expect(pointValueText(mk({ qualifier: "exact" }))).toBe("$14.0B");
    expect(pointValueText(mk({ qualifier: "over", value_low_usd_bn: 30 }))).toBe("$30.0B 이상");
    expect(pointValueText(mk({ qualifier: "approximately" }))).toBe("약 $14.0B");
    expect(pointValueText(mk({ qualifier: "range", value_low_usd_bn: 20, value_high_usd_bn: 26 }))).toBe("$20.0B–$26.0B");
    expect(pointValueText(mk({ qualifier: "target", value_low_usd_bn: 20 }))).toBe("목표 $20.0B");
  });

  it("기준일 미공개(date_precision=unknown)는 기준일을 단정하지 않는다", () => {
    const p = mk({ date_precision: "unknown", as_of_end: "2026-07-28", published_at: "2026-07-28" });
    expect(pointDate(p)).toBe("2026-07-28 보도(기준일 미상)");
    // 월범위·일자 정밀도는 기존 표기 유지
    expect(pointDate(mk({ date_precision: "month_range", as_of_start: "2026-02-01", as_of_end: "2026-02-28" })))
      .toBe("2026년 2월 중");
    expect(pointDate(mk({ date_precision: "day", as_of_end: "2026-07-29" }))).toBe("2026-07-29");
  });

  it("qualifierLabel", () => {
    expect(qualifierLabel("over")).toBe("이상");
    expect(qualifierLabel("estimate")).toBe("추정");
  });
});
