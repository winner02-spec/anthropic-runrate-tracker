export type Qualifier =
  | "exact" | "approximately" | "approaching" | "over" | "range" | "target" | "estimate" | "reported" | "derived";

export interface Point {
  value_low_usd_bn: number | null;
  value_high_usd_bn: number | null;
  metric_type?: string | null;
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
  is_derived?: number;
  calculation_method?: string | null;
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
  qualifier?: string | null;
  unit?: string | null;
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

export interface ValuationMultiple {
  valuation_usd_bn: number; runrate_usd_bn: number; multiple: number; basis: string;
  valuation_as_of?: string; runrate_as_of?: string; date_gap_days?: number | null; date_mismatch_warning?: boolean;
}

export interface GrowthVelocity {
  delta_usd_bn: number; days: number; delta_per_30d_usd_bn: number;
  implied_monthly_growth_pct: number | null; from: string; to: string; is_approximate: boolean; label: string;
}

export interface EstimateBySource {
  source: string;
  point: Point;
}

export interface EstimateDivergence {
  high: { source: string; value_usd_bn: number; as_of?: string | null };
  low: { source: string; value_usd_bn: number; as_of?: string | null };
  spread_usd_bn: number;
  spread_pct: number | null;
  source_count: number;
  note: string;
}

export interface Metrics {
  latest_official: Point | null;
  latest_estimate: Point | null;
  latest_estimates_by_source?: EstimateBySource[];
  estimate_divergence?: EstimateDivergence | null;
  official_estimate_gap:
    | { official: number; estimate: number; diff_usd_bn: number; diff_pct: number | null; note: string; official_as_of?: string; estimate_as_of?: string }
    | null;
  growth_velocity: GrowthVelocity | null;
  acceleration: { state: string; note?: string; recent_per30?: number; prior_per30?: number };
  target_progress:
    | { official: number; target_low: number | null; target_high: number | null; target_date?: string; vs_target_low_pct?: number | null; vs_target_high_pct?: number | null; already_exceeded?: boolean; days_to_target?: number }
    | null;
  valuation_multiple: ValuationMultiple | null;
  product_contribution: Array<{ product: string; metric_name?: string | null; value_usd_bn: number | null; qualifier?: string | null; unit?: string | null; is_revenue?: boolean; share_pct: number | null; as_of?: string | null; date_mismatch?: boolean }>;
}

export interface Quality {
  official_count: number;
  estimate_count: number;
  target_count: number;
  derived_count?: number;
  monthly_count?: number;
  verified_count?: number;
  corroborated_count?: number;
  provisional_count?: number;
  needs_review_count?: number;
  review_queue_count: number;
  uncertain_asof_count: number;
  last_collect: string | null;
  last_errors: string[];
}

export interface CompanySeries {
  official: Point[]; estimated: Point[]; reported: Point[]; target: Point[];
  derived: Point[]; monthly: Point[];
}

export interface CompanyPayload {
  slug: string;
  display_name: string;
  note: string;
  series: CompanySeries;
  valuations: Valuation[];
  products: ProductMetric[];
  events: EventItem[];
  metrics: Metrics;
  quality: Quality;
  freshness: { latest_official_as_of: string | null; generated_kst: string };
}

export interface ComparisonCompany {
  display_name: string;
  latest_official: Point | null;
  official_metric_type?: string | null;
  official_series: Point[];
  estimated_series: Point[];
  derived_series: Point[];
  monthly_series: Point[];
  growth_velocity: GrowthVelocity | null;
  valuation_multiple: ValuationMultiple | null;
  normalized: Array<{ as_of_end?: string | null; value_usd_bn: number; index: number }>;
  latest_official_as_of: string | null;
}

export interface Comparison {
  anchor: string;
  note: string;
  definition_note?: string;
  companies: Record<string, ComparisonCompany>;
}

export interface Dashboard {
  schema: string;
  display_name: string;
  note: string;
  generated_kst: string;
  company_order: string[];
  companies: Record<string, CompanyPayload>;
  comparison: Comparison;
}
