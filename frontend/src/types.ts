// Types for the BioValue AI API (backend/main.py). They mirror the backend's Pydantic models.

export type Quality = 'high' | 'moderate' | 'low' | 'unverified'
export type ScenarioName = 'conservative' | 'base' | 'optimistic'
export const SCENARIOS: ScenarioName[] = ['conservative', 'base', 'optimistic']

export interface Quantity {
  value: number | null
  low?: number | null
  high?: number | null
  unit: string
  basis: string
  method?: string
  note?: string
}

export interface Asset {
  kind: string
  name: string
  status: 'operating' | 'planned' | 'not_available'
  capacity?: Quantity | null
  note?: string
}

export interface DataGap {
  field: string
  issue: 'missing' | 'uncertain' | 'method_unclear' | 'fictional'
  severity: 'low' | 'medium' | 'high'
  impact: string
  next_step: string
}

export interface Feedstock {
  id: string
  name: string
  data_status: 'fictional_demo' | 'measured' | 'mixed'
  disclaimer: string
  feedstock_type: string
  wood_type: 'softwood' | 'hardwood' | 'mixed'
  annual_wet_quantity: Quantity
  moisture_pct: Quantity
  dry_matter: Quantity
  composition: Record<string, Quantity | Record<string, Quantity>>
  variability: { summary: string; drivers: string[] }
  current_use: { route: string; description: string }
  infrastructure: Asset[]
  geographic_market: { mill_location: string; target_markets: string[]; logistics: string }
  data_gaps: DataGap[]
}

export interface ScenarioInput {
  base: number
  conservative?: number | null
  optimistic?: number | null
  unit: string
  basis: string
  evidence_ids?: string[]
  note: string
}

export interface CostItem {
  name: string
  rate: ScenarioInput
  per: 'product' | 'usable_feedstock'
}

export interface PathwayAssumptions {
  product: string
  availability?: ScenarioInput
  product_yield?: ScenarioInput
  price?: ScenarioInput
  variable_costs?: CostItem[]
}

export type EconomicAssumptions = Record<string, PathwayAssumptions>

export interface Pathway {
  id: string
  code: string
  name: string
  description: string
  example_products: string[]
  incumbent_materials: string[]
}

export interface RubricEntry {
  label: string
  question: string
  how_scored: string
  levels: Record<string, string>
}

export interface ScoringConfig {
  weights: Record<string, number>
  min_completeness: number
  rubric: Record<string, RubricEntry>
}

export interface ProjectInfo {
  name: string
  feedstock: Feedstock
  economic_assumptions: EconomicAssumptions
  pathways: Pathway[]
  scoring: ScoringConfig
  agents: { id: string; title: string }[]
}

export interface Step {
  key: string
  label: string
  status: 'calculated' | 'not_calculated'
  value: number | null
  unit: string
  formula: string
  inputs: string[]
  reason: string
  warnings: string[]
}

export interface AssumptionLine {
  input: string
  conservative: number | null
  base: number
  optimistic: number | null
  unit: string
  held_constant: boolean
  basis: string
  evidence_ids: string[]
  note: string
}

export interface ScenarioAnalysis {
  pathway_id: string
  product: string
  scenarios: Record<ScenarioName, { scenario: ScenarioName; steps: Record<string, Step> }>
  assumptions: AssumptionLine[]
  missing_inputs: string[]
  not_calculated_metrics: string
}

export interface Assessment {
  criterion: string
  score: number | null
  method: 'rule' | 'analyst' | 'none'
  rationale: string
  evidence_ids: string[]
  inputs: string[]
}

export interface CriterionResult extends Assessment {
  label: string
  weight: number
  status: 'assessed' | 'not_assessed'
  meaning: string
  weighted_contribution: number | null
}

export interface OpportunityResult {
  pathway_id: string
  name: string
  criteria: CriterionResult[]
  attractiveness: number | null
  attractiveness_range: [number, number]
  completeness: { assessed_weight: number; assessed: string[]; not_assessed: string[]; missing_inputs: string[] }
  evidence: { cited_records: string[]; by_quality: Record<Quality, number>; strongest: Quality | null; criteria_without_evidence: string[] }
  status: 'ranked' | 'insufficient_data'
  rank: number | null
}

export interface Ranking {
  weights: Record<string, number>
  min_completeness: number
  ranked: OpportunityResult[]
  insufficient_data: OpportunityResult[]
}

export interface EvidenceFinding {
  statement: string
  evidence: string[]
}

export interface Judgment {
  score: number
  rationale: string
  evidence: string[]
}

export interface FeedstockAgentOutput {
  feedstock_id: string
  is_fictional: boolean
  wet_mass_t_per_yr: number
  moisture_fraction: number
  dry_mass_t_per_yr: number
  missing_properties: string[]
  inconsistencies: string[]
  constraints: string[]
  data_quality_notes: string[]
  summary: string
}

export interface PathwayMarket {
  pathway_id: string
  applications: EvidenceFinding[]
  target_customers: EvidenceFinding[]
  competing_materials: EvidenceFinding[]
  qualification_requirements: EvidenceFinding[]
  limitations: string[]
  missing_information: string[]
  market_evidence: Judgment | null
}

