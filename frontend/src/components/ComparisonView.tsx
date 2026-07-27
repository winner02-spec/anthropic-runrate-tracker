import { useState } from "react";
import type { Comparison, Point } from "../types";
import { usdBn, pointValueText } from "../format";
import { dateToUtcEpoch, epochToYmd } from "../dateutil";

const COMPANY_COLORS = ["var(--official)", "#10b981", "#f59e0b", "#ef4444"];

const METRIC_LABEL: Record<string, string> = {
  revenue_run_rate: "Revenue Run-rate", arr: "ARR", monthly_revenue: "월 매출",
  derived_annualized_revenue: "파생 연환산(×12)",
};
const metricLabel = (mt?: string | null): string => METRIC_LABEL[mt || ""] || (mt || "—");
const vsBadge = (s?: string | null): string =>
  ({ verified: "검증완료", corroborated: "간접 확인", provisional: "원문 미확인", needs_review: "검토대기" }[s || ""] || "");

interface Line { label: string; color: string; dashed?: boolean; pts: Array<{ x: number; y: number; raw?: Point }>; }

function MultiLineChart({ lines, yLabel, yFormat }: {
  lines: Line[]; yLabel: string; yFormat: (v: number) => string;
}) {
  const [hover, setHover] = useState<{ x: number; y: number; label: string; text: string } | null>(null);
  const allX: number[] = [], allY: number[] = [];
  lines.forEach((l) => l.pts.forEach((p) => { allX.push(p.x); allY.push(p.y); }));
  if (allX.length === 0) return <div className="empty">비교할 공식 시계열이 없습니다.</div>;

  const W = 940, H = 340, m = { t: 16, r: 18, b: 34, l: 56 };
  const minT = Math.min(...allX), maxT = Math.max(...allX) || minT + 1;
  const spanT = maxT - minT || 1;
  const maxV = Math.max(...allY, 1), minV = 0;
  const X = (t: number) => m.l + ((t - minT) / spanT) * (W - m.l - m.r);
  const Y = (v: number) => m.t + (1 - (v - minV) / (maxV - minV || 1)) * (H - m.t - m.b);
  const grid = Array.from({ length: 5 }, (_, i) => minV + ((maxV - minV) * i) / 4);

  return (
    <div>
      <div className="chartwrap">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img" aria-label={yLabel}>
          {grid.map((v, i) => (
            <g key={i}>
              <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke="var(--line)" />
              <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{yFormat(v)}</text>
            </g>
          ))}
          {lines.map((l, li) => {
            const pp = l.pts.map((p) => ({ x: X(p.x), y: Y(p.y), raw: p.raw })).sort((a, b) => a.x - b.x);
            return (
              <g key={li}>
                {pp.length > 1 && (
                  <path fill="none" stroke={l.color} strokeWidth="2.4"
                        strokeDasharray={l.dashed ? "6 4" : undefined}
                        d={pp.map((q, i) => `${i ? "L" : "M"}${q.x},${q.y}`).join(" ")} />
                )}
                {pp.map((q, i) => (
                  <circle key={i} cx={q.x} cy={q.y} r={4} fill={l.color} stroke="var(--card)" strokeWidth="1.5"
                          onMouseEnter={() => setHover({ x: q.x, y: q.y, label: l.label,
                            text: q.raw ? pointValueText(q.raw) : yFormat(0) })}
                          onMouseLeave={() => setHover(null)} />
                ))}
              </g>
            );
          })}
          <text x={m.l} y={H - 10} fontSize="10" fill="var(--muted)">{epochToYmd(minT)}</text>
          <text x={W - m.r} y={H - 10} textAnchor="end" fontSize="10" fill="var(--muted)">{epochToYmd(maxT)}</text>
        </svg>
      </div>
      {hover && <div className="hint"><b>{hover.label}</b> · {hover.text}</div>}
      <div className="legend">
        {lines.map((l, i) => <span key={i}><i style={{ background: l.color }} />{l.label}</span>)}
      </div>
    </div>
  );
}

function officialLine(label: string, color: string, points: Point[]): Line {
  return {
    label, color,
    pts: points
      .map((p) => { const x = dateToUtcEpoch(p.as_of_end); return x != null && p.value_low_usd_bn != null ? { x, y: p.value_low_usd_bn, raw: p } : null; })
      .filter((v): v is { x: number; y: number; raw: Point } => v !== null),
  };
}

