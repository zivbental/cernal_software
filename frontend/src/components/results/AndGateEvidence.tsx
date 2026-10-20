/**
 * The measurements behind a two-input AND candidate's ON and OFF.
 *
 * Bacterial whole-window equilibrium opening and eukaryotic joint-stem sampling have distinct
 * displays. Missing values read "unmeasured", and failed checks remain visible. These numeric
 * diagnostics contain no sequence, so they remain readable while sequences are held.
 */

import type { AndGateDiagnostics, ProkaryoticAndDiagnostics } from "@/api/types";

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

function BacterialEquilibriumEvidence({ info }: { info: ProkaryoticAndDiagnostics }) {
  const switchOnly = info.evaluation_context === "switch_through_linker_excluding_output";
  const fullContext = info.full_context_status === "evaluated";
  const screening = info.screening;
  const contextStatus = fullContext ? "completed; see full-context feasibility below"
    : info.full_context_status === "screen_failed" ? "not run because the initial screen failed; no final rank"
      : info.full_context_status === "not_evaluated_budget" ? "not run within the finalist budget; no final rank"
        : "not recorded";
  const labels: Record<string, string> = {
    "00": "No triggers",
    "10": "Trigger A only",
    "01": "Trigger B only",
    "11": "Both triggers (ON)",
  };
  return (
    <section aria-label="Bacterial AND equilibrium evidence" data-testid="and-gate-evidence"
      className="mt-6 rounded-xl border border-border bg-card p-4">
      <div className="font-mono text-[11px] uppercase tracking-wider text-muted-foreground">
        Bacterial AND · equilibrium folding
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        {info.definition ?? "Joint equilibrium probability that the entire declared initiation window is unpaired."}
        {" "}This is a structural model, not measured translation or a kinetic rate.
      </p>
      {switchOnly ? <p className="mt-2 text-xs text-muted-foreground">
        Folding context: complete switch through its linker, excluding the output CDS
        {info.evaluated_nt != null ? ` (${info.evaluated_nt} nt total)` : ""}.
        {" "}Candidates must pass the declared feasibility and construct checks before ranking.
        Exported constructs include the complete output. Distal output interactions are outside this model.
      </p> : <><p className="mt-2 text-xs text-muted-foreground">
        Displayed folding context: {fullContext ? "complete switch plus full output CDS"
          : `initial screen with switch plus ${info.payload_head_nt ?? "unrecorded"} nt of payload tail`}
        {info.evaluated_nt != null ? ` (${info.evaluated_nt} nt total)` : ""}.
        {" "}Only candidates passing the full switch-plus-CDS evaluation and remaining checks receive
        a final rank. Promoter and terminator interactions are outside both folding stages.
      </p>
      <p className="mt-2 text-xs font-medium">
        Full switch-plus-CDS equilibrium check: {contextStatus}.
      </p></>}
      <dl className="mt-3 grid gap-3 text-sm sm:grid-cols-3">
        <div><dt className="text-xs text-muted-foreground">ON (both triggers)</dt>
          <dd className="font-semibold">{pct(info.on_pct)}</dd></div>
        <div><dt className="text-xs text-muted-foreground">Worst OFF</dt>
          <dd className="font-semibold">{pct(info.off_pct)}{info.worst_off_state ? ` (${info.worst_off_state})` : ""}</dd></div>
        <div><dt className="text-xs text-muted-foreground">ON − OFF</dt>
          <dd className="font-semibold">{info.on_minus_off_pp == null
            ? "unmeasured" : `${info.on_minus_off_pp.toFixed(2)} points`}</dd></div>
      </dl>
      <table className="mt-3 w-full text-left text-xs">
        <caption className="sr-only">Whole initiation-window opening in each equilibrium state</caption>
        <thead><tr className="text-muted-foreground">
          <th scope="col" className="py-1 pr-3 font-medium">State</th>
          <th scope="col" className="py-1 pr-3 font-medium">Window open</th>
          <th scope="col" className="py-1 font-medium">Opening cost</th>
        </tr></thead>
        <tbody>{Object.entries(info.states ?? {}).map(([name, state]) => (
          <tr key={name} className="border-t border-border">
            <th scope="row" className="py-1 pr-3 font-normal">{name} · {labels[name] ?? name}</th>
            <td className="py-1 pr-3">{pct(state.open_probability == null ? null : 100 * state.open_probability)}</td>
            <td className="py-1">{state.opening_energy_kcal_per_mol == null
              ? "unmeasured" : `${state.opening_energy_kcal_per_mol.toFixed(2)} kcal/mol`}</td>
          </tr>
        ))}</tbody>
      </table>
      <p className="mt-3 text-xs">
        {fullContext ? "Full-context" : info.full_context_status ? "Screen" : "Equilibrium"} feasibility: <strong>{info.feasibility == null ? "unavailable"
          : info.feasibility.passed === info.feasibility.total ? "passed" : "failed"}</strong>
        {info.feasibility != null ? ` (${info.feasibility.passed}/${info.feasibility.total} declared checks)` : ""}.
      </p>
      {!!info.feasibility?.violations?.length && (
        <ul className="mt-2 list-disc pl-5 text-xs text-destructive">
          {info.feasibility.violations.map((reason) => <li key={reason}>{reason}</li>)}
        </ul>
      )}
      {fullContext && screening && (
        <details className="mt-3 text-xs">
          <summary className="cursor-pointer font-medium">Compare initial screen with full CDS</summary>
          <table className="mt-2 w-full text-left">
            <caption className="sr-only">Initial screening compared with full-CDS equilibrium check</caption>
            <thead><tr className="text-muted-foreground">
              <th scope="col" className="py-1 pr-3 font-medium">Context</th>
              <th scope="col" className="py-1 pr-3 font-medium">ON</th>
              <th scope="col" className="py-1 pr-3 font-medium">Worst OFF</th>
              <th scope="col" className="py-1 font-medium">Passed checks</th>
            </tr></thead>
            <tbody>{[
              { label: "Initial payload-prefix screen", measurement: screening },
              { label: "Full output CDS", measurement: info },
            ].map(({ label, measurement }) => (
              <tr key={label} className="border-t border-border">
                <th scope="row" className="py-1 pr-3 font-normal">{label}</th>
                <td className="py-1 pr-3">{pct(measurement.on_pct)}</td>
                <td className="py-1 pr-3">{pct(measurement.off_pct)}</td>
                <td className="py-1">{measurement.feasibility
                  ? `${measurement.feasibility.passed}/${measurement.feasibility.total}` : "unavailable"}</td>
              </tr>
            ))}</tbody>
          </table>
        </details>
      )}
      {info.ranking && <p className="mt-2 text-xs text-muted-foreground">{info.ranking}</p>}
      {!!info.warnings?.length && <p className="mt-2 text-xs text-muted-foreground">{info.warnings.join(" ")}</p>}
    </section>
  );
}

export function AndGateEvidence({ info }: { info: AndGateDiagnostics | ProkaryoticAndDiagnostics }) {
  if (info.method === "prokaryotic_equilibrium") return <BacterialEquilibriumEvidence info={info} />;
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
