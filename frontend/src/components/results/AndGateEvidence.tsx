/**
 * The measurements behind a two-input AND candidate's ON and OFF.
 *
 * ON is the joint opening of both hairpin stems with both triggers present; OFF is the largest
 * joint opening in any state that should stay shut. Every sampled state carries its sampler
 * check against the exact base-pair probabilities, and a failed check is shown as failed, not
 * hidden: the value stays and so does its failed check. A value that could not be measured reads
 * "unmeasured", never 0. Nothing here is a sequence, so it is shown even while sequences are held.
 */

import type { AndGateDiagnostics } from "@/api/types";

const STATE_LABEL: Record<string, string> = {
  alone: "Alone (no trigger)",
  "+A": "Trigger A only",
  "+B": "Trigger B only",
  "+A+B": "Both triggers (ON)",
};

function pct(value: number | null | undefined, digits = 2) {
  return value === null || value === undefined ? "unmeasured" : `${value.toFixed(digits)}%`;
}

function tie(value: boolean | null | undefined) {
  if (value === null || value === undefined) return "not determined";
  return value ? "yes, indistinguishable from the best within the seed noise" : "no";
}

export function AndGateEvidence({ info }: { info: AndGateDiagnostics }) {
  const states = Object.entries(info.states ?? {});
  const failed = states.filter(([, state]) => state.verified === false).map(([name]) => name);
  return (
    <section
      aria-label="Two-input AND gate evidence"
      data-testid="and-gate-evidence"
      className="mt-6 rounded-xl border border-border bg-card p-4"
    >
      <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        Two-input AND evidence
      </div>
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-4">
        <div>
          <dt className="text-xs text-muted-foreground">ON (both triggers)</dt>
          <dd className="font-semibold">{pct(info.on_pct)}</dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">OFF (worst shut state)</dt>
          <dd className="font-semibold">
            {pct(info.off_pct)}
            {info.off_source ? <span className="ml-1 text-xs font-normal">({info.off_source})</span> : null}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">ON − OFF</dt>
          <dd className="font-semibold">
            {info.on_minus_off_pp === null || info.on_minus_off_pp === undefined
              ? "unmeasured"
              : `${info.on_minus_off_pp.toFixed(2)} points`}
          </dd>
        </div>
        <div>
          <dt className="text-xs text-muted-foreground">ΔG of the two-trigger complex</dt>
          <dd className="font-semibold">
            {info.delta_g_kcal_per_mol === null || info.delta_g_kcal_per_mol === undefined
              ? "unmeasured"
              : `${info.delta_g_kcal_per_mol.toFixed(1)} kcal/mol`}
          </dd>
        </div>
      </dl>
      <p className="mt-3 text-xs">
        Tied with the best candidate: <strong>{tie(info.tied_group)}</strong>.
      </p>

      <table className="mt-3 w-full text-left text-xs">
        <caption className="sr-only">
          Joint stem opening and sampler check for each folded state
        </caption>
        <thead>
          <tr className="text-muted-foreground">
            <th scope="col" className="py-1 pr-3 font-medium">State</th>
            <th scope="col" className="py-1 pr-3 font-medium">Joint opening</th>
            <th scope="col" className="py-1 pr-3 font-medium">Draws</th>
            <th scope="col" className="py-1 font-medium">Sampler check</th>
          </tr>
        </thead>
        <tbody>
          {states.map(([name, state]) => (
            <tr key={name} className="border-t border-border">
              <th scope="row" className="py-1 pr-3 font-normal">{STATE_LABEL[name] ?? name}</th>
              <td className="py-1 pr-3">{pct(state.open_pct)}</td>
              <td className="py-1 pr-3">{state.draws ?? "unavailable"}</td>
              <td className={`py-1 ${state.verified === false ? "font-semibold text-destructive" : ""}`}>
                {state.verified === true ? "passed" : state.verified === false ? "FAILED" : "unavailable"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className="mt-3 text-xs text-muted-foreground">
        Mismatched-trigger controls: {info.controls?.found ?? "unavailable"} of{" "}
        {info.controls?.requested ?? "unavailable"} ({info.controls?.mode ?? "unavailable"}); highest{" "}
        {pct(info.controls?.max_open_pct)}.
        {info.noise
          ? ` Seed-to-seed change of ON − OFF: ${
              info.noise.seed_to_seed_change_pp === null || info.noise.seed_to_seed_change_pp === undefined
                ? "unmeasured"
                : `${info.noise.seed_to_seed_change_pp.toFixed(2)} points`
            }.`
          : " The seed-noise check was not run."}
      </p>
      {failed.length > 0 && (
        <p role="alert" className="mt-2 text-xs text-destructive">
          The sampler check failed for {failed.join(", ")}: the value is kept but may be unreliable.
        </p>
      )}
      <p className="mt-2 text-[11px] text-muted-foreground">
        Joint opening is the share of each hairpin&rsquo;s own stem that is open at the same time in sampled
        equilibrium structures: a structural proxy for translation, not a measurement. No AND construct has
        been experimentally validated.
      </p>
    </section>
  );
}
