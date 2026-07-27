import { describe, it, expect } from "vitest";
import { usdBn, pct, pointValueText, qualifierLabel } from "../format";
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

  it("qualifierLabel", () => {
    expect(qualifierLabel("over")).toBe("이상");
    expect(qualifierLabel("estimate")).toBe("추정");
  });
});
