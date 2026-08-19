import type { CSSProperties } from 'react';
import type { SiteData } from '../types';

/**
 * The finding, as the first thing on the page.
 *
 * Everything else in this application exists to be checked against this panel.
 * The decomposition is a single stacked bar rather than five numbers in a
 * table, because the point is not any individual figure -- it is the ratio
 * between them, and a bar shows a 93.9%-to-0.3% relationship in a way a column
 * of percentages does not.
 *
 * The kill criterion is stated with its threshold and its outcome together. A
 * result shown without the threshold it was judged against invites the reader
 * to supply their own, which is the whole failure that registering one in
 * advance was meant to prevent.
 */

const SEGMENTS = [
  {
    key: 'external_wait',
    label: 'External queues',
    sub: 'carrier · state · vendor',
    tier: 'var(--tier-decline)',
    external: true,
  },
  {
    key: 'internal_queue',
    label: 'Our backlog',
    sub: 'work waiting on us',
    tier: 'var(--tier-table-rated)',
    external: false,
  },
  {
    key: 'rework',
    label: 'Rework',
    sub: 'defect caught by a carrier',
    tier: 'var(--tier-standard)',
    external: false,
  },
  {
    key: 'internal_idle',
    label: 'Idle',
    sub: 'actionable, untouched',
    tier: 'var(--tier-standard-plus)',
    external: false,
  },
  {
    key: 'internal_touch',
    label: 'Someone working',
    sub: 'the only part extraction touches',
    tier: 'var(--tier-preferred-plus)',
    external: false,
  },
] as const;

const LEVER_LABEL: Record<string, string> = {
  extraction: 'Extraction — a model reads the documents',
  rule_engine: 'Rule engine — catch defects before submission',
  nudge: 'Nudge queue — chase idle work',
  all_three: 'All three together',
};

