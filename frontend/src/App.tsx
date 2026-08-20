import { useEffect, useState, type CSSProperties } from 'react';
import { OWNER_LABEL, OWNER_TIER, type Agent, type SiteData } from './types';
import { CycleTimePanel } from './components/CycleTimePanel';
import { AgentDetail } from './components/AgentDetail';

/**
 * The whole application: a finding, a cohort, and one agent at a time.
 *
 * There is no backend. Unlike the sibling Underwriting Copilot, which answers
 * free text and therefore needs a model behind a server, this app answers
 * nothing. It shows a fixed cohort and functions of it. Everything is computed
 * once by tools/build_site_data.py and served as a file. That is the correct
 * shape for an application with no query, not a workaround for deployment.
 *
 * The cycle-time panel comes first and the cohort second, because the finding
 * is the point and the cohort is the evidence for it. Leading with the board
 * would make this look like an ops dashboard that happens to have a chart.
 */

function Mark() {
  return (
    <svg viewBox="0 0 32 32" aria-hidden className="size-8 shrink-0">
      <rect width="32" height="32" rx="8" fill="var(--ink)" />
      <rect x="7" y="8" width="18" height="3.5" rx="1.75" fill="var(--tier-decline)" />
      <rect x="7" y="14" width="6" height="3.5" rx="1.75" fill="var(--tier-table-rated)" />
      <rect x="7" y="20" width="3" height="3.5" rx="1.75" fill="var(--tier-preferred-plus)" />
    </svg>
  );
}

/** One row of the cohort board. */
function AgentRow({
  agent,
  selected,
  onSelect,
}: {
  agent: Agent;
  selected: boolean;
  onSelect: () => void;
}) {
  // The step that is currently holding this agent up, which is what a person
  // scanning the board actually wants to know.
  const current =
    agent.steps.find((step) => step.status !== 'complete' && step.status !== 'not_started') ??
    agent.steps.find((step) => step.status !== 'complete');
  const owner = current?.owner ?? 'ops';
  const style = { '--tier': OWNER_TIER[owner] } as CSSProperties;
  const blocking = agent.gaps.filter((gap) => gap.severity === 'blocking').length;

  return (
    <li>
      <button
        type="button"
        onClick={onSelect}
        aria-current={selected}
        className={`tier-rail flex w-full flex-wrap items-center gap-x-4 gap-y-1.5 border-b border-line px-4 py-3 text-left transition-colors last:border-b-0 ${
          selected ? 'bg-surface-inset' : 'hover:bg-surface-inset'
        }`}
        style={style}
      >
        <span className="min-w-0 flex-1 basis-40">
          <span className="block truncate text-sm font-medium text-ink">
            {agent.display_name}
          </span>
          <span className="block truncate text-xs text-ink-faint">
            {current?.name ?? 'Complete'}
          </span>
        </span>

        <span className="tier-chip" style={style}>
          <span className="tier-dot" style={style} />
          {OWNER_LABEL[owner]}
        </span>

        {blocking > 0 && (
          <span
            className="tier-chip"
            style={{ '--tier': 'var(--tier-decline)' } as CSSProperties}
          >
            {blocking} blocking
          </span>
        )}

        <span className="tabular w-16 shrink-0 text-right text-sm font-semibold text-ink">
          {agent.days_elapsed}d
        </span>
      </button>
    </li>
  );
}