export interface PathwayCommercialization {
  pathway_id: string
  processing_requirements: EvidenceFinding[]
  technical_maturity: EvidenceFinding | null
  adoption_barriers: EvidenceFinding[]
  missing_inputs: string[]
  assumptions: string[]
  uncertainties: string[]
  commercialization_feasibility: Judgment | null
}

export interface DecisionReport {
  shortlist: { pathway_id: string; rank: number | null; main_drivers: string[]; what_could_change_it: string[] }[]
  validation_steps: { action: string; reason: string; addresses: string[] }[]
  ranking_changers: string[]
  caveats: string[]
  summary: string
}

export interface Normalized {
  feedstock_id: string
  is_fictional: boolean
  wet_mass_t_per_yr: number
  moisture_fraction: number
  dry_mass_t_per_yr: number
  dry_lignin_t_per_yr: number | null
  composition: Record<string, Quantity>
  other_composition: Record<string, Quantity>
}

export interface Checks {
  checks: { check: string; passed: boolean; detail: string }[]
  inconsistencies: string[]
  missing_fields: string[]
  data_gaps: DataGap[]
  data_status: string
  disclaimer: string
  infrastructure: Record<'operating' | 'planned' | 'not_available', string[]>
  ranges: Record<string, { low: number | null; high: number | null; unit: string }>
}

export interface ToolCall {
  agent: string
  tool: string
  arguments: Record<string, unknown>
  status: 'ok' | 'rejected' | 'error'
  result: string
  seconds: number
}

export interface Usage {
  requests: number
  tool_calls: number
  input_tokens: number
  cache_read_tokens: number
  output_tokens: number
  reasoning_tokens: number | null
}

export interface SecurityEvent {
  kind: string
  source: string
  field: string
  matched: string[]
}

export interface LedgerItem {
  statement: string
  source: string
}

export interface Ledger {
  documented_facts: LedgerItem[]
  assumptions: LedgerItem[]
  estimates: LedgerItem[]
  unknowns: LedgerItem[]
}

export interface AgentRun {
  agent: string
  order: number
  status: 'pending' | 'running' | 'ok' | 'failed' | 'skipped'
  attempts: number
  started_at: string | null
  finished_at: string | null
  seconds: number | null
  usage: Usage
  tool_calls: ToolCall[]
  guard_events: { agent: string; action: 'retry_requested' | 'fixed_by_code'; problems: string[] }[]
  errors: string[]
  skipped_reason: string
}

export interface Trace {
  run_id: string
  model: string
  config: string
  token_budget: number | null
  started_at: string
  finished_at: string | null
  agents: AgentRun[]
  security_events: SecurityEvent[]
}

export interface FinalAssessment {
  run_id: string
  created_at: string
  model: string
  config: string
  project_id: string
  project_name: string
  status: 'complete' | 'partial' | 'failed'
  disclaimers: string[]
  feedstock: { agent: FeedstockAgentOutput; normalized: Normalized; checks: Checks } | null
  market: { pathway_id: string; source_ids: string[]; supported_claims: Record<string, string>; findings: PathwayMarket }[] | null
  commercialization: {
    pathway_id: string
    findings: PathwayCommercialization
    feedstock_compatibility: Assessment
    technical_readiness: Assessment
    indicative_economics: Assessment
    scenario_analysis: ScenarioAnalysis
  }[] | null
  decision: { ranking: Ranking; ranking_source: string; report: DecisionReport | null }
  ledger: Ledger | null
  execution: Trace
  usage: Usage
  cost: { status: 'calculated' | 'not_calculated'; usd: number | null; note: string; proxy_usd: number | null; proxy_note: string }
}

export interface RunResponse {
  run_id: string
  status: 'running' | 'complete' | 'partial' | 'failed' | 'error'
  started_at: string
  finished_at: string | null
  error: string | null
  trace: Trace
  result: FinalAssessment | null
}

export interface Preview {
  feedstock: { profile: Feedstock; normalized: Normalized; checks: Checks }
  uncertainty_flags: string[]
  pathways: { pathway_id: string; name: string; compatibility: Assessment; indicative_economics: Assessment; scenario_analysis: ScenarioAnalysis }[]
}

export interface Claim {
  text: string
  status: 'supported' | 'unverified'
  support: string
}

export interface Requirement {
  parameter: string
  requirement: string
  applies_to: string
  property: string | null
  min: number | null
  max: number | null
  status: 'supported' | 'unverified'
  support: string
}

export interface EvidenceRecord {
  id: string
  pathway: string
  title: string
  publisher: string
  authors: string
  published: string | null
  url: string | null
  url_verified_on: string | null
  source_type: string
  quality: Quality
  claims: Claim[]
  technical_requirements: Requirement[]
  limitations: string[]
}

export interface EvidenceLibrary {
  quality_labels: Record<Quality, string>
  pathways: Pathway[]
  records: EvidenceRecord[]
}

export interface Health {
  ok: boolean
  model: string
  api_key_configured: boolean
  active_run: string | null
}

export interface FieldError {
  field: string
  message: string
}

export interface Inputs {
  feedstock: Feedstock
  economic_assumptions: EconomicAssumptions
}

export interface RunWithInputs extends RunResponse {
  inputs?: { feedstock: Feedstock | null; economic_assumptions: EconomicAssumptions | null } | null
}
