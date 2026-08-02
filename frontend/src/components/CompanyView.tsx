import type { CompanyPayload, Point } from "../types";
import { usdBn, pct, pointValueText, pointDate, qualifierLabel } from "../format";
import { dateToUtcEpoch } from "../dateutil";
import RunrateChart from "./RunrateChart";

function Stat({ label, value, meta, cls, title }: { label: string; value: string; meta?: string; cls?: string; title?: string }) {
  return (
    <div className="card stat" title={title}>
      <div className="label">{label}</div>
      <div className={"value " + (cls || "")}>{value}</div>
      {meta && <div className="meta">{meta}</div>}
    </div>
  );
}

const ACCEL_LABEL: Record<string, string> = {
  accelerating: "가속", decelerating: "감속", stable: "안정", insufficient_data: "데이터 부족",
};

const vsBadge = (s?: string | null): string =>
  ({ verified: "검증완료", corroborated: "간접 확인", provisional: "원문 미확인", needs_review: "검토대기" }[s || ""] || "—");

const COUNT_METRICS = new Set(["active_users", "paid_subscribers", "business_customers"]);

// 제품지표 값 표기: 사용자/구독자 수는 백만 단위, 매출성은 $B
function productValue(pm: { value_usd_bn?: number | null; qualifier?: string | null; metric_name?: string | null }): string {
  const v = pm.value_usd_bn;
  if (v == null) return "—";
  const over = pm.qualifier === "over" ? "+" : "";
  if (COUNT_METRICS.has(pm.metric_name || "")) return `${Math.round(v * 1000)}M${over}`;
  return `${usdBn(v)}${over ? " 이상" : ""}`;
}

const METRIC_LABEL: Record<string, string> = {
  revenue_run_rate: "Run-rate 매출", product_arr: "제품 ARR", arr: "ARR",
  active_users: "주간 활성 사용자", paid_subscribers: "유료 구독자", business_customers: "비즈니스 고객",
};

