export type Qualifier =
  | "exact" | "approximately" | "approaching" | "over" | "range" | "target" | "estimate" | "reported";

export interface Point {
  value_low_usd_bn: number | null;
  value_high_usd_bn: number | null;
  qualifier: Qualifier;
  as_of_start?: string | null;
  as_of_end?: string | null;
  date_precision?: string | null;
  published_at?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  source_tier?: string | null;
  source_type?: string | null;
  confidence_score?: number | null;
  evidence_text?: string | null;
  is_official?: number;
  is_estimate?: number;
  is_target?: number;
  verification_status?: "verified" | "corroborated" | "provisional" | "needs_review" | null;
  verification_reason?: string | null;
  source_note?: string | null;
  evidence_note?: string | null;
}

export interface Valuation {
  as_of_date?: string | null;
  published_at?: string | null;
  money_basis?: string | null;
  valuation_usd_bn?: number | null;
  investment_usd_bn?: number | null;
  round_name?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  is_official?: number;
  evidence_text?: string | null;
}

export interface ProductMetric {
  product: string;
  metric_name?: string;
  value_usd_bn?: number | null;
  as_of_date?: string | null;
  source_name?: string | null;
  source_url?: string | null;
  evidence_text?: string | null;
}

export interface EventItem {
  event_date?: string | null;
  event_type?: string | null;
  title?: string | null;
  description?: string | null;
  source_url?: string | null;
}

export interface Metrics {
  latest_official: Point | null;
  latest_estimate: Point | null;
  official_estimate_gap:
    | { official: number; estimate: number; diff_usd_bn: number; diff_pct: number | null; note: string; official_as_of?: string; estimate_as_of?: string }
    | null;
  growth_velocity:
    | { delta_usd_bn: number; days: number; delta_per_30d_usd_bn: number; implied_monthly_growth_pct: number | null; from: string; to: string; is_approximate: boolean; label: string }
    | null;
  acceleration: { state: string; note?: string; recent_per30?: number; prior_per30?: number };
  target_progress:
    | { official: number; target_low: number | null; target_high: number | null; target_date?: string; vs_target_low_pct?: number | null; vs_target_high_pct?: number | null; already_exceeded?: boolean; days_to_target?: number }
    | null;
  valuation_multiple:
    | { valuation_usd_bn: number; runrate_usd_bn: number; multiple: number; basis: string; valuation_as_of?: string; runrate_as_of?: string; date_gap_days?: number | null; date_mismatch_warning?: boolean }
    | null;
  product_contribution: Array<{ product: string; value_usd_bn: number | null; qualifier?: string | null; share_pct: number | null; as_of?: string | null; date_mismatch?: boolean }>;
}

export interface Quality {
  official_count: number;
  estimate_count: number;
  target_count: number;
  review_queue_count: number;
  uncertain_asof_count: number;
  last_collect: string | null;
  last_errors: string[];
}

export interface Dashboard {
  display_name: string;
  note: string;
  series: { official: Point[]; estimated: Point[]; reported: Point[]; target: Point[] };
  valuations: Valuation[];
  products: ProductMetric[];
  events: EventItem[];
  metrics: Metrics;
  quality: Quality;
  freshness: { latest_official_as_of: string | null; generated_kst: string };
}