export function CycleTimePanel({ data }: { data: SiteData }) {
  const { baseline, decomposition, levers } = data.cycle_time;
  const extraction = levers.extraction.percent_removed;
  const fires = extraction < data.kill_threshold_pct;

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-line px-5 py-4">
        <h2 className="text-sm font-semibold text-ink">
          Where a {baseline.mean_days}-day onboarding actually goes
        </h2>
        <p className="mt-1 text-xs text-ink-subtle">
          Mean across {data.cycle_time.cohort_size} agents, along the critical
          path — steps that ran concurrently are counted once, not twice.
        </p>
      </div>

      {/* The bar. Widths come straight from the computed shares, so it cannot
          disagree with the table beneath it. */}
      <div className="px-5 pt-5">
        <div className="flex h-9 w-full overflow-hidden rounded-lg">
          {SEGMENTS.map((segment) => {
            const share = decomposition[`${segment.key}_share_pct`] ?? 0;
            if (share <= 0) return null;
            return (
              <div
                key={segment.key}
                title={`${segment.label} — ${share}%`}
                style={
                  {
                    width: `${share}%`,
                    background: `color-mix(in oklab, ${segment.tier} 72%, transparent)`,
                  } as CSSProperties
                }
              />
            );
          })}
        </div>

        <dl className="mt-4 grid gap-x-6 gap-y-2.5 sm:grid-cols-2 lg:grid-cols-3">
          {SEGMENTS.map((segment) => {
            const share = decomposition[`${segment.key}_share_pct`] ?? 0;
            const hours = decomposition[`${segment.key}_hours`] ?? 0;
            const style = { '--tier': segment.tier } as CSSProperties;
            return (
              <div key={segment.key} className="flex items-baseline gap-2.5">
                <span className="tier-dot mt-1.5" style={style} />
                <div className="min-w-0 flex-1">
                  <dt className="flex items-baseline justify-between gap-2 text-sm text-ink-muted">
                    <span className="truncate">{segment.label}</span>
                    <span className="tabular shrink-0 font-semibold text-ink">
                      {share}%
                    </span>
                  </dt>
                  <dd className="text-xs text-ink-faint">
                    {segment.sub} ·{' '}
                    <span className="tabular">{hours.toFixed(1)}h</span>
                  </dd>
                </div>
              </div>
            );
          })}
        </dl>
      </div>

      {/* The levers, each modelled on its own. Extraction first, because it is
          the one the brief implies and the one the numbers refuse. */}
      <div className="mt-5 border-t border-line">
        <p className="px-5 pt-4 text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-faint">
          What each lever removes from the total
        </p>
        <ul className="px-5 pb-4 pt-2">
          {Object.entries(levers).map(([name, lever]) => {
            const isExtraction = name === 'extraction';
            return (
              <li
                key={name}
                className="flex flex-wrap items-baseline gap-x-3 gap-y-1 border-b border-line py-2.5 last:border-b-0"
              >
                <span className="min-w-0 flex-1 text-sm text-ink-muted">
                  {LEVER_LABEL[name] ?? name}
                </span>
                <span className="tabular text-xs text-ink-faint">
                  −{lever.hours_removed.toFixed(1)}h
                </span>
                <span
                  className={`tabular w-14 text-right text-sm font-semibold ${
                    isExtraction ? 'text-warn' : 'text-ink'
                  }`}
                >
                  {lever.percent_removed}%
                </span>
              </li>
            );
          })}
        </ul>
      </div>

      {/* The criterion and its outcome, together. */}
      <div
        className="tier-rail border-t border-line bg-surface-inset px-5 py-4"
        style={{ '--tier': 'var(--tier-table-rated)' } as CSSProperties}
      >
        <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-faint">
          Kill criterion, registered before the build
        </p>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
          Extraction had to remove at least{' '}
          <span className="tabular font-semibold text-ink">
            {data.kill_threshold_pct}%
          </span>{' '}
          of elapsed time. It removes{' '}
          <span className="tabular font-semibold text-warn">{extraction}%</span>.{' '}
          {fires ? (
            <>
              <span className="font-semibold text-ink">The criterion fires.</span>{' '}
              &ldquo;A model reads the documents and onboarding takes hours&rdquo;
              is not available at any level of extraction accuracy — because
              someone actively working is{' '}
              <span className="tabular font-semibold text-ink">
                {decomposition.internal_touch_share_pct}%
              </span>{' '}
              of the total.
            </>
          ) : (
            <span className="font-semibold text-ink">The criterion holds.</span>
          )}
        </p>
      </div>

      {/* A conclusion that only survives one set of assumptions is not a
          conclusion, so the assumptions are pushed in the direction that would
          most favour extraction and the result is shown either way. */}
      <div className="border-t border-line px-5 py-4">
        <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-faint">
          Does it hold if the assumptions are wrong?
        </p>
        <div className="mt-2.5 overflow-x-auto">
          <table className="w-full min-w-[30rem] text-sm">
            <thead>
              <tr className="text-left text-xs text-ink-faint">
                <th className="pb-1.5 font-medium">Scenario</th>
                <th className="pb-1.5 text-right font-medium">External</th>
                <th className="pb-1.5 text-right font-medium">Extraction</th>
                <th className="pb-1.5 text-right font-medium">Rule engine</th>
              </tr>
            </thead>
            <tbody>
              {data.sensitivity.map((row) => (
                <tr key={row.scenario} className="border-t border-line">
                  <td className="py-2 text-ink-muted">{row.scenario}</td>
                  <td className="tabular py-2 text-right text-ink-muted">
                    {row.external_wait_share_pct}%
                  </td>
                  <td className="tabular py-2 text-right font-semibold text-warn">
                    {row.extraction_pct}%
                  </td>
                  <td className="tabular py-2 text-right font-semibold text-ink">
                    {row.rule_engine_pct}%
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2.5 text-xs leading-relaxed text-ink-subtle">
          Extraction never overtakes the rule engine, at any assumption I can
          defend. The step durations are plausible rather than observed, and are
          the first thing worth pushing on — which is why the conclusion is
          shown surviving them being wrong.
        </p>
      </div>
    </section>
  );
}
