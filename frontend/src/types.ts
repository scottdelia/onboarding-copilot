/** Shapes of `public/data/site.json`, written by tools/build_site_data.py. */

export type Owner = 'agent' | 'ops' | 'carrier' | 'state_doi' | 'vendor';

/** Who a step belongs to, and whether it is ours to shorten. */
export const OWNER_LABEL: Record<Owner, string> = {
  agent: 'Agent',
  ops: 'Ops',
  carrier: 'Carrier',
  state_doi: 'State DOI',
  vendor: 'Vendor',
};

/**
 * The load-bearing distinction in the whole application. Ops and the agent are
 * the only owners a tool of ours can act on; the rest is somebody else's queue.
 * Colour follows that split rather than following the step order, so the
 * pipeline shows at a glance how little of it is ours.
 */
export const OWNER_IS_EXTERNAL: Record<Owner, boolean> = {
  agent: false,
  ops: false,
  carrier: true,
  state_doi: true,
  vendor: true,
};

export const OWNER_TIER: Record<Owner, string> = {
  agent: 'var(--tier-standard-plus)',
  ops: 'var(--accent)',
  carrier: 'var(--tier-table-rated)',
  state_doi: 'var(--tier-decline)',
  vendor: 'var(--tier-standard)',
};

export interface Step {
  step_id: string;
  name: string;
  owner: Owner;
  status: string;
  blocker: string;
  blocker_detail: string;
  touch_minutes: number;
  wait_hours: number;
  idle_hours: number;
  automatable_by: string;
  on_critical_path: boolean;
  note: string;
}

export interface Gap {
  key: string;
  rule_id: string;
  carrier_id: string | null;
  carrier_name: string | null;
  severity: 'blocking' | 'advisory';
  summary: string;
  expected: string;
  observed: string;
  owner: string;
  source: 'deterministic';
}

export interface Agent {
  agent_id: string;
  display_name: string;
  resident_state: string;
  npn: string;
  target_carriers: string[];
  demonstrates: string;
  days_elapsed: number;
  rework_hours: number;
  external_wait_hours: number;
  internal_touch_hours: number;
  internal_idle_hours: number;
  critical_chain: string[];
  steps: Step[];
  gaps: Gap[];
}

export interface Lever {
  after_hours: number;
  hours_removed: number;
  percent_removed: number;
}

export interface SiteData {
  anchor: string;
  engine_version: string;
  kill_threshold_pct: number;
  cycle_time: {
    cohort_size: number;
    baseline: { mean_hours: number; mean_days: number };
    decomposition: Record<string, number>;
    levers: Record<string, Lever>;
    assumptions: Record<string, unknown>;
  };
  sensitivity: {
    scenario: string;
    external_wait_share_pct: number;
    extraction_pct: number;
    rule_engine_pct: number;
    extraction_wins: boolean;
  }[];
  carriers: { carrier_id: string; name: string }[];
  agents: Agent[];
  extraction: {
    model: string;
    documents: number;
    accuracy_pct: number;
    wrong_pct: number;
    danger_confident_wrong_pct: number;
    criterion_threshold_pct: number;
    criterion_fires: boolean;
    cost_usd: number;
  } | null;
}
