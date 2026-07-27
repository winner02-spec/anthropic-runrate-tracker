import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import RunrateChart from "../components/RunrateChart";
import type { Dashboard } from "../types";

const EMPTY: Dashboard = {
  display_name: "x", note: "",
  series: { official: [], estimated: [], reported: [], target: [] },
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
    render(<RunrateChart data={EMPTY} />);
    expect(screen.getByText(/표시할 공식\/추정 데이터가 아직 없습니다/)).toBeTruthy();
  });

  it("공식 포인트 있으면 svg 렌더", () => {
    const d: Dashboard = {
      ...EMPTY,
      series: { ...EMPTY.series, official: [
        { value_low_usd_bn: 14, value_high_usd_bn: null, qualifier: "exact", as_of_end: "2026-02-12", published_at: "2026-02-12", is_official: 1 },
        { value_low_usd_bn: 47, value_high_usd_bn: null, qualifier: "over", as_of_end: "2026-05-15", published_at: "2026-05-29", is_official: 1 },
      ] },
    };
    const { container } = render(<RunrateChart data={d} />);
    expect(container.querySelector("svg")).toBeTruthy();
  });
});
