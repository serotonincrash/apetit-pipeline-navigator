// Internal names turned into the words people see. Terms follow docs/glossary.md.

const REGIONS: Record<string, string> = {
  FI_SW: "South-west Finland",
  SE_SKANE: "Skåne",
};

const CROPS: Record<string, string> = {
  pea: "Pea",
  turnip_rape: "Turnip rape",
  potato: "Potato",
  carrot: "Carrot",
  spinach: "Spinach",
};

const CLIMATE_SCENARIOS: Record<string, string> = {
  historical: "Past weather",
  baseline: "1991–2020 weather",
  ssp126: "Low emissions (SSP1-2.6)",
  ssp245: "Middle (SSP2-4.5)",
  ssp585: "High emissions (SSP5-8.5)",
};

const TRANSITION_SCENARIOS: Record<string, string> = {
  today: "Today's premiums",
  net_zero_2050: "Net Zero 2050",
  below_2c: "Below 2°C",
  low_demand: "Low Demand",
  delayed_transition: "Delayed Transition",
  fragmented_world: "Fragmented World",
  ndcs: "Nationally Determined Contributions (NDCs)",
  current_policies: "Current Policies",
};

/** The climate scenarios of the Risk view, low to high. Each has a fixed colour. */
export const FUTURE_SCENARIOS = ["ssp126", "ssp245", "ssp585"] as const;
export type FutureScenario = (typeof FUTURE_SCENARIOS)[number];

/** The transition scenarios that go with each climate scenario, from the glossary. */
export const TRANSITION_BY_CLIMATE: Record<string, string[]> = {
  baseline: ["today"],
  ssp126: ["net_zero_2050", "below_2c", "low_demand"],
  ssp245: ["delayed_transition", "fragmented_world", "ndcs"],
  ssp585: ["current_policies"],
};

export const DEFAULT_TRANSITION: Record<string, string> = {
  baseline: "today",
  ssp126: "net_zero_2050",
  ssp245: "delayed_transition",
  ssp585: "current_policies",
};

const TABLES: Record<string, string> = {
  farm_survey: "Farm survey",
  farm_survey_clean: "Farm survey, cleaned",
  farm_registry: "Farm registry",
  farm_registry_clean: "Farm registry, cleaned",
  foodhills: "Foodhills growing data",
  foodhills_clean: "Foodhills growing data, cleaned",
  parcels: "Parcels",
  crop_history: "Crop history and plan",
  grid: "Weather grid",
  erp_purchase_lines: "Purchase lines",
  weather_daily: "Daily weather",
  dev_issue_labels: "Known data issues, 2023–24",
  c1_template: "Yield submission template",
  climate_change_signals: "Climate change signals",
  contract_prices: "Contract prices and replacement premiums",
  transition_scenarios: "Transition scenarios",
  training_table: "Training table",
  parcel_year_contract: "Contract parcels by year",
  parcel_seasons: "Simulated parcel seasons",
  yield_draws: "Simulated seasons, yield",
  yield_projection: "Yield projection",
  yield_coefficients: "Yield model coefficients",
  yield_fit: "Yield model fit",
  farm_levels: "Farm yield levels",
  yield_backtest: "Yield model backtest",
  model_table: "Model table",
  contracted_volume: "Contracted volume",
  priced_draws: "Simulated seasons, priced",
  climate_risk: "Climate risk by crop and region",
  climate_risk_total: "Climate risk, totals",
  foodhills_cover: "Foodhills cover",
  action_results: "Action results",
  actions_not_run: "Actions not priced",
  calendar_choice: "Crop calendar choice",
  calendar_tuning: "Crop calendar tuning",
  crop_params: "Crop calendar",
  import_factors: "Import emission factors",
  loss_drivers: "Loss drivers",
  parcel_features: "Parcel weather measures",
  parcel_year_features: "Parcel-year weather measures",
  premiums: "Replacement premiums",
  rule_validation: "Data check results",
  weather_features_cell: "Weather measures by cell",
};

const STEPS: Record<string, string> = {
  load_raw: "Load package files",
  check_farm_data: "Check farm data",
  propose_fixes: "Propose fixes",
  explain_proposals: "Explain suggested fixes",
  apply_approved: "Apply approved fixes",
  spatial_join: "Match parcels to weather cells",
  tune_calendar: "Tune crop calendar",
  weather_features: "Build weather measures",
  fit_yield_model: "Fit yield model",
  project_yields: "Project yields",
  price_risk: "Price the risk",
  compare_actions: "Compare actions",
};

