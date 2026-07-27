import { useEffect, useState } from "react";
import type { Dashboard } from "./types";
import { usdBn, pct, pointValueText, pointDate, qualifierLabel } from "./format";
import RunrateChart from "./components/RunrateChart";

function Stat({ label, value, meta, cls }: { label: string; value: string; meta?: string; cls?: string }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className={"value " + (cls || "")}>{value}</div>
      {meta && <div className="meta">{meta}</div>}
    </div>
  );
}

const ACCEL_LABEL: Record<string, string> = {
  accelerating: "가속", decelerating: "감속", stable: "안정", insufficient_data: "데이터 부족",
};

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/dashboard.json`)
      .then((r) => { if (!r.ok) throw new Error("data " + r.status); return r.json(); })
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="wrap"><div className="empty">데이터를 불러오지 못했습니다: {err}</div></div>;
  if (!data) return <div className="wrap"><div className="empty">불러오는 중…</div></div>;

  const m = data.metrics;
  const off = m.latest_official;
  const est = m.latest_estimate;
  const gap = m.official_estimate_gap;
  const vel = m.growth_velocity;
  const hasAny = data.series.official.length + data.series.estimated.length +
                 data.series.reported.length + data.series.target.length > 0;

  return (
    <div className="wrap">
      <h1>📊 {data.display_name}</h1>
      <div className="sub">공식 Revenue Run-rate · 외부 추정 · 목표 · 밸류에이션 멀티플을 분리 추적</div>
      <div className="note">{data.note}</div>

      {!hasAny ? (
        <div className="card empty">
          아직 확정된 데이터가 없습니다. <br />
          <code>python -m tracker seed &amp;&amp; python -m tracker collect</code> 로 수집한 뒤
          <code> python -m tracker export</code> 로 갱신하세요.
        </div>
      ) : (
        <>
          <div className="cards">
            <Stat label="최신 공식 Run-rate" value={off ? pointValueText(off) : "—"}
                  meta={off ? `기준일 ${off.as_of_end} · ${off.source_name ?? ""}` : "공식 데이터 없음"} />
            <Stat label="최신 외부 추정치" value={est ? pointValueText(est) : "공개 추정 없음"}
                  meta={est ? `기준일 ${est.as_of_end}` : "—"} />
            <Stat label="공식 대비 추정치 차이"
                  value={gap ? `${usdBn(gap.diff_usd_bn)} (${pct(gap.diff_pct)})` : "—"}
                  meta={gap ? gap.note : "추정치 없음"} />
            <Stat label="최근 공식 성장속도(30일 환산)"
                  value={vel ? usdBn(vel.delta_per_30d_usd_bn) : "—"}
                  meta={vel ? `${vel.from}→${vel.to} · ${vel.label}` : "공식 2개 이상 필요"}
                  cls={vel && vel.delta_per_30d_usd_bn >= 0 ? "up" : ""} />
            <Stat label="성장 가속·감속" value={ACCEL_LABEL[m.acceleration.state] || m.acceleration.state}
                  meta={m.acceleration.note || `최근 ${usdBn(m.acceleration.recent_per30)} / 이전 ${usdBn(m.acceleration.prior_per30)}`} />
            <Stat label="목표 진행률"
                  value={m.target_progress ? pct(m.target_progress.vs_target_low_pct) : "목표 없음"}
                  meta={m.target_progress ? `목표 ${usdBn(m.target_progress.target_low)} · ${m.target_progress.target_date ?? ""}` : "—"} />
            <Stat label="밸류에이션 / Run-rate"
                  value={m.valuation_multiple ? `${m.valuation_multiple.multiple}x` : "—"}
                  meta={m.valuation_multiple
                    ? `${usdBn(m.valuation_multiple.valuation_usd_bn, 0)} / ${usdBn(m.valuation_multiple.runrate_usd_bn, 0)}${m.valuation_multiple.date_mismatch_warning ? " ⚠️날짜불일치" : ""}`
                    : "—"}
                  cls={m.valuation_multiple?.date_mismatch_warning ? "warn" : ""} />
            <Stat label="공식 데이터 신선도" value={data.freshness.latest_official_as_of || "—"}
                  meta={`마지막 수집 ${data.quality.last_collect || "—"} · 생성 ${data.freshness.generated_kst}`} />
          </div>

          <div className="card section">
            <h2>Official vs Estimated Run-rate</h2>
            <p className="hint">공식(실선)과 추정·보도(점선)는 별도 시계열로, 하나의 선으로 연결하지 않습니다.</p>
            <RunrateChart data={data} />
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
            <h2>Product Drivers</h2>
            {data.products.length > 0 ? (
              <table>
                <thead><tr><th>제품</th><th>Run-rate</th><th>전체 대비</th><th>기준일</th></tr></thead>
                <tbody>
                  {m.product_contribution.map((p, i) => (
                    <tr key={i}>
                      <td>{p.product}</td>
                      <td>{usdBn(p.value_usd_bn)}{p.qualifier === "over" ? " 이상" : ""}</td>
                      <td>{p.share_pct != null ? `${p.share_pct}%` : "—"}{p.date_mismatch ? " ⚠️" : ""}</td>
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
                {[...data.series.official, ...data.series.reported, ...data.series.estimated, ...data.series.target]
                  .sort((a, b) => (b.published_at || "").localeCompare(a.published_at || ""))
                  .map((p, i) => (
                    <tr key={i}>
                      <td>{p.published_at ?? "—"}</td>
                      <td>{pointDate(p)}</td>
                      <td>{pointValueText(p)}</td>
                      <td><span className={"badge " + (p.source_tier || "D")}>{p.source_type}</span> {qualifierLabel(p.qualifier)}</td>
                      <td>{p.source_url ? <a href={p.source_url} target="_blank" rel="noreferrer">{p.source_name}</a> : (p.source_name ?? "—")}</td>
                      <td style={{ maxWidth: 320, color: "var(--muted)" }}>{p.evidence_text}</td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      <div className="card section">
        <h2>데이터 품질</h2>
        <table>
          <tbody>
            <tr><th>공식 확정</th><td>{data.quality.official_count}</td>
                <th>외부 추정</th><td>{data.quality.estimate_count}</td></tr>
            <tr><th>검토 대기</th><td>{data.quality.review_queue_count}</td>
                <th>기준일 불명확</th><td>{data.quality.uncertain_asof_count}</td></tr>
            <tr><th>마지막 수집</th><td colSpan={3}>{data.quality.last_collect || "—"}</td></tr>
            <tr><th>최근 오류</th><td colSpan={3}>{data.quality.last_errors.length ? data.quality.last_errors.join("; ") : "없음"}</td></tr>
          </tbody>
        </table>
      </div>

      <div className="footer">
        Revenue Run-rate ≠ 회계상 연간 매출 · 공식/추정 분리 · 출처 원문 링크 제공 · 생성 {data.freshness.generated_kst} KST
      </div>
    </div>
  );
}