export default function ComparisonView({ cmp }: { cmp: Comparison }) {
  const [showEst, setShowEst] = useState(false);
  const slugs = Object.keys(cmp.companies);

  const absLines: Line[] = [];
  slugs.forEach((slug, i) => {
    const c = cmp.companies[slug];
    absLines.push(officialLine(`${c.display_name} 공식 (${metricLabel(c.official_metric_type)})`, COMPANY_COLORS[i % COMPANY_COLORS.length], c.official_series));
    if (showEst && c.estimated_series.length) {
      absLines.push({ ...officialLine(`${c.display_name} 외부추정`, COMPANY_COLORS[i % COMPANY_COLORS.length], c.estimated_series), dashed: true });
    }
  });

  const normLines: Line[] = slugs.map((slug, i) => {
    const c = cmp.companies[slug];
    return {
      label: `${c.display_name} (100 기준)`, color: COMPANY_COLORS[i % COMPANY_COLORS.length],
      pts: c.normalized.map((n) => { const x = dateToUtcEpoch(n.as_of_end); return x != null ? { x, y: n.index } : null; })
        .filter((v): v is { x: number; y: number } => v !== null),
    };
  });

  return (
    <>
      {cmp.definition_note && (
        <div className="note" style={{ borderLeft: "3px solid var(--target)", paddingLeft: 10 }}>
          ⚠️ {cmp.definition_note}
        </div>
      )}
      <div className="cards">
        {slugs.map((slug) => {
          const c = cmp.companies[slug];
          const monthly = c.monthly_series[c.monthly_series.length - 1];
          const derived = c.derived_series[c.derived_series.length - 1];
          return (
            <div className="card stat" key={slug}>
              <div className="label">{c.display_name} · 최신 공식 ({metricLabel(c.official_metric_type)})</div>
              <div className="value">{c.latest_official ? pointValueText(c.latest_official) : "—"}</div>
              <div className="meta">기준일 {c.latest_official_as_of ?? "—"}
                {c.latest_official ? ` · ${vsBadge(c.latest_official.verification_status)}` : ""}
                {c.valuation_multiple ? ` · 밸류/RR ${c.valuation_multiple.multiple}x` : ""}</div>
              {(monthly || derived) && (
                <div className="meta" style={{ color: "var(--muted)", marginTop: 4 }}>
                  {monthly ? `월매출 ${pointValueText(monthly)}` : ""}
                  {monthly && derived ? " · " : ""}
                  {derived ? `파생연환산 ${pointValueText(derived)}(×12, 공식 ARR 아님)` : ""}
                </div>
              )}
            </div>
          );
        })}
      </div>

      <div className="card section">
        <h2>공식 Revenue Run-rate / ARR 비교</h2>
        <p className="hint">{cmp.note} 각 선의 지표 정의는 회사별로 다릅니다(범례 참고).</p>
        <div className="controls">
          <button className={"seg" + (!showEst ? " on" : "")} onClick={() => setShowEst(false)}>공식만</button>
          <button className={"seg" + (showEst ? " on" : "")} onClick={() => setShowEst(true)}>외부추정 포함</button>
        </div>
        <MultiLineChart lines={absLines} yLabel="공식 Run-rate 비교" yFormat={(v) => usdBn(v, 0)} />
      </div>

      <div className="card section">
        <h2>정규화 성장 (공통 시작점 {cmp.anchor} = 100)</h2>
        <p className="hint">회사별 공식(연환산) 시계열을 각 회사의 시작점 100 기준으로 정규화한 성장 곡선입니다.</p>
        <MultiLineChart lines={normLines} yLabel="정규화 성장" yFormat={(v) => `${v.toFixed(0)}`} />
      </div>

      <div className="card section">
        <h2>회사별 지표 비교</h2>
        <table>
          <thead><tr><th>회사</th><th>지표</th><th>최신 공식</th><th>기준일</th><th>성장속도(30일)</th><th>밸류/Run-rate</th></tr></thead>
          <tbody>
            {slugs.map((slug) => {
              const c = cmp.companies[slug];
              const v = c.growth_velocity;
              return (
                <tr key={slug}>
                  <td>{c.display_name}</td>
                  <td>{metricLabel(c.official_metric_type)}</td>
                  <td>{c.latest_official ? pointValueText(c.latest_official) : "—"}{c.latest_official ? ` (${vsBadge(c.latest_official.verification_status)})` : ""}</td>
                  <td>{c.latest_official_as_of ?? "—"}</td>
                  <td className={v && v.delta_per_30d_usd_bn >= 0 ? "up" : ""}>
                    {v ? usdBn(v.delta_per_30d_usd_bn) : "—"}{v?.is_approximate ? " ~" : ""}</td>
                  <td>{c.valuation_multiple
                    ? `${c.valuation_multiple.multiple}x (${usdBn(c.valuation_multiple.valuation_usd_bn, 0)} / ${usdBn(c.valuation_multiple.runrate_usd_bn, 0)})`
                    : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
        <p className="hint">성장속도는 회사별 공식 포인트끼리만 계산합니다. 파생값(월매출×12)·외부추정은 공식선에서 제외됩니다.</p>
      </div>
    </>
  );
}
