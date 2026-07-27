import { useState } from "react";
import type { Dashboard, Point } from "../types";
import { usdBn, pointValueText, qualifierLabel } from "../format";

const COL = {
  official: "var(--official)",
  estimated: "var(--estimate)",
  reported: "var(--reported)",
  target: "var(--target)",
};
type Kind = keyof typeof COL;

function ts(d?: string | null): number | null {
  if (!d) return null;
  const t = new Date(d + "T00:00:00").getTime();
  return Number.isNaN(t) ? null : t;
}

interface PlotPoint { x: number; y: number; p: Point; kind: Kind; }

export default function RunrateChart({ data }: { data: Dashboard }) {
  const [logScale, setLog] = useState(false);
  const [hover, setHover] = useState<PlotPoint | null>(null);

  const series: Array<{ kind: keyof typeof COL; dashed: boolean; points: Point[] }> = [
    { kind: "official", dashed: false, points: data.series.official },
    { kind: "reported", dashed: true, points: data.series.reported },
    { kind: "estimated", dashed: true, points: data.series.estimated },
  ];
  const targets = data.series.target;
  const events = data.events || [];

  const allVals: number[] = [];
  series.forEach((s) => s.points.forEach((p) => p.value_low_usd_bn != null && allVals.push(p.value_low_usd_bn)));
  targets.forEach((p) => p.value_low_usd_bn != null && allVals.push(p.value_low_usd_bn));

  const dates: number[] = [];
  series.forEach((s) => s.points.forEach((p) => { const t = ts(p.as_of_end); if (t) dates.push(t); }));
  events.forEach((e) => { const t = ts(e.event_date); if (t) dates.push(t); });

  if (allVals.length === 0) {
    return <div className="empty">표시할 공식/추정 데이터가 아직 없습니다.</div>;
  }

  const W = 920, H = 360, m = { t: 16, r: 18, b: 34, l: 52 };
  const minT = Math.min(...dates), maxT = Math.max(...dates) || minT + 1;
  const spanT = maxT - minT || 1;
  const maxV = Math.max(...allVals, 1);
  const minV = logScale ? Math.max(0.1, Math.min(...allVals)) : 0;

  const X = (t: number) => m.l + ((t - minT) / spanT) * (W - m.l - m.r);
  const Y = (v: number) => {
    if (logScale) {
      const lv = Math.log10(Math.max(v, 0.1)), lmin = Math.log10(Math.max(minV, 0.1)), lmax = Math.log10(maxV);
      return m.t + (1 - (lv - lmin) / (lmax - lmin || 1)) * (H - m.t - m.b);
    }
    return m.t + (1 - (v - minV) / (maxV - minV || 1)) * (H - m.t - m.b);
  };

  const plotted: Array<{ kind: keyof typeof COL; dashed: boolean; pp: PlotPoint[] }> = series.map((s) => ({
    kind: s.kind,
    dashed: s.dashed,
    pp: s.points
      .map((p) => { const t = ts(p.as_of_end); return t && p.value_low_usd_bn != null ? { x: X(t), y: Y(p.value_low_usd_bn), p, kind: s.kind } : null; })
      .filter((v): v is PlotPoint => v !== null),
  }));

  const gridVals = Array.from({ length: 5 }, (_, i) => minV + ((maxV - minV) * i) / 4);

  return (
    <div>
      <div className="controls">
        <button className={"seg" + (!logScale ? " on" : "")} onClick={() => setLog(false)}>Linear</button>
        <button className={"seg" + (logScale ? " on" : "")} onClick={() => setLog(true)}>Log</button>
      </div>
      <div className="chartwrap">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img"
             aria-label="Anthropic Revenue Run-rate 추이">
          {gridVals.map((v, i) => (
            <g key={i}>
              <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke="var(--line)" />
              <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{usdBn(v, 0)}</text>
            </g>
          ))}
          {/* 목표 밴드/선 */}
          {targets.map((tg, i) => tg.value_low_usd_bn != null && (
            <g key={"t" + i}>
              <line x1={m.l} x2={W - m.r} y1={Y(tg.value_low_usd_bn)} y2={Y(tg.value_low_usd_bn)}
                    stroke={COL.target} strokeDasharray="6 4" />
              <text x={W - m.r} y={Y(tg.value_low_usd_bn) - 4} textAnchor="end" fontSize="10" fill={COL.target}>
                목표 {usdBn(tg.value_low_usd_bn, 0)}
              </text>
            </g>
          ))}
          {/* 이벤트 주석 */}
          {events.map((e, i) => { const t = ts(e.event_date); return t ? (
            <g key={"e" + i}>
              <line x1={X(t)} x2={X(t)} y1={m.t} y2={H - m.b} stroke="var(--muted)" strokeDasharray="2 3" opacity="0.5" />
            </g>
          ) : null; })}
          {/* 시리즈: 공식은 실선, 추정/보도는 점선. 서로 연결하지 않음 */}
          {plotted.map((s) => s.pp.length > 0 && (
            <g key={s.kind}>
              {s.pp.length > 1 && (
                <path fill="none" stroke={COL[s.kind]} strokeWidth={s.dashed ? 1.6 : 2.4}
                      strokeDasharray={s.dashed ? "6 4" : undefined}
                      d={s.pp.map((q, i) => `${i ? "L" : "M"}${q.x},${q.y}`).join(" ")} />
              )}
              {s.pp.map((q, i) => (
                <circle key={i} cx={q.x} cy={q.y} r={s.kind === "official" ? 5 : 4}
                        fill={s.kind === "official" ? COL.official : "var(--card)"}
                        stroke={COL[s.kind]} strokeWidth="2"
                        onMouseEnter={() => setHover(q)} onMouseLeave={() => setHover(null)} />
              ))}
            </g>
          ))}
          {/* x축 라벨(최소/최대일) */}
          <text x={m.l} y={H - 10} fontSize="10" fill="var(--muted)">{new Date(minT).toISOString().slice(0, 10)}</text>
          <text x={W - m.r} y={H - 10} textAnchor="end" fontSize="10" fill="var(--muted)">{new Date(maxT).toISOString().slice(0, 10)}</text>
        </svg>
      </div>
      {hover && (
        <div className="hint">
          <b>{pointValueText(hover.p)}</b> · 기준일 {hover.p.as_of_end} · 발표일 {hover.p.published_at} ·
          {" "}{qualifierLabel(hover.p.qualifier)} · {hover.p.source_name} ({hover.p.source_tier}) ·
          {" "}신뢰도 {hover.p.confidence_score ?? "—"}
        </div>
      )}
      <div className="legend">
        <span><i style={{ background: COL.official }} />공식(실선·원점)</span>
        <span><i style={{ background: COL.reported }} />보도(점선)</span>
        <span><i style={{ background: COL.estimated }} />추정(점선)</span>
        <span><i style={{ background: COL.target }} />목표</span>
        <span style={{ color: "var(--muted)" }}>· 세로선 = 이벤트</span>
      </div>
    </div>
  );
}
