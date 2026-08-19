import { useState } from "react";
import type { CompanyPayload, Point } from "../types";
import { usdBn, pointValueText, pointDate, qualifierLabel } from "../format";
import { dateToUtcEpoch, epochToYmd } from "../dateutil";
import { canonicalEpoch } from "../pointsort";
import {
  FILTERS, classify, showsTarget, visibleKinds,
  type Filter, type SKind,
} from "../filters";

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
  target: { color: "var(--target)", label: "목표", dashed: true, line: false },
} as const;
type TipKind = keyof typeof SERIES;

const VS_BADGE: Record<string, string> = {
  verified: "검증완료", corroborated: "간접 확인", provisional: "원문 미확인", needs_review: "검토대기",
};

interface PP { x: number; y: number; p: Point; kind: TipKind; }

const W = 940, H = 380, m = { t: 16, r: 18, b: 34, l: 54 };

export default function RunrateChart(
  { cp, filter: outerFilter, setFilter: outerSetFilter }:
  { cp: CompanyPayload; filter?: Filter; setFilter?: (f: Filter) => void },
) {
  const [logScale, setLog] = useState(false);
  const [innerFilter, setInnerFilter] = useState<Filter>("all");
  // 필터를 밖에서 쥐고 있으면(타임라인과 공유) 그걸 쓰고, 아니면 스스로 쥔다.
  const filter = outerFilter ?? innerFilter;
  const setFilter = outerSetFilter ?? setInnerFilter;

  const [hover, setHover] = useState<PP | null>(null);
  // 모바일에는 hover 가 없다. 점을 탭하면 고정해 두고, 다시 탭하거나 닫으면 사라진다.
  const [pinned, setPinned] = useState<PP | null>(null);
  const shown = pinned ?? hover;

  const showTarget = showsTarget(filter);
  const vis = visibleKinds(filter);

  const allPts: Point[] = [
    ...cp.series.official, ...cp.series.reported, ...cp.series.estimated, ...cp.series.derived,
  ];
  const grouped = {
    official_current: [], official_retro: [], reported: [], tickertrends: [], yipit: [],
    sacra: [], funda: [], estimate: [], derived: [],
  } as Record<SKind, Point[]>;
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

  // 가로축은 canonical 날짜(기간의 끝)로 놓는다. 화면에 적는 기준일은 범위 그대로 보여준다.
  const dates: number[] = [];
  allPts.forEach((p) => { const t = canonicalEpoch(p); if (t) dates.push(t); });
  cp.events.forEach((e) => { const t = dateToUtcEpoch(e.event_date); if (t) dates.push(t); });

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
        .map((p) => { const t = canonicalEpoch(p); return t && p.value_low_usd_bn != null ? { x: X(t), y: Y(p.value_low_usd_bn), p, kind: k as TipKind } : null; })
        .filter((v): v is PP => v !== null)
        .sort((a, b) => a.x - b.x),
    }));

  const grid = Array.from({ length: 5 }, (_, i) => minV + ((maxV - minV) * i) / 4);

  // 점마다 자기 정보를 들고 있다. 서로 겹쳐도 잡히는 점의 tooltip 이 뜬다.
  const handlers = (q: PP) => ({
    onMouseEnter: () => setHover(q),
    onMouseLeave: () => setHover(null),
    onClick: () => setPinned((cur) => (cur && cur.p === q.p ? null : q)),
    style: { cursor: "pointer" as const },
  });

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
            <g key={"t" + i} className="targetband"
               {...handlers({ x: (m.l + W - m.r) / 2, y: Y(tg.value_low_usd_bn), p: tg, kind: "target" })}>
              {/* 실선 위에 보이지 않는 굵은 선을 겹쳐 둔다 — 얇은 선은 마우스로 잡기 어렵다 */}
              <line x1={m.l} x2={W - m.r} y1={Y(tg.value_low_usd_bn)} y2={Y(tg.value_low_usd_bn)}
                    stroke="transparent" strokeWidth="12" />
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
              {pp.map((q, i) => (
                <g key={i} className="marker" {...handlers(q)}>
                  {/* 잡기 쉬우라고 투명한 원을 덧댄다. 겹친 점들도 각자 이 원을 갖는다 */}
                  <circle cx={q.x} cy={q.y} r={10} fill="transparent" />
                  {kind === "derived" ? (
                    // 파생값 = 회전 사각형(다이아몬드) 마커로 공식과 구분
                    <rect x={q.x - 4} y={q.y - 4} width={8} height={8}
                          transform={`rotate(45 ${q.x} ${q.y})`} fill="var(--card)"
                          stroke={SERIES[kind].color} strokeWidth="2" />
                  ) : kind === "funda" ? (
                    // Funda = 원자료·기준일 미확인 추정 후보 → 정사각 마커(선 연결 없음)
                    <rect x={q.x - 4} y={q.y - 4} width={8} height={8} fill="var(--card)"
                          stroke={SERIES[kind].color} strokeWidth="2" />
                  ) : (
                    <circle cx={q.x} cy={q.y} r={kind === "official_current" ? 5 : 4}
                            fill={kind === "official_current" ? SERIES[kind].color : "var(--card)"}
                            stroke={SERIES[kind].color} strokeWidth="2" />
                  )}
                </g>
              ))}
            </g>
          ))}
          <text x={m.l} y={H - 10} fontSize="10" fill="var(--muted)">{epochToYmd(minT)}</text>
          <text x={W - m.r} y={H - 10} textAnchor="end" fontSize="10" fill="var(--muted)">{epochToYmd(maxT)}</text>
        </svg>
        {shown && <Tooltip pp={shown} pinned={pinned !== null} onClose={() => { setPinned(null); setHover(null); }} />}
      </div>
      <div className="legend">
        {(Object.keys(SERIES) as TipKind[])
          .filter((k) => (k === "target" ? showTarget : vis.has(k as SKind)))
          .map((k) => (
            <span key={k}><i style={{ background: SERIES[k].color }} />{SERIES[k].label}</span>
          ))}
        <span style={{ color: "var(--muted)" }}>
          · 공식·보도·추정·파생은 선을 연결하지 않음 · 외부추정은 기관별(TickerTrends/Sacra/Yipit/Funda)로 분리
        </span>
      </div>
    </div>
  );
}

