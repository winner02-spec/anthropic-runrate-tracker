import { describe, it, expect } from "vitest";
import { timelinePoints } from "../filters";
import type { CompanyPayload, Point } from "../types";

const p = (over: Partial<Point>): Point => ({
  value_low_usd_bn: 1, value_high_usd_bn: null, qualifier: "exact",
  as_of_end: "2026-05-28", published_at: "2026-05-28", ...over,
});

const OFFICIAL = p({ is_official: 1, source_name: "공식" });
const REPORTED = p({ source_name: "보도" });
const ESTIMATE = p({ is_estimate: 1, source_name: "TickerTrends" });
const DERIVED = p({ is_derived: 1, source_name: "파생" });
const TARGET = p({ is_target: 1, source_name: "목표" });

const CP = {
  series: { official: [OFFICIAL], reported: [REPORTED], estimated: [ESTIMATE],
            derived: [DERIVED], target: [TARGET], monthly: [] },
} as unknown as CompanyPayload;

const names = (f: Parameters<typeof timelinePoints>[1]) =>
  timelinePoints(CP, f).map((x) => x.source_name);

describe("타임라인 필터", () => {
  it("공식만 고르면 공식만 남는다", () => {
    expect(names("official")).toEqual(["공식"]);
  });

  it("공식+매체는 보도까지 남긴다", () => {
    expect(names("official_reported")).toEqual(["공식", "보도"]);
  });

  it("파생값 포함은 외부추정을 끌어오지 않는다", () => {
    expect(names("derived")).toEqual(["공식", "보도", "파생"]);
  });

  it("전체는 목표까지 포함한다", () => {
    expect(names("all")).toEqual(["공식", "보도", "TickerTrends", "파생", "목표"]);
  });

  it("목표는 목표 포함·전체에서만 보인다", () => {
    expect(names("target")).toContain("목표");
    expect(names("official")).not.toContain("목표");
    expect(names("estimates")).not.toContain("목표");
  });
});
