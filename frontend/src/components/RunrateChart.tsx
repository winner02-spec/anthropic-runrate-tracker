import { useState } from "react";
import type { CompanyPayload, Point } from "../types";
import { usdBn, pointValueText, pointDate, qualifierLabel } from "../format";
import { dateToUtcEpoch, epochToYmd } from "../dateutil";

// 시계열 종류별 색/스타일 — 공식·보도·추정·파생을 하나의 선으로 연결하지 않는다.
const SERIES = {
  official_current: { color: "var(--official)", label: "공식(현재)", dashed: false, line: true },
  official_retro: { color: "var(--official)", label: "공식(회고)", dashed: false, line: false },
  reported: { color: "var(--reported)", label: "주요 매체 보도", dashed: true, line: true },
  tickertrends: { color: "var(--estimate)", label: "TickerTrends 추정", dashed: true, line: true },
  yipit: { color: "#d98a00", label: "Yipit 추정", dashed: true, line: false },
  sacra: { color: "#0ea5e9", label: "Sacra 추정", dashed: true, line: true },
  // Funda: 기준일·산정방법 미공개(원자료 미확인) → 선으로 연결하지 않고 마커만
  funda: { color: "#ec4899", label: "Funda 추정 후보(원자료 미확인)", dashed: true, line: false },
  estimate: { color: "var(--estimate)", label: "외부 추정", dashed: true, line: false },
  derived: { color: "#8b5cf6", label: "파생(월매출×12)", dashed: true, line: false },
} as const;
type SKind = keyof typeof SERIES;

const VS_BADGE: Record<string, string> = {
  verified: "검증완료", corroborated: "간접 확인", provisional: "원문 미확인", needs_review: "검토대기",
};

type Filter = "all" | "official" | "official_reported" | "estimates" | "derived" | "target";
const FILTERS: Array<[Filter, string]> = [
  ["all", "전체"], ["official", "공식만"], ["official_reported", "공식+매체"],
  ["estimates", "외부추정 포함"], ["derived", "파생값 포함"], ["target", "목표 포함"],
];

const ESTIMATE_KINDS: SKind[] = ["tickertrends", "yipit", "sacra", "funda", "estimate"];

function visibleKinds(f: Filter): Set<SKind> {
  if (f === "official") return new Set<SKind>(["official_current", "official_retro"]);
  if (f === "official_reported") return new Set<SKind>(["official_current", "official_retro", "reported"]);
  if (f === "derived") return new Set<SKind>(["official_current", "official_retro", "reported", "derived"]);
  return new Set<SKind>(["official_current", "official_retro", "reported", ...ESTIMATE_KINDS, "derived"]);
}

function classify(p: Point): SKind | null {
  if (p.is_derived) return "derived";
  const src = (p.source_name || "").toLowerCase();
  if (p.is_official) return p.source_type === "official_retrospective" ? "official_retro" : "official_current";
  if (p.is_estimate) {
    if (src.includes("tickertrends")) return "tickertrends";
    if (src.includes("yipit")) return "yipit";
    if (src.includes("sacra")) return "sacra";
    if (src.includes("funda")) return "funda";
    return "estimate";
  }
  if (p.is_target) return null; // 목표는 밴드로 별도
  return "reported";
}

interface PP { x: number; y: number; p: Point; kind: SKind; }