export default function App() {
  const [data, setData] = useState<SiteData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}data/site.json`)
      .then((response) => {
        if (!response.ok) throw new Error(`Failed to load data (${response.status})`);
        return response.json();
      })
      .then((payload: SiteData) => {
        setData(payload);
        // Open on the agent whose packet was bounced -- the one that carries
        // the alternative finding -- rather than on the first row.
        const bounced = payload.agents.find((agent) => agent.rework_hours > 0);
        setSelectedId((bounced ?? payload.agents[0])?.agent_id ?? null);
      })
      .catch((caught: Error) => setError(caught.message));
  }, []);

  const selected = data?.agents.find((agent) => agent.agent_id === selectedId) ?? null;

  return (
    <div className="min-h-screen bg-surface-sunken">
      <div
        role="note"
        className="border-b border-warn-line bg-warn-soft"
        style={{ boxShadow: 'inset 0 2px 0 0 var(--warn)' }}
      >
        <div className="mx-auto max-w-[76rem] px-5 py-2.5">
          <p
            className="text-[0.8125rem] leading-relaxed"
            style={{ color: 'color-mix(in oklab, var(--warn) 78%, var(--ink))' }}
          >
            <span className="font-semibold">Illustrative demonstration only.</span>{' '}
            Every agent, carrier, licence, producer number, and duration here is{' '}
            <span className="font-semibold">fictional and generated</span>. Not
            affiliated with any insurance carrier. Nothing here is a licence,
            evidence of one, or advice.
          </p>
        </div>
      </div>

      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[76rem] items-center justify-between gap-4 px-5 py-3">
          <div className="flex min-w-0 items-center gap-2.5">
            <Mark />
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold tracking-tight text-ink">
                Onboarding Copilot
              </p>
              <p className="truncate text-xs text-ink-subtle">
                Where the days go, and which of them a model can remove
              </p>
            </div>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-[76rem] px-5 pb-20 pt-8">
        {error && <div className="note note-danger">{error}</div>}

        {!data && !error && (
          <div className="card h-64 animate-pulse" aria-live="polite" />
        )}

        {data && (
          <>
            <div className="mb-7 max-w-3xl">
              <h1 className="text-display font-semibold text-ink">
                Onboarding does not take days because reading is slow.
              </h1>
              <p className="mt-3 text-lead text-ink-muted">
                The brief asked what it would take to turn days into hours.
                This is the measurement that answers it, built before the obvious
                model. The arithmetic is cheap. The build is not.
              </p>
            </div>

            <CycleTimePanel data={data} />

            <div className="mt-4 grid gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
              <section className="card h-fit overflow-hidden">
                <div className="border-b border-line px-4 py-3.5">
                  <h2 className="text-sm font-semibold text-ink">
                    Cohort ({data.agents.length})
                  </h2>
                  <p className="mt-0.5 text-xs text-ink-subtle">
                    Coloured by who is holding the work
                  </p>
                </div>
                <ul>
                  {data.agents.map((agent) => (
                    <AgentRow
                      key={agent.agent_id}
                      agent={agent}
                      selected={agent.agent_id === selectedId}
                      onSelect={() => setSelectedId(agent.agent_id)}
                    />
                  ))}
                </ul>
              </section>

              {selected && <AgentDetail agent={selected} />}
            </div>

            {data.extraction && (
              <section className="card mt-4 overflow-hidden">
                <div className="border-b border-line px-5 py-4">
                  <h2 className="text-sm font-semibold text-ink">
                    The extractor, built anyway
                  </h2>
                  <p className="mt-1 max-w-prose text-xs leading-relaxed text-ink-subtle">
                    A kill is more credible when you built the thing.
                    Extraction answers a different question: not does it save
                    time, but can it be trusted to auto-populate a carrier
                    submission. That turns on <em>how</em> it fails, not how
                    often. A null gets reviewed by a person. A confident wrong
                    value posts to a carrier.
                  </p>
                </div>
                <dl className="flex flex-wrap">
                  {[
                    ['Field accuracy', `${data.extraction.accuracy_pct}%`],
                    ['Confident wrong', `${data.extraction.wrong_pct}%`],
                    [
                      'On danger fields',
                      `${data.extraction.danger_confident_wrong_pct}%`,
                    ],
                    ['Documents', `${data.extraction.documents}`],
                    ['Cost', `$${data.extraction.cost_usd.toFixed(2)}`],
                  ].map(([label, value]) => (
                    <div
                      key={label}
                      className="grow basis-[9rem] border-b border-r border-line px-5 py-3 last:border-r-0"
                    >
                      <dt className="gauge-label">
                        {label}
                      </dt>
                      <dd className="tabular mt-1 text-sm font-semibold text-ink">
                        {value}
                      </dd>
                    </div>
                  ))}
                </dl>
                <p className="px-5 py-3.5 text-xs leading-relaxed text-ink-subtle">
                  <span className="font-semibold text-ink-muted">
                    This is a ceiling, not a forecast.
                  </span>{' '}
                  Clean vector PDFs generated by this repository. The number
                  measures transcription logic under planted hazards: a
                  leading-zero NPN under a watermark, a DD-MMM-YYYY date, states
                  printed in full. Not robustness to a photocopy shot on a phone.
                  Model {data.extraction.model}.
                </p>
              </section>
            )}

            <footer className="mt-14 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-t border-line pt-5 text-xs text-ink-faint">
              <p>
                Gap engine {data.engine_version} · deterministic, no model ·
                computed once by tools/build_site_data.py
              </p>
              <p>
                <a
                  className="underline underline-offset-2 hover:text-ink-subtle"
                  href="https://scottdelia.github.io/innovation-office/"
                >
                  Part of an applied-AI portfolio
                </a>
              </p>
            </footer>
          </>
        )}
      </main>
    </div>
  );
}
