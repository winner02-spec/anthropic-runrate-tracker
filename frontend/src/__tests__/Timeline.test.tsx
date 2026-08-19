import { describe, it, expect, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Timeline from "../components/Timeline";
import { sortPoints } from "../pointsort";
import type { Point } from "../types";

// 기준일과 발표일이 서로 다른 순서가 되도록 일부러 엇갈리게 둔다.
// 두 정렬이 같은 결과를 내면 무엇으로 정렬했는지 알 수 없다.
const A: Point = { value_low_usd_bn: 30, value_high_usd_bn: null, qualifier: "over",
  as_of_start: "2026-04-06", as_of_end: "2026-04-06", published_at: "2026-04-06",
  source_name: "A출처", evidence_text: "근거 A", is_official: 1, date_precision: "day" };
const B: Point = { value_low_usd_bn: 47, value_high_usd_bn: null, qualifier: "over",
  as_of_start: "2026-05-28", as_of_end: "2026-05-28", published_at: "2026-05-28",
  source_name: "B출처", evidence_text: "근거 B", is_official: 1, date_precision: "day" };
const C: Point = { value_low_usd_bn: 65, value_high_usd_bn: null, qualifier: "over",
  as_of_start: "2026-07-31", as_of_end: "2026-07-31", published_at: "2026-08-17",
  source_name: "C출처", evidence_text: "근거 C", is_official: 0, date_precision: "day" };

const ALL = [A, B, C];

function sourceOrder(): string[] {
  return Array.from(document.querySelectorAll("tbody tr"))
    .map((tr) => tr.querySelectorAll("td")[4]?.textContent ?? "");
}

describe("업데이트 타임라인 정렬", () => {
  beforeEach(() => localStorage.clear());

  it("기본은 기준일 최신순", () => {
    render(<Timeline points={ALL} />);
    expect(sourceOrder()).toEqual(["C출처", "B출처", "A출처"]);
    expect((screen.getByLabelText("정렬 기준") as HTMLSelectElement).value).toBe("as_of");
    expect((screen.getByLabelText("정렬 방향") as HTMLSelectElement).value).toBe("desc");
  });

  it("기준일 오래된순", () => {
    render(<Timeline points={ALL} />);
    fireEvent.change(screen.getByLabelText("정렬 방향"), { target: { value: "asc" } });
    expect(sourceOrder()).toEqual(["A출처", "B출처", "C출처"]);
  });

  it("발표일 최신순", () => {
    render(<Timeline points={ALL} />);
    fireEvent.change(screen.getByLabelText("정렬 기준"), { target: { value: "published" } });
    expect(sourceOrder()).toEqual(["C출처", "B출처", "A출처"]);
  });

  it("발표일 오래된순", () => {
    render(<Timeline points={ALL} />);
    fireEvent.change(screen.getByLabelText("정렬 기준"), { target: { value: "published" } });
    fireEvent.change(screen.getByLabelText("정렬 방향"), { target: { value: "asc" } });
    expect(sourceOrder()).toEqual(["A출처", "B출처", "C출처"]);
  });

  it("기준일과 발표일이 엇갈리면 결과가 달라진다", () => {
    // 기준일은 빠르지만 발표는 늦은 값. 두 정렬이 다른 답을 내야 한다.
    const late: Point = { ...A, as_of_end: "2026-01-31", published_at: "2026-09-01", source_name: "늦게발표" };
    render(<Timeline points={[...ALL, late]} />);
    expect(sourceOrder()[3]).toBe("늦게발표");            // 기준일 최신순 → 맨 뒤
    fireEvent.change(screen.getByLabelText("정렬 기준"), { target: { value: "published" } });
    expect(sourceOrder()[0]).toBe("늦게발표");            // 발표일 최신순 → 맨 앞
  });

  it("헤더를 눌러도 정렬이 바뀌고 방향 표시가 붙는다", () => {
    render(<Timeline points={ALL} />);
    expect(screen.getByRole("button", { name: /기준일/ }).textContent).toContain("↓");

    fireEvent.click(screen.getByRole("button", { name: /발표일/ }));
    expect(screen.getByRole("button", { name: /발표일/ }).textContent).toContain("↓");

    fireEvent.click(screen.getByRole("button", { name: /발표일/ }));   // 같은 헤더 → 방향만 뒤집기
    expect(screen.getByRole("button", { name: /발표일/ }).textContent).toContain("↑");
    expect(sourceOrder()).toEqual(["A출처", "B출처", "C출처"]);
  });

  it("고른 정렬이 새로고침 뒤에도 남는다", () => {
    const first = render(<Timeline points={ALL} />);
    fireEvent.change(screen.getByLabelText("정렬 기준"), { target: { value: "published" } });
    fireEvent.change(screen.getByLabelText("정렬 방향"), { target: { value: "asc" } });
    first.unmount();

    render(<Timeline points={ALL} />);   // 다시 그린다 = 새로고침
    expect((screen.getByLabelText("정렬 기준") as HTMLSelectElement).value).toBe("published");
    expect((screen.getByLabelText("정렬 방향") as HTMLSelectElement).value).toBe("asc");
  });

  it("저장소가 깨져 있어도 기본값으로 뜬다", () => {
    localStorage.setItem("runrate.timelineSort", "{망가진 값");
    render(<Timeline points={ALL} />);
    expect((screen.getByLabelText("정렬 기준") as HTMLSelectElement).value).toBe("as_of");
  });

  it("필터로 걸러 낸 뒤 남은 것만 정렬한다", () => {
    render(<Timeline points={[A, B]} />);
    expect(sourceOrder()).toEqual(["B출처", "A출처"]);
    expect(screen.queryByText("C출처")).toBeNull();
  });

  it("빈 목록이면 안내만 보여준다", () => {
    render(<Timeline points={[]} />);
    expect(screen.getByText(/표시할 데이터가 없습니다/)).toBeTruthy();
  });
});

describe("같은 날짜 정렬", () => {
  it("날짜가 같으면 발표일 → created_at 순으로 안정적으로 놓인다", () => {
    const base = { value_low_usd_bn: 1, value_high_usd_bn: null, qualifier: "exact" as const,
                   as_of_end: "2026-05-28", as_of_start: "2026-05-28", date_precision: "day" };
    const x: Point = { ...base, published_at: "2026-05-28", created_at: "2026-05-28 09:00", source_name: "먼저" };
    const y: Point = { ...base, published_at: "2026-05-28", created_at: "2026-05-28 10:00", source_name: "나중" };

    expect(sortPoints([y, x], "as_of", "asc").map((p) => p.source_name)).toEqual(["먼저", "나중"]);
    expect(sortPoints([x, y], "as_of", "asc").map((p) => p.source_name)).toEqual(["먼저", "나중"]);
  });

  it("date-only 문자열이 타임존에 밀리지 않는다", () => {
    const p: Point = { value_low_usd_bn: 1, value_high_usd_bn: null, qualifier: "exact",
                       as_of_start: "2026-05-01", as_of_end: "2026-05-28", date_precision: "month_range",
                       published_at: "2026-05-28", source_name: "S", evidence_text: "e" };
    render(<Timeline points={[p]} />);
    const cells = document.querySelectorAll("tbody tr td");
    expect(cells[0].textContent).toBe("2026-05-28");        // 발표일 그대로
    expect(cells[1].textContent).toBe("2026년 5월 중");      // 월범위는 하루로 단정하지 않는다
  });
});