export default function RunrateChart({ cp }: { cp: CompanyPayload }) {
  const [logScale, setLog] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [hover, setHover] = useState<PP | null>(null);

  const showTarget = filter === "all" || filter === "target";
  const vis = visibleKinds(filter);

  // 공식·보도·추정·파생 포인트 → 종류별 분류(월매출은 연환산 축과 스케일 달라 차트에서 제외)
  const allPts: Point[] = [
    ...cp.series.official, ...cp.series.reported, ...cp.series.estimated, ...cp.series.derived,
  ];
  const grouped: Record<SKind, Point[]> = {
    official_current: [], official_retro: [], reported: [], tickertrends: [], yipit: [],
    sacra: [], funda: [], estimate: [], derived: [],
  };
  for (const p of allPts) {
    const k = classify(p);
    if (k) grouped[k].push(p);
  }
  const targets = cp.series.target;

  const vals: number[] = [];
  (Object.keys(grouped) as SKind[]).forEach((k) => {
    if (vis.has(k)) grouped[k].forEach((p) => p.value_low_usd_bn != null && vals.push(p.value_low_usd_bn));
  });
  if (showTarget) targets.forEach((p) => p.value_low_usd_bn != null && vals.push(p.value_low_usd_bn));

  if (vals.length === 0) {
    return (
      <div>
        <Filters filter={filter} setFilter={setFilter} />
        <div className="empty">이 필터에 표시할 데이터가 없습니다.</div>
      </div>
    );
  }

  const dates: number[] = [];
  allPts.forEach((p) => { const t = dateToUtcEpoch(p.as_of_end); if (t) dates.push(t); });
  cp.events.forEach((e) => { const t = dateToUtcEpoch(e.event_date); if (t) dates.push(t); });

  const W = 940, H = 380, m = { t: 16, r: 18, b: 34, l: 54 };
  const minT = Math.min(...dates), maxT = Math.max(...dates) || minT + 1;
  const spanT = maxT - minT || 1;
  const maxV = Math.max(...vals, 1);
  const minV = logScale ? Math.max(0.05, Math.min(...vals)) : 0;
  const X = (t: number) => m.l + ((t - minT) / spanT) * (W - m.l - m.r);
  const Y = (v: number) => {
    if (logScale) {
      const lv = Math.log10(Math.max(v, 0.05)), a = Math.log10(Math.max(minV, 0.05)), b = Math.log10(maxV);
      return m.t + (1 - (lv - a) / (b - a || 1)) * (H - m.t - m.b);
    }
    return m.t + (1 - (v - minV) / (maxV - minV || 1)) * (H - m.t - m.b);
  };

  const plotted = (Object.keys(grouped) as SKind[])
    .filter((k) => vis.has(k))
    .map((k) => ({
      kind: k,
      pp: grouped[k]
        .map((p) => { const t = dateToUtcEpoch(p.as_of_end); return t && p.value_low_usd_bn != null ? { x: X(t), y: Y(p.value_low_usd_bn), p, kind: k } : null; })
        .filter((v): v is PP => v !== null)
        .sort((a, b) => a.x - b.x),
    }));

  const grid = Array.from({ length: 5 }, (_, i) => minV + ((maxV - minV) * i) / 4);

  return (
    <div>
      <div className="controls">
        <button className={"seg" + (!logScale ? " on" : "")} onClick={() => setLog(false)}>Linear</button>
        <button className={"seg" + (logScale ? " on" : "")} onClick={() => setLog(true)}>Log</button>
      </div>
      <Filters filter={filter} setFilter={setFilter} />
      <div className="chartwrap">
        <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="xMidYMid meet" role="img"
             aria-label={`${cp.display_name} Revenue Run-rate 시계열`}>
          {grid.map((v, i) => (
            <g key={i}>
              <line x1={m.l} x2={W - m.r} y1={Y(v)} y2={Y(v)} stroke="var(--line)" />
              <text x={m.l - 6} y={Y(v) + 4} textAnchor="end" fontSize="11" fill="var(--muted)">{usdBn(v, 0)}</text>
            </g>
          ))}
          {showTarget && targets.map((tg, i) => tg.value_low_usd_bn != null && (
            <g key={"t" + i}>
              <line x1={m.l} x2={W - m.r} y1={Y(tg.value_low_usd_bn)} y2={Y(tg.value_low_usd_bn)}
                    stroke="var(--target)" strokeDasharray="7 4" opacity="0.8" />
              <text x={W - m.r} y={Y(tg.value_low_usd_bn) - 4} textAnchor="end" fontSize="10" fill="var(--target)">
                목표 {usdBn(tg.value_low_usd_bn, 0)}
              </text>
            </g>
          ))}
          {cp.events.map((e, i) => { const t = dateToUtcEpoch(e.event_date); return t ? (
            <line key={"e" + i} x1={X(t)} x2={X(t)} y1={m.t} y2={H - m.b} stroke="var(--muted)" strokeDasharray="2 3" opacity="0.4" />
          ) : null; })}
          {plotted.map(({ kind, pp }) => pp.length > 0 && (
            <g key={kind}>
              {SERIES[kind].line && pp.length > 1 && (
                <path fill="none" stroke={SERIES[kind].color} strokeWidth={SERIES[kind].dashed ? 1.7 : 2.6}
                      strokeDasharray={SERIES[kind].dashed ? "6 4" : undefined}
                      d={pp.map((q, i) => `${i ? "L" : "M"}${q.x},${q.y}`).join(" ")} />
              )}
              {pp.map((q, i) => kind === "derived" ? (
                // 파생값 = 회전 사각형(다이아몬드) 마커로 공식과 구분
                <rect key={i} x={q.x - 4} y={q.y - 4} width={8} height={8}
                      transform={`rotate(45 ${q.x} ${q.y})`} fill="var(--card)"
                      stroke={SERIES[kind].color} strokeWidth="2"
                      onMouseEnter={() => setHover(q)} onMouseLeave={() => setHover(null)} />
              ) : kind === "funda" ? (
                // Funda = 원자료·기준일 미확인 추정 후보 → 정사각 마커(선 연결 없음)
                <rect key={i} x={q.x - 4} y={q.y - 4} width={8} height={8} fill="var(--card)"
                      stroke={SERIES[kind].color} strokeWidth="2"
                      onMouseEnter={() => setHover(q)} onMouseLeave={() => setHover(null)} />
              ) : (
                <circle key={i} cx={q.x} cy={q.y} r={kind === "official_current" ? 5 : 4}
                        fill={kind === "official_current" ? SERIES[kind].color : "var(--card)"}
                        stroke={SERIES[kind].color} strokeWidth="2"
                        onMouseEnter={() => setHover(q)} onMouseLeave={() => setHover(null)} />
              ))}
            </g>
          ))}
          <text x={m.l} y={H - 10} fontSize="10" fill="var(--muted)">{epochToYmd(minT)}</text>
          <text x={W - m.r} y={H - 10} textAnchor="end" fontSize="10" fill="var(--muted)">{epochToYmd(maxT)}</text>
        </svg>
      </div>
      {hover && (
        <div className="hint">
          <b>{pointValueText(hover.p)}</b> · {qualifierLabel(hover.p.qualifier)} · 기준일 {pointDate(hover.p)} ·
          {" "}발표일 {hover.p.published_at ?? "—"} · {SERIES[hover.kind].label} ({hover.p.source_type}) ·
          {" "}{hover.p.source_url
            ? <a href={hover.p.source_url} target="_blank" rel="noreferrer">{hover.p.source_name}</a>
            : (hover.p.source_name ?? "—")}
          {" "}· 신뢰도 {hover.p.confidence_score ?? "—"}
          {hover.kind === "official_retro" ? " · 회고값" : ""}
          {hover.kind === "derived" ? " · 월 매출을 12배 한 계산값(공식 ARR 아님)" : ""}
          {hover.kind === "funda" ? " · 기준일·산정방법 미공개 추정 후보(시계열로 연결하지 않음)" : ""}
          {hover.p.date_precision === "unknown" ? " · 기준일 미상" : ""}
          {" "}· <b>{VS_BADGE[hover.p.verification_status || "needs_review"]}</b>
          {hover.p.verification_status === "provisional" && hover.p.source_note ? ` · ${hover.p.source_note}` : ""}
        </div>
      )}
      <div className="legend">
        {(Object.keys(SERIES) as SKind[]).filter((k) => vis.has(k)).map((k) => (
          <span key={k}><i style={{ background: SERIES[k].color }} />{SERIES[k].label}</span>
        ))}
        {showTarget && <span><i style={{ background: "var(--target)" }} />목표</span>}
        <span style={{ color: "var(--muted)" }}>
          · 공식·보도·추정·파생은 선을 연결하지 않음 · 외부추정은 기관별(TickerTrends/Sacra/Yipit/Funda)로 분리
        </span>
      </div>
    </div>
  );
}

function Filters({ filter, setFilter }: { filter: Filter; setFilter: (f: Filter) => void }) {
  return (
    <div className="controls">
      {FILTERS.map(([v, l]) => (
        <button key={v} className={"seg" + (filter === v ? " on" : "")} onClick={() => setFilter(v)}>{l}</button>
      ))}
    </div>
  );
}
