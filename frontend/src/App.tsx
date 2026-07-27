import { useEffect, useState } from "react";
import type { Dashboard } from "./types";
import CompanyView from "./components/CompanyView";
import ComparisonView from "./components/ComparisonView";

type Tab = "compare" | string; // "compare" 또는 회사 slug

export default function App() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("compare");

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/dashboard.json`)
      .then((r) => { if (!r.ok) throw new Error("data " + r.status); return r.json(); })
      .then(setData)
      .catch((e) => setErr(String(e)));
  }, []);

  if (err) return <div className="wrap"><div className="empty">데이터를 불러오지 못했습니다: {err}</div></div>;
  if (!data) return <div className="wrap"><div className="empty">불러오는 중…</div></div>;

  const order = data.company_order || Object.keys(data.companies);

  return (
    <div className="wrap">
      <h1>📊 {data.display_name}</h1>
      <div className="sub">Anthropic·OpenAI 공식 Revenue Run-rate/ARR · 외부 추정 · 파생 · 밸류에이션을 분리 추적·비교</div>
      <div className="note">{data.note}</div>

      <div className="tabs">
        <button className={"tab" + (tab === "compare" ? " on" : "")} onClick={() => setTab("compare")}>비교</button>
        {order.map((slug) => (
          <button key={slug} className={"tab" + (tab === slug ? " on" : "")} onClick={() => setTab(slug)}>
            {data.companies[slug]?.display_name || slug}
          </button>
        ))}
      </div>

      {tab === "compare"
        ? <ComparisonView cmp={data.comparison} />
        : data.companies[tab]
          ? <CompanyView cp={data.companies[tab]} />
          : <div className="empty">회사를 찾을 수 없습니다.</div>}

      <div className="footer">
        Revenue Run-rate ≠ 회계상 연간 매출 · 공식/추정/파생 분리 · 출처 원문 링크 제공 · 생성 {data.generated_kst} KST
      </div>
    </div>
  );
}
