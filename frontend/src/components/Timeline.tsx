import { useEffect, useState } from "react";
import type { Point } from "../types";
import { pointDate, pointValueText, qualifierLabel } from "../format";
import { sortPoints, type SortDir, type SortKey } from "../pointsort";

const STORE_KEY = "runrate.timelineSort";

const KEY_LABEL: Record<SortKey, string> = { as_of: "기준일", published: "발표일" };
const DIR_LABEL: Record<SortDir, string> = { desc: "최신순", asc: "오래된순" };

function load(): { key: SortKey; dir: SortDir } {
  // 기본은 기준일·최신순. 저장된 값이 깨져 있으면 조용히 기본으로 돌아간다 —
  // 정렬 하나 때문에 화면 전체가 죽으면 안 된다.
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) {
      const v = JSON.parse(raw);
      if ((v.key === "as_of" || v.key === "published") && (v.dir === "desc" || v.dir === "asc")) {
        return { key: v.key, dir: v.dir };
      }
    }
  } catch {
    /* 저장소를 못 읽는 환경(사파리 프라이빗 등)에서도 화면은 떠야 한다 */
  }
  return { key: "as_of", dir: "desc" };
}

function save(key: SortKey, dir: SortDir): void {
  try {
    localStorage.setItem(STORE_KEY, JSON.stringify({ key, dir }));
  } catch {
    /* 저장 못 해도 이번 세션 동안은 정상 동작한다 */
  }
}

/** 업데이트 타임라인. 필터로 걸러 낸 뒤 남은 것에만 순서를 매긴다. */
export default function Timeline({ points }: { points: Point[] }) {
  const [{ key, dir }, setSort] = useState(load);

  useEffect(() => { save(key, dir); }, [key, dir]);

  // 헤더를 누르면: 같은 기준이면 방향만 뒤집고, 다른 기준이면 그 기준으로 옮긴다.
  const onHeader = (next: SortKey) =>
    setSort((s) => (s.key === next ? { key: s.key, dir: s.dir === "desc" ? "asc" : "desc" } : { ...s, key: next }));

  const arrow = (col: SortKey) => (key === col ? (dir === "desc" ? " ↓" : " ↑") : "");
  const rows = sortPoints(points, key, dir);

  return (
    <div className="card section">
      <h2>업데이트 타임라인</h2>
      <div className="controls">
        <label>
          <span className="sronly">정렬 기준</span>
          <select aria-label="정렬 기준" value={key}
                  onChange={(e) => setSort((s) => ({ ...s, key: e.target.value as SortKey }))}>
            {(Object.keys(KEY_LABEL) as SortKey[]).map((k) => (
              <option key={k} value={k}>{KEY_LABEL[k]}</option>
            ))}
          </select>
        </label>
        <label>
          <span className="sronly">정렬 방향</span>
          <select aria-label="정렬 방향" value={dir}
                  onChange={(e) => setSort((s) => ({ ...s, dir: e.target.value as SortDir }))}>
            {(Object.keys(DIR_LABEL) as SortDir[]).map((d) => (
              <option key={d} value={d}>{DIR_LABEL[d]}</option>
            ))}
          </select>
        </label>
      </div>
      {rows.length === 0 ? (
        <div className="empty">이 필터에 표시할 데이터가 없습니다.</div>
      ) : (
        <table>
          <thead>
            <tr>
              <th><button type="button" className="thsort" onClick={() => onHeader("published")}
                          aria-sort={key === "published" ? (dir === "desc" ? "descending" : "ascending") : "none"}>
                발표일{arrow("published")}
              </button></th>
              <th><button type="button" className="thsort" onClick={() => onHeader("as_of")}
                          aria-sort={key === "as_of" ? (dir === "desc" ? "descending" : "ascending") : "none"}>
                기준일{arrow("as_of")}
              </button></th>
              <th>값</th><th>구분</th><th>출처</th><th>근거</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={i}>
                <td>{p.published_at ?? "—"}</td>
                <td>{pointDate(p)}</td>
                <td>{pointValueText(p)}</td>
                <td>
                  <span className={"badge " + (p.source_tier || "D")}>{p.metric_type || p.source_type}</span>{" "}
                  {qualifierLabel(p.qualifier)}
                </td>
                <td>{p.source_url
                  ? <a href={p.source_url} target="_blank" rel="noreferrer">{p.source_name}</a>
                  : (p.source_name ?? "—")}</td>
                <td style={{ maxWidth: 320, color: "var(--muted)" }}>{p.evidence_text}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