const COLUMNS: Record<string, string> = {
  region: "Region",
  crop: "Crop",
  scenario: "Climate scenario",
  ngfs_scenario: "Transition scenario",
  farm_id: "Farm",
  ngfs: "Transition scenario",
  parcel_id: "Parcel",
  cell_id: "Weather cell",
  year: "Season",
  record_key: "Record",
};

const MEASURES: Record<string, string> = {
  "price_risk.expected_cost_eur": "Expected cost per year",
  "price_risk.one_in_ten_cost_eur": "Cost in a 1-in-10 bad year",
  "price_risk.expected_import_tco2e": "Extra emissions per year",
  "price_risk.climate_added_cost_eur": "Cost added by climate change",
  "project_yields.bad_year_chance": "Chance of a bad year",
  "project_yields.yield_change_pct": "Yield change",
  "fit_yield_model.production_error_pct": "Model error",
  "fit_yield_model.baseline_production_error_pct": "Farm average error",
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  pending: "Pending",
  reused: "Reused",
  open: "Open",
  approved: "Approved",
  rejected: "Rejected",
  flag: "Flag",
  draft: "Draft",
  in_review: "In review",
  published: "Published",
  superseded: "Superseded",
};

export const ROLE_LABELS: Record<string, string> = {
  data_specialist: "Data specialist",
  sustainability_specialist: "Sustainability specialist",
};

export function sentenceCase(code: string): string {
  const spaced = code.replaceAll("_", " ").trim();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function lookup(map: Record<string, string>, code: string): string {
  return map[code] ?? sentenceCase(code);
}

export const regionLabel = (code: string) => lookup(REGIONS, code);
export const cropLabel = (code: string) => lookup(CROPS, code);
export const climateLabel = (code: string) => lookup(CLIMATE_SCENARIOS, code);
export const transitionLabel = (code: string) => lookup(TRANSITION_SCENARIOS, code);
export const tableLabel = (code: string) => lookup(TABLES, code);
export const stepLabel = (code: string) => lookup(STEPS, code);
export const columnLabel = (code: string) => lookup(COLUMNS, code);
export const measureLabel = (code: string) => lookup(MEASURES, code);
export const statusLabel = (code: string) => lookup(STATUS_LABELS, code);
export const roleLabel = (code: string) => lookup(ROLE_LABELS, code);

export const REGION_CODES = Object.keys(REGIONS);
export const CROP_CODES = Object.keys(CROPS);

/** One lineage filter entry, such as `crop=pea`, written in plain words. */
function filterPart(column: string, value: string): string {
  if (column === "region") return regionLabel(value);
  if (column === "crop") return cropLabel(value);
  if (column === "scenario") return climateLabel(value);
  if (column === "ngfs_scenario" || column === "ngfs") return transitionLabel(value);
  return `${columnLabel(column)} ${value}`;
}

const SHIFTED_TABLES = new Set(["parcel_seasons", "yield_draws", "priced_draws"]);

/** The lineage filter of one table in plain words, for the Sources panel. */
export function filterInWords(table: string, filters: string[]): string {
  if (filters.length === 0) return "Every row";
  const pairs = filters.map((entry) => {
    const at = entry.indexOf("=");
    return [entry.slice(0, at), entry.slice(at + 1)] as const;
  });
  const grouped = new Map<string, string[]>();
  for (const [column, value] of pairs) grouped.set(column, [...(grouped.get(column) ?? []), value]);
  const parts = [...grouped].map(([column, values]) => {
    const words = values.map((value) => filterPart(column, value));
    return words.length > 3
      ? `${words.length} ${columnLabel(column).toLowerCase()}s`
      : words.join(" or ");
  });
  const scenarios = grouped.get("scenario") ?? [];
  const shifted = SHIFTED_TABLES.has(table) && scenarios.some((s) => s.startsWith("ssp"));
  if (shifted) parts.push("30 past seasons shifted to 2041 to 2060");
  return parts.join(", ");
}

/** The two-part label of a table row in the Risk view. */
export const placeLabel = (crop: string, region: string) =>
  `${cropLabel(crop)}, ${regionLabel(region)}`;

/** Who wrote a suggestion, in plain words. */
export function proposerLabel(proposer: string): string {
  const rule = /^rule (\w+)/.exec(proposer);
  if (rule) return `Suggested by data check ${rule[1]}`;
  return "Suggested by the assistant";
}
