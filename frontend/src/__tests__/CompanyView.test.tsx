import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import CompanyView from "../components/CompanyView";
import type { CompanyPayload, Point } from "../types";

const est = (v: number, d: string, src: string, prec = "day"): Point => ({
  value_low_usd_bn: v, value_high_usd_bn: null, qualifier: "estimate",
  as_of_end: d, published_at: d, is_estimate: 1, metric_type: "arr",
  date_precision: prec, source_name: src, verification_status: "provisional",
  source_note: `${src} note`,
});

const OFFICIAL: Point = {
  value_low_usd_bn: 20, value_high_usd_bn: null, qualifier: "over", metric_type: "arr",
  as_of_start: "2025-01-01", as_of_end: "2025-12-31", date_precision: "year",
  published_at: "2026-01-18", is_official: 1, source_name: "OpenAI (공식)",
  verification_status: "corroborated",
};
const TT = est(42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)");
const SACRA = est(25, "2026-02-28", "Sacra (OpenAI 매출 추정)", "month_range");
// Funda 는 원문 표현이 '약 $49B' → qualifier=approximately, 기준일 미공개 → date_precision=unknown
const FUNDA: Point = { ...est(49, "2026-07-28", "Funda (Axios 2026-07-28 재인용, 원자료 미확인)", "unknown"),
                       qualifier: "approximately" };

const CP: CompanyPayload = {
  slug: "openai", display_name: "OpenAI", note: "",
  series: {
    official: [OFFICIAL], estimated: [SACRA, FUNDA, TT], reported: [], target: [],
    derived: [{ value_low_usd_bn: 24, value_high_usd_bn: null, qualifier: "derived",
                as_of_end: "2026-03-31", published_at: "2026-03-31", is_derived: 1,
                metric_type: "derived_annualized_revenue", calculation_method: "monthly_revenue_x12",
                source_name: "OpenAI (월매출 ×12 파생)", verification_status: "corroborated" }],
    monthly: [{ value_low_usd_bn: 2, value_high_usd_bn: null, qualifier: "exact",
                as_of_end: "2026-03-31", published_at: "2026-03-31", is_official: 1,
                metric_type: "monthly_revenue", source_name: "OpenAI (공식)",
                verification_status: "corroborated" }],
  },
  valuations: [], products: [], events: [],
  metrics: {
    latest_official: OFFICIAL, latest_estimate: TT,
    latest_estimates_by_source: [
      { source: "TickerTrends", point: TT },
      { source: "Funda", point: FUNDA },
      { source: "Sacra", point: SACRA },
    ],
    estimate_divergence: {
      high: { source: "Funda", value_usd_bn: 49, as_of: "2026-07-28" },
      low: { source: "Sacra", value_usd_bn: 25, as_of: "2026-02-28" },
      spread_usd_bn: 24, spread_pct: 96, source_count: 3, note: "방법론 확인 필요",
    },
    official_estimate_gap: null, growth_velocity: null,
    acceleration: { state: "insufficient_data" }, target_progress: null,
    valuation_multiple: null, product_contribution: [],
  },
  quality: { official_count: 1, estimate_count: 3, target_count: 0, review_queue_count: 0,
             uncertain_asof_count: 0, last_collect: null, last_errors: [] },
  freshness: { latest_official_as_of: "2025-12-31", generated_kst: "2026-08-02 16:00" },
};

describe("CompanyView", () => {
  it("외부추정을 기관별 카드로 분리 표시(하나로 합치지 않음)", () => {
    render(<CompanyView cp={CP} />);
    expect(screen.getByText("TickerTrends 최신 추정")).toBeTruthy();
    expect(screen.getByText("Sacra 최신 추정")).toBeTruthy();
    // 기준일 미공개(Funda)는 '추정 후보' 로 구분
    expect(screen.getByText("Funda 추정 후보")).toBeTruthy();
    expect(screen.getAllByText("$42.6B").length).toBeGreaterThan(0);
    expect(screen.getAllByText("약 $49.0B").length).toBeGreaterThan(0);
  });

  it("공식·파생·기관별 추정을 나열하고 기관간 편차를 명시", () => {
    render(<CompanyView cp={CP} />);
    expect(screen.getByText("최신 수준 해석")).toBeTruthy();
    expect(screen.getByText(/공식 ARR 최신값/)).toBeTruthy();
    expect(screen.getByText(/파생 연환산\(월매출×12, 공식 ARR 아님\)/)).toBeTruthy();
    expect(screen.getByText(/기관별 최신 추정 편차/)).toBeTruthy();
    expect(screen.getByText(/방법론 확인 필요/)).toBeTruthy();
  });

  it("기준일 미공개 추정은 기준일을 단정하지 않는다", () => {
    render(<CompanyView cp={CP} />);
    expect(screen.getAllByText(/2026-07-28 보도\(기준일 미상\)/).length).toBeGreaterThan(0);
  });
});
