import { describe, it, expect } from "vitest";
import { render, screen, fireEvent, within } from "@testing-library/react";
import RunrateChart from "../components/RunrateChart";
import type { CompanyPayload, Point } from "../types";

const BASE: CompanyPayload = {
  slug: "anthropic", display_name: "Anthropic", note: "",
  series: { official: [], estimated: [], reported: [], target: [], derived: [], monthly: [] },
  valuations: [], products: [], events: [],
  metrics: {
    latest_official: null, latest_estimate: null, official_estimate_gap: null,
    growth_velocity: null, acceleration: { state: "insufficient_data" },
    target_progress: null, valuation_multiple: null, product_contribution: [],
  },
  quality: { official_count: 0, estimate_count: 0, target_count: 0, review_queue_count: 0, uncertain_asof_count: 0, last_collect: null, last_errors: [] },
  freshness: { latest_official_as_of: null, generated_kst: "2026-08-19 00:00" },
};

const OFFICIAL: Point = {
  value_low_usd_bn: 47, value_high_usd_bn: null, qualifier: "over",
  as_of_start: "2026-05-01", as_of_end: "2026-05-28", date_precision: "month_range",
  published_at: "2026-05-28", source_name: "Anthropic (Series H)",
  source_url: "https://www.anthropic.com/news/series-h", source_type: "official_current",
  is_official: 1, verification_status: "verified", metric_type: "revenue_run_rate",
};

function withPoints(over: Partial<CompanyPayload["series"]>): CompanyPayload {
  return { ...BASE, series: { ...BASE.series, ...over } };
}

function markers(container: HTMLElement) {
  return container.querySelectorAll("g.marker");
}

describe("차트 tooltip", () => {
  it("점에 마우스를 올리면 값과 기준일이 뜬다", () => {
    const { container } = render(<RunrateChart cp={withPoints({ official: [OFFICIAL] })} />);
    fireEvent.mouseEnter(markers(container)[0]);

    const tip = within(screen.getByRole("tooltip"));
    expect(tip.getByText(/\$47\.0B 이상/)).toBeTruthy();
    expect(tip.getByText("발표일")).toBeTruthy();
    expect(tip.getByText("2026-05-28")).toBeTruthy();   // 발표일 칸
  });

  it("month_range 기준일은 하루로 단정하지 않고 '월 중' 으로 보여준다", () => {
    const { container } = render(<RunrateChart cp={withPoints({ official: [OFFICIAL] })} />);
    fireEvent.mouseEnter(markers(container)[0]);

    expect(within(screen.getByRole("tooltip")).getByText("2026년 5월 중")).toBeTruthy();
  });

  it("마우스를 떼면 사라진다", () => {
    const { container } = render(<RunrateChart cp={withPoints({ official: [OFFICIAL] })} />);
    fireEvent.mouseEnter(markers(container)[0]);
    fireEvent.mouseLeave(markers(container)[0]);

    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("provisional 은 '원문 미확인', corroborated 는 '간접 확인' 으로 적는다", () => {
    const prov: Point = { ...OFFICIAL, is_official: 0, is_estimate: 1, verification_status: "provisional",
                          source_name: "TickerTrends", as_of_end: "2026-06-15", date_precision: "day",
                          source_note: "원자료 미확인" };
    const corr: Point = { ...OFFICIAL, is_official: 0, verification_status: "corroborated",
                          source_name: "CNBC", as_of_end: "2026-07-31", date_precision: "day" };
    const one = render(<RunrateChart cp={withPoints({ estimated: [prov] })} />);
    fireEvent.mouseEnter(markers(one.container)[0]);
    expect(within(screen.getByRole("tooltip")).getByText("원문 미확인")).toBeTruthy();
    one.unmount();

    const two = render(<RunrateChart cp={withPoints({ reported: [corr] })} />);
    fireEvent.mouseEnter(markers(two.container)[0]);
    expect(within(screen.getByRole("tooltip")).getByText("간접 확인")).toBeTruthy();
  });

  it("파생값은 공식 ARR 이 아니라는 설명을 붙인다", () => {
    const derived: Point = { ...OFFICIAL, is_official: 0, is_derived: 1, qualifier: "derived",
                             as_of_end: "2026-03-31", date_precision: "day",
                             metric_type: "derived_annualized_revenue", calculation_method: "monthly_revenue_x12",
                             source_name: "OpenAI (월매출 ×12 파생)" };
    const { container } = render(<RunrateChart cp={withPoints({ derived: [derived] })} />);
    fireEvent.mouseEnter(markers(container)[0]);

    const tip = within(screen.getByRole("tooltip"));
    expect(tip.getByText(/월 매출을 12배 한 계산값/)).toBeTruthy();
    expect(tip.getByText(/회사가 발표한 ARR 이 아닙니다/)).toBeTruthy();
  });

  it("원문 링크를 tooltip 안에서 열 수 있다", () => {
    const { container } = render(<RunrateChart cp={withPoints({ official: [OFFICIAL] })} />);
    fireEvent.mouseEnter(markers(container)[0]);

    const link = screen.getByText("원문 보기").closest("a");
    expect(link?.getAttribute("href")).toBe("https://www.anthropic.com/news/series-h");
  });

  it("모바일에서는 점을 탭하면 열리고 닫기 전까지 남는다", () => {
    const { container } = render(<RunrateChart cp={withPoints({ official: [OFFICIAL] })} />);
    const marker = markers(container)[0];

    fireEvent.click(marker);
    fireEvent.mouseLeave(marker);          // 탭한 뒤에는 마우스가 떠나도 남아 있어야 한다
    expect(screen.getByRole("tooltip")).toBeTruthy();

    fireEvent.click(screen.getByLabelText("툴팁 닫기"));
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("겹쳐 있는 서로 다른 계열도 각자의 tooltip 을 낸다", () => {
    // 같은 날짜·같은 값이라 화면에서 겹친다. 그래도 잡히는 점의 정보가 떠야 한다.
    const a: Point = { ...OFFICIAL, source_name: "Anthropic (Series H)", as_of_end: "2026-05-28", date_precision: "day" };
    const b: Point = { ...OFFICIAL, is_official: 0, is_estimate: 1, source_name: "TickerTrends",
                       as_of_end: "2026-05-28", date_precision: "day", verification_status: "provisional" };
    const { container } = render(<RunrateChart cp={withPoints({ official: [a], estimated: [b] })} />);
    const ms = markers(container);

    fireEvent.mouseEnter(ms[0]);
    expect(within(screen.getByRole("tooltip")).getByText(/Anthropic \(Series H\)/)).toBeTruthy();
    fireEvent.mouseLeave(ms[0]);

    fireEvent.mouseEnter(ms[1]);
    expect(within(screen.getByRole("tooltip")).getByText("TickerTrends")).toBeTruthy();
  });

  it("date-only 값은 타임존에 밀리지 않는다", () => {
    const { container } = render(<RunrateChart cp={withPoints({ official: [
      { ...OFFICIAL, as_of_start: "2026-05-28", as_of_end: "2026-05-28", date_precision: "day" },
      { ...OFFICIAL, value_low_usd_bn: 65, as_of_start: "2026-07-31", as_of_end: "2026-07-31",
        date_precision: "day", published_at: "2026-08-17" },
    ] })} />);

    // 축 양끝 라벨이 입력한 날짜 그대로여야 한다(하루 밀리면 05-27 / 07-30 이 된다)
    expect(container.textContent).toContain("2026-05-28");
    expect(container.textContent).toContain("2026-07-31");
  });
});
