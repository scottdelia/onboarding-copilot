import type { CSSProperties } from 'react';
import {
  OWNER_IS_EXTERNAL,
  OWNER_LABEL,
  OWNER_TIER,
  type Agent,
  type Gap,
  type Step,
} from '../types';

/**
 * One agent's pipeline and its gaps.
 *
 * THE COLOUR IS THE ARGUMENT
 * --------------------------
 * Steps are coloured by owner, not by status. Running an eye down the rail
 * shows how much of an onboarding belongs to a carrier, a state, or a vendor,
 * and how little of it is ours — which is the finding the whole application
 * exists to make, restated at the level of a single person.
 *
 * Steps off the critical path are dimmed. They finished while something slower
 * was running, so making them instant would not move the date this agent can
 * write business. That distinction is invisible in a status list and is most of
 * what separates a real cycle-time view from a progress bar.
 */

function StatusDot({ step }: { step: Step }) {
  const tone =
    step.status === 'complete'
      ? 'var(--tier-preferred-plus)'
      : step.status === 'blocked'
        ? 'var(--tier-decline)'
        : step.status === 'not_started'
          ? 'var(--ink-faint)'
          : 'var(--tier-table-rated)';
  return (
    <span
      aria-hidden
      className="mt-1.5 size-2 shrink-0 rounded-full"
      style={{ background: tone }}
    />
  );
}

function GapRow({ gap }: { gap: Gap }) {
  return (
    <li
      className="tier-rail rounded-r-lg bg-surface-inset py-3 pl-4 pr-4"
      style={{ '--tier': 'var(--tier-decline)' } as CSSProperties}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <p className="text-sm font-medium text-ink">{gap.summary}</p>
        <span className="flex items-center gap-2">
          {gap.carrier_name && (
            <span className="text-xs text-ink-subtle">{gap.carrier_name}</span>
          )}
          {/* The provenance tag is the point of the component. This is a set
              comparison in plain code, and saying so beside the finding is what
              separates it from a model's opinion. */}
          <span className="rounded bg-surface px-1.5 py-0.5 font-mono text-[0.6875rem] text-ink-faint">
            rule engine · no model
          </span>
        </span>
      </div>
      <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
        <div className="flex gap-2">
          <dt className="text-ink-faint">Expected</dt>
          <dd className="text-ink-muted">{gap.expected}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-ink-faint">Observed</dt>
          <dd className="text-ink-muted">{gap.observed}</dd>
        </div>
      </dl>
      <p className="mt-1.5 text-xs text-ink-faint">
        Owned by {OWNER_LABEL[gap.owner as keyof typeof OWNER_LABEL] ?? gap.owner}
      </p>
    </li>
  );
}

export function AgentDetail({ agent }: { agent: Agent }) {
  const blocking = agent.gaps.filter((gap) => gap.severity === 'blocking');

  return (
    <section className="card overflow-hidden">
      <div className="border-b border-line px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="text-lg font-semibold tracking-tight text-ink">
            {agent.display_name}
          </h2>
          <p className="tabular text-sm text-ink-subtle">
            {agent.days_elapsed} days elapsed
            {agent.rework_hours > 0 && (
              <span className="text-warn">
                {' '}
                · {(agent.rework_hours / 24).toFixed(0)}d lost to rework
              </span>
            )}
          </p>
        </div>
        <p className="mt-1 text-xs text-ink-faint">
          NPN {agent.npn} · {agent.resident_state} ·{' '}
          {agent.target_carriers.length} target carriers
        </p>
        <p className="mt-2 max-w-prose text-xs leading-relaxed text-ink-subtle">
          {agent.demonstrates}
        </p>
      </div>

      {blocking.length > 0 && (
        <div className="border-b border-line px-5 py-4">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-faint">
            {blocking.length} blocking{' '}
            {blocking.length === 1 ? 'gap' : 'gaps'}, found before submission
          </p>
          <ul className="mt-2.5 space-y-2.5">
            {blocking.map((gap) => (
              <GapRow key={gap.key} gap={gap} />
            ))}
          </ul>
        </div>
      )}

      <div className="px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <p className="text-[0.6875rem] font-semibold uppercase tracking-[0.06em] text-ink-faint">
            Pipeline
          </p>
          <p className="text-xs text-ink-faint">
            Coloured by owner · dimmed steps are off the critical path
          </p>
        </div>

        <ol className="mt-3">
          {agent.steps.map((step) => {
            const style = { '--tier': OWNER_TIER[step.owner] } as CSSProperties;
            const external = OWNER_IS_EXTERNAL[step.owner];
            return (
              <li
                key={step.step_id}
                className={`tier-rail flex gap-3 border-b border-line py-3 pl-4 last:border-b-0 ${
                  step.on_critical_path ? '' : 'opacity-45'
                }`}
                style={style}
              >
                <StatusDot step={step} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                    <p className="text-sm text-ink">{step.name}</p>
                    <span className="tier-chip" style={style}>
                      {OWNER_LABEL[step.owner]}
                      {external && ' · not ours'}
                    </span>
                  </div>
                  <p className="tabular mt-1 text-xs text-ink-faint">
                    {step.touch_minutes}m work
                    {step.wait_hours > 0 && ` · ${step.wait_hours}h queue`}
                    {step.idle_hours > 0 && (
                      <span className="text-warn"> · {step.idle_hours}h idle</span>
                    )}
                    {step.on_critical_path && ' · on critical path'}
                  </p>
                  {step.blocker_detail && (
                    <p className="mt-1.5 text-xs leading-relaxed text-ink-subtle">
                      {step.blocker_detail}
                    </p>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