/** 점 하나가 무엇인지 그 자리에서 말한다. 값만 보고 기준을 오해하지 않게 한다. */
function Tooltip({ pp, pinned, onClose }: { pp: PP; pinned: boolean; onClose: () => void }) {
  const p = pp.p;
  const vs = p.verification_status || "needs_review";
  return (
    <div className="tip" role="tooltip"
         style={{ left: `${(pp.x / W) * 100}%`, top: `${(pp.y / H) * 100}%` }}>
      {pinned && (
        <button type="button" className="tipclose" onClick={onClose} aria-label="툴팁 닫기">×</button>
      )}
      <div className="tipval">{pointValueText(p)} <span className="tipq">{qualifierLabel(p.qualifier)}</span></div>
      <dl>
        <dt>기준일</dt><dd>{pointDate(p)}</dd>
        <dt>발표일</dt><dd>{p.published_at ?? "—"}</dd>
        <dt>구분</dt><dd>{SERIES[pp.kind].label}{p.source_type ? ` (${p.source_type})` : ""}</dd>
        <dt>출처</dt><dd>{p.source_url
          ? <a href={p.source_url} target="_blank" rel="noreferrer">{p.source_name ?? "원문 보기"}</a>
          : (p.source_name ?? "—")}</dd>
        <dt>검증</dt><dd><b>{VS_BADGE[vs]}</b></dd>
      </dl>
      {pp.kind === "derived" && (
        <p className="tipnote">월 매출을 12배 한 계산값입니다. 회사가 발표한 ARR 이 아닙니다.</p>
      )}
      {pp.kind === "official_retro" && <p className="tipnote">지난 시점을 나중에 회고한 값입니다.</p>}
      {pp.kind === "funda" && <p className="tipnote">기준일·산정방법이 공개되지 않아 시계열로 잇지 않습니다.</p>}
      {p.date_precision === "unknown" && <p className="tipnote">기준일이 공개되지 않았습니다.</p>}
      {vs === "provisional" && p.source_note && <p className="tipnote">{p.source_note}</p>}
      {p.source_url && <p className="tipnote"><a href={p.source_url} target="_blank" rel="noreferrer">원문 보기</a></p>}
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