export default function CompanyView({ cp }: { cp: CompanyPayload }) {
  const m = cp.metrics;
  const off = m.latest_official;
  const gap = m.official_estimate_gap;
  const vel = m.growth_velocity;

  const lc = (s?: string) => (p: { source_name?: string | null }) => (p.source_name || "").toLowerCase().includes(s || "");
  const last = <T,>(a: T[]): T | null => (a.length ? a[a.length - 1] : null);
  const latestReported = last(cp.series.reported);
  const tickers = cp.series.estimated.filter(lc("tickertrends"));
  const latestMonthly = last(cp.series.monthly);
  const latestDerived = last(cp.series.derived);
  // 기관별 최신 외부추정(TickerTrends/Sacra/Funda …) — 하나로 합치지 않고 카드도 기관별로 분리
  const estBySource = m.latest_estimates_by_source ?? [];
  const divergence = m.estimate_divergence;
  // 기준일 미공개(date_precision=unknown) = 시계열 포인트가 아닌 '추정 후보'
  const isCandidate = (p: Point) => p.date_precision === "unknown";

  function estVelocity(): number | null {
    if (tickers.length < 2) return null;
    const a = tickers[tickers.length - 2], b = tickers[tickers.length - 1];
    const ea = dateToUtcEpoch(a.as_of_end), eb = dateToUtcEpoch(b.as_of_end);
    if (!ea || !eb || a.value_low_usd_bn == null || b.value_low_usd_bn == null) return null;
    const days = Math.max(1, (eb - ea) / 86400000);
    return Math.round((b.value_low_usd_bn - a.value_low_usd_bn) / days * 30 * 100) / 100;
  }
  const estVel = estVelocity();
  const s = cp.series;
  const hasAny = s.official.length + s.estimated.length + s.reported.length +
                 s.target.length + s.derived.length + s.monthly.length > 0;

  if (!hasAny) {
    return <div className="card empty">이 회사의 공개 데이터가 아직 없습니다.</div>;
  }

  return (
    <>
      <div className="cards">
        <Stat label="최신 공식 Run-rate / ARR" value={off ? pointValueText(off) : "—"}
              meta={off ? `기준일 ${off.as_of_end} · ${off.source_name ?? ""}` : "공식 데이터 없음"} />
        {latestMonthly && (
          <Stat label="최신 월 매출(공식)" value={pointValueText(latestMonthly)}
                meta={`기준일 ${pointDate(latestMonthly)} · 월 매출(연환산 아님)`} />
        )}
        {latestDerived && (
          <Stat label="파생 연환산(월매출×12)" value={pointValueText(latestDerived)}
                meta={`${pointDate(latestDerived)} · 계산값 · 공식 ARR 아님`} cls="warn" />
        )}
        <Stat label="최신 주요 매체 보도값" value={latestReported ? pointValueText(latestReported) : "—"}
              meta={latestReported ? `기준일 ${pointDate(latestReported)} · ${latestReported.source_name ?? ""}` : "보도값 없음"} />
        {estBySource.map(({ source, point }) => (
          <Stat key={source}
                label={`${source} ${isCandidate(point) ? "추정 후보" : "최신 추정"}`}
                value={pointValueText(point)}
                meta={`${pointDate(point)} · ${point.source_name ?? source} · ${vsBadge(point.verification_status)}`}
                title={[point.source_note, point.evidence_note].filter(Boolean).join(" / ")}
                cls={point.verification_status === "provisional" ? "warn" : ""} />
        ))}
        {estVel != null && (
          <Stat label="외부추정 성장속도(30일 환산)" value={usdBn(estVel)}
                meta="TickerTrends 최근 구간" cls={estVel >= 0 ? "up" : ""} />
        )}
        {gap && (
          <Stat label="공식 대비 추정치 차이" value={`${usdBn(gap.diff_usd_bn)} (${pct(gap.diff_pct)})`} meta={gap.note} />
        )}
        <Stat label="최근 공식 성장속도(30일 환산)"
              value={vel ? usdBn(vel.delta_per_30d_usd_bn) : "—"}
              meta={vel ? `${vel.from}→${vel.to} · ${vel.label}` : "공식 2개 이상 필요"}
              cls={vel && vel.delta_per_30d_usd_bn >= 0 ? "up" : ""} />
        <Stat label="성장 가속·감속" value={ACCEL_LABEL[m.acceleration.state] || m.acceleration.state}
              meta={m.acceleration.note || `최근 ${usdBn(m.acceleration.recent_per30)} / 이전 ${usdBn(m.acceleration.prior_per30)}`} />
        {m.target_progress && (
          <Stat label="목표 진행률" value={pct(m.target_progress.vs_target_low_pct)}
                meta={`목표 ${usdBn(m.target_progress.target_low)} · ${m.target_progress.target_date ?? ""}`} />
        )}
        <Stat label="밸류에이션 / Run-rate"
              value={m.valuation_multiple ? `${m.valuation_multiple.multiple}x` : "—"}
              meta={m.valuation_multiple
                ? `${usdBn(m.valuation_multiple.valuation_usd_bn, 0)} / ${usdBn(m.valuation_multiple.runrate_usd_bn, 0)}${m.valuation_multiple.date_mismatch_warning ? " ⚠️날짜불일치" : ""}`
                : "—"}
              cls={m.valuation_multiple?.date_mismatch_warning ? "warn" : ""} />
        <Stat label="공식 데이터 신선도" value={cp.freshness.latest_official_as_of || "—"}
              meta={`마지막 수집 ${cp.quality.last_collect || "—"} · 생성 ${cp.freshness.generated_kst}`} />
      </div>

      <div className="card section">
        <h2>Official vs Estimated Run-rate</h2>
        <p className="hint">공식(실선)·추정/보도(점선)·파생(다이아몬드)은 별도 시계열로, 하나의 선으로 연결하지 않습니다.</p>
        <RunrateChart cp={cp} />
      </div>

      <div className="card section">
        <h2>최신 수준 해석</h2>
        <p className="hint">
          공식·파생·기관별 추정을 각각 그대로 나열합니다. 서로 다른 출처를 하나의 “현재 수준”으로 합치거나
          단일 결론(정체/가속)으로 단정하지 않습니다.
        </p>
        <table>
          <thead><tr><th>구분</th><th>값</th><th>기준일</th><th>출처</th><th>검증</th></tr></thead>
          <tbody>
            <tr>
              <td>공식 {off?.metric_type === "arr" ? "ARR" : "Run-rate"} 최신값</td>
              <td>{off ? pointValueText(off) : "—"}</td>
              <td>{off ? pointDate(off) : "—"}</td>
              <td>{off?.source_name ?? "—"}</td>
              <td>{vsBadge(off?.verification_status)}</td>
            </tr>
            {latestMonthly && (
              <tr>
                <td>공식 월매출 신호</td>
                <td>{pointValueText(latestMonthly)}/월</td>
                <td>{pointDate(latestMonthly)}</td>
                <td>{latestMonthly.source_name ?? "—"}</td>
                <td>{vsBadge(latestMonthly.verification_status)}</td>
              </tr>
            )}
            {latestDerived && (
              <tr>
                <td className="warn">파생 연환산(월매출×12, 공식 ARR 아님)</td>
                <td>{pointValueText(latestDerived)}</td>
                <td>{pointDate(latestDerived)}</td>
                <td>{latestDerived.source_name ?? "—"}</td>
                <td>{vsBadge(latestDerived.verification_status)}</td>
              </tr>
            )}
            {estBySource.map(({ source, point }) => (
              <tr key={source}>
                <td>{source} 외부 추정{isCandidate(point) ? " (후보)" : ""}</td>
                <td>{pointValueText(point)}</td>
                <td>{pointDate(point)}</td>
                <td>{point.source_url
                  ? <a href={point.source_url} target="_blank" rel="noreferrer">{point.source_name}</a>
                  : (point.source_name ?? source)}</td>
                <td>{vsBadge(point.verification_status)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        {divergence && (
          <p className="hint warn">
            기관별 최신 추정 편차: {divergence.high.source} {usdBn(divergence.high.value_usd_bn)}
            {" ↔ "}{divergence.low.source} {usdBn(divergence.low.value_usd_bn)}
            {" "}(차이 {usdBn(divergence.spread_usd_bn)}{divergence.spread_pct != null ? ` · ${divergence.spread_pct}%` : ""},
            {" "}{divergence.source_count}개 기관). {divergence.note}
          </p>
        )}
      </div>

      <div className="card section">
        <h2>Growth Velocity</h2>
        {vel ? (
          <table>
            <tbody>
              <tr><th>구간</th><td>{vel.from} → {vel.to} ({vel.days}일)</td></tr>
              <tr><th>증가액</th><td>{usdBn(vel.delta_usd_bn)}</td></tr>
              <tr><th>30일 환산</th><td>{usdBn(vel.delta_per_30d_usd_bn)}</td></tr>
              <tr><th>implied monthly growth</th><td>{pct(vel.implied_monthly_growth_pct)}</td></tr>
              <tr><th>비고</th><td className={vel.is_approximate ? "warn" : ""}>{vel.label}</td></tr>
            </tbody>
          </table>
        ) : <div className="empty">공식 수치가 2개 이상일 때 계산됩니다.</div>}
      </div>

      <div className="card section">
        <h2>성장 동인 / Product Drivers</h2>
        {cp.products.length > 0 ? (
          <table>
            <thead><tr><th>지표</th><th>값</th><th>전체 대비</th><th>기준일</th></tr></thead>
            <tbody>
              {m.product_contribution.map((p, i) => (
                <tr key={i}>
                  <td>{p.product} · {METRIC_LABEL[p.metric_name || ""] || p.metric_name}</td>
                  <td>{productValue(p)}</td>
                  <td>{p.share_pct != null ? `${p.share_pct}%` : (p.is_revenue ? "—" : "매출 아님")}{p.date_mismatch ? " ⚠️" : ""}</td>
                  <td>{p.as_of ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : <div className="empty">제품별 공개 데이터 없음</div>}
      </div>

      <div className="card section">
        <h2>업데이트 타임라인</h2>
        <table>
          <thead><tr><th>발표일</th><th>기준일</th><th>값</th><th>구분</th><th>출처</th><th>근거</th></tr></thead>
          <tbody>
            {[...s.official, ...s.reported, ...s.estimated, ...s.derived, ...s.monthly, ...s.target]
              .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""))
              .map((p, i) => (
                <tr key={i}>
                  <td>{p.published_at ?? "—"}</td>
                  <td>{pointDate(p)}</td>
                  <td>{pointValueText(p)}</td>
                  <td><span className={"badge " + (p.source_tier || "D")}>{p.metric_type || p.source_type}</span> {qualifierLabel(p.qualifier)}</td>
                  <td>{p.source_url ? <a href={p.source_url} target="_blank" rel="noreferrer">{p.source_name}</a> : (p.source_name ?? "—")}</td>
                  <td style={{ maxWidth: 320, color: "var(--muted)" }}>{p.evidence_text}</td>
                </tr>
              ))}
          </tbody>
        </table>
      </div>

      <div className="card section">
        <h2>데이터 품질</h2>
        <table>
          <tbody>
            <tr><th>공식 확정</th><td>{cp.quality.official_count}</td>
                <th>외부 추정</th><td>{cp.quality.estimate_count}</td></tr>
            <tr><th>파생값</th><td>{cp.quality.derived_count ?? 0}</td>
                <th>월 매출</th><td>{cp.quality.monthly_count ?? 0}</td></tr>
            <tr><th>검토 대기</th><td>{cp.quality.review_queue_count}</td>
                <th>기준일 불명확</th><td>{cp.quality.uncertain_asof_count}</td></tr>
            <tr><th>마지막 수집</th><td colSpan={3}>{cp.quality.last_collect || "—"}</td></tr>
          </tbody>
        </table>
      </div>
    </>
  );
}
