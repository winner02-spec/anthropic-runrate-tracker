import { describe, it, expect } from "vitest";
import { dateToUtcEpoch, epochToYmd, ymd } from "../dateutil";

const DAY = 86_400_000;

describe("dateutil — 타임존 무관 date-only 처리", () => {
  it("2026-02-12 / 2026-05-28 왕복 보존(하루 밀림 없음)", () => {
    for (const d of ["2026-02-12", "2026-05-28"]) {
      const e = dateToUtcEpoch(d)!;
      expect(epochToYmd(e)).toBe(d);   // 어떤 브라우저 타임존이든 동일
    }
  });

  it("항상 UTC 자정으로 고정(로컬 오프셋 누출 없음) → 타임존 독립 보장", () => {
    // epoch 이 UTC 자정(하루의 배수)이면, toISOString(UTC) 결과가 브라우저 TZ와 무관하게 같다.
    for (const d of ["2026-02-12", "2026-05-28", "2024-01-01"]) {
      expect(dateToUtcEpoch(d)! % DAY).toBe(0);
    }
  });

  it("date-only 문자열은 그대로 보존(ymd)", () => {
    expect(ymd("2026-05-28")).toBe("2026-05-28");
    expect(ymd("2026-05-28T09:00:00")).toBe("2026-05-28");
    expect(ymd(null)).toBe("—");
  });

  it("잘못된 값은 null", () => {
    expect(dateToUtcEpoch("")).toBeNull();
    expect(dateToUtcEpoch(null)).toBeNull();
  });
});
