import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RunrateChart from "../components/RunrateChart";
import type { CompanyPayload } from "../types";

const EMPTY: CompanyPayload = {
  slug: "openai", display_name: "OpenAI", note: "",
  series: { official: [], estimated: [], reported: [], target: [], derived: [], monthly: [] },
  valuations: [], products: [], events: [],
  metrics: {
    latest_official: null, latest_estimate: null, official_estimate_gap: null,
    growth_velocity: null, acceleration: { state: "insufficient_data" },
    target_progress: null, valuation_multiple: null, product_contribution: [],
  },
  quality: { official_count: 0, estimate_count: 0, target_count: 0, review_queue_count: 0, uncertain_asof_count: 0, last_collect: null, last_errors: [] },
  freshness: { latest_official_as_of: null, generated_kst: "2026-07-27 00:00" },
};

describe("RunrateChart", () => {
  it("빈 데이터면 안내 메시지", () => {
    render(<RunrateChart cp={EMPTY} />);
    expect(screen.getByText(/표시할 데이터가 없습니다/)).toBeTruthy();
  });

  it("공식 포인트 있으면 svg 렌더", () => {
    const cp: CompanyPayload = {
      ...EMPTY,
      series: { ...EMPTY.series, official: [
        { value_low_usd_bn: 2, value_high_usd_bn: null, qualifier: "exact", as_of_end: "2023-12-31", published_at: "2026-01-18", is_official: 1, metric_type: "arr" },
        { value_low_usd_bn: 20, value_high_usd_bn: null, qualifier: "over", as_of_end: "2025-12-31", published_at: "2026-01-18", is_official: 1, metric_type: "arr" },
      ] },
    };
    const { container } = render(<RunrateChart cp={cp} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });

  it("파생 포인트는 다이아몬드(rect) 마커로 렌더", () => {
    const cp: CompanyPayload = {
      ...EMPTY,
      series: { ...EMPTY.series,
        official: [{ value_low_usd_bn: 20, value_high_usd_bn: null, qualifier: "over", as_of_end: "2025-12-31", published_at: "2026-01-18", is_official: 1, metric_type: "arr" }],
        derived: [{ value_low_usd_bn: 24, value_high_usd_bn: null, qualifier: "derived", as_of_end: "2026-03-31", published_at: "2026-03-31", is_official: 0, is_derived: 1, metric_type: "derived_annualized_revenue", calculation_method: "monthly_revenue_x12" }],
      },
    };
    const { container } = render(<RunrateChart cp={cp} />);
    expect(container.querySelector("rect")).toBeTruthy();   // 파생 마커 존재
  });

  it("기관별 외부추정은 별도 계열 — Funda 는 선 없이 마커만", () => {
    const est = (v: number, d: string, src: string, prec = "day") => ({
      value_low_usd_bn: v, value_high_usd_bn: null, qualifier: "estimate" as const,
      as_of_end: d, published_at: d, is_estimate: 1, metric_type: "arr",
      date_precision: prec, source_name: src, verification_status: "provisional" as const,
    });
    const cp: CompanyPayload = {
      ...EMPTY,
      series: { ...EMPTY.series, estimated: [
        est(33, "2026-05-30", "TickerTrends (OpenAI ARR 추정)"),
        est(42.6, "2026-07-29", "TickerTrends (OpenAI ARR 추정)"),
        est(25, "2026-02-28", "Sacra (OpenAI 매출 추정)"),
        est(49, "2026-07-28", "Funda (Axios 2026-07-28 재인용, 원자료 미확인)", "unknown"),
      ] },
    };
    const { container } = render(<RunrateChart cp={cp} />);
    // Funda 는 정사각 마커(rect) 로만 표시 — 다른 기관과 한 선으로 연결하지 않는다
    expect(container.querySelectorAll("rect").length).toBe(1);
    // TickerTrends 2점만 선(path)으로 연결(Sacra 1점·Funda 는 선 없음)
    expect(container.querySelectorAll("path").length).toBe(1);
    expect(screen.getByText(/Funda 추정 후보/)).toBeTruthy();
  });
});
