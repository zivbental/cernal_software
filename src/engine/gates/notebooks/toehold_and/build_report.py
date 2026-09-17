# ruff: noqa: E501 -- this module is an HTML template. Its long lines are markup
# and table rows, and hand-wrapping them to 100 columns would break the rows
# apart without making anything easier to read.
"""Assemble the architecture decision report, inlining the eight structure figures.

    uv run python src/engine/gates/notebooks/toehold_and/build_report.py

Reads ``results/report_x448_{baseline,aug_paired}_state{00,01,10,11}.svg``, produced by
``four_state_figures.py --x-start 448 --stem strongest --variant <v> --out report``, and
writes ``results/report.html``. Every number in the prose is copied from a committed CSV --
``modifications.csv`` for the variant table, ``green_calibration.csv`` for the correlations --
so a figure that moves is a signal that the report needs regenerating, not that it drifted.
"""

import pathlib

HERE = pathlib.Path(__file__).resolve().parent / "results"
STATES = ("00", "01", "10", "11")
STATE_NOTE = {
    "00": "neither trigger",
    "01": "trigger B only",
    "10": "trigger A only &mdash; must stay OFF",
    "11": "both &mdash; the only ON state",
}


def figure_panels(variant: str) -> str:
    out = []
    for state in STATES:
        svg = (HERE / f"report_x448_{variant}_state{state}.svg").read_text(encoding="utf-8")
        out.append(
            f'<figure class="plot"><figcaption><b>{state}</b> &middot; {STATE_NOTE[state]}'
            f'</figcaption><div class="canvas">{svg}</div></figure>'
        )
    return "\n".join(out)


HEAD = """<title>A0 Architecture Review</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Spectral:ital,wght@0,400;0,600;1,400&family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>
:root{
  --ground:#F4F2EC; --raise:#FBFAF6; --ink:#16150F; --soft:#55524A; --faint:#7C7970;
  --rule:#DFDBCD; --accent:#4A42A8; --accent-soft:#E4E1F4;
  --good:#2F6B12; --good-soft:#E0EBD2; --warn:#8A5A00; --warn-soft:#F6E9CE;
  --bad:#9E2B2B; --bad-soft:#F4DBDB;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,sans-serif;
  --serif:"Spectral",Georgia,"Times New Roman",serif;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --ground:#14130E; --raise:#1C1B14; --ink:#F1EFE8; --soft:#B7B3A8; --faint:#8B877C;
  --rule:#302D24; --accent:#A9A2F0; --accent-soft:#252248;
  --good:#9BCB74; --good-soft:#1E2A14; --warn:#E0B060; --warn-soft:#2E2412;
  --bad:#E39292; --bad-soft:#331919;
}}
:root[data-theme="dark"]{
  --ground:#14130E; --raise:#1C1B14; --ink:#F1EFE8; --soft:#B7B3A8; --faint:#8B877C;
  --rule:#302D24; --accent:#A9A2F0; --accent-soft:#252248;
  --good:#9BCB74; --good-soft:#1E2A14; --warn:#E0B060; --warn-soft:#2E2412;
  --bad:#E39292; --bad-soft:#331919;
}
*{box-sizing:border-box}
body{margin:0;background:var(--ground);color:var(--ink);font-family:var(--sans);
  font-size:16px;line-height:1.65;-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding-inline:20px;padding-block:44px 96px}
h1{font-family:var(--serif);font-size:clamp(30px,5vw,44px);line-height:1.12;margin:0 0 10px;
  font-weight:600;letter-spacing:-.015em;text-wrap:balance}
.dek{font-family:var(--serif);font-size:19px;font-style:italic;color:var(--soft);
  margin:0 0 28px;max-width:62ch}
.meta{font-family:var(--mono);font-size:12px;color:var(--faint);letter-spacing:.02em;
  border-top:1px solid var(--rule);border-bottom:1px solid var(--rule);
  padding-block:12px;margin-bottom:40px;display:flex;flex-wrap:wrap;gap:6px 22px}
h2{font-family:var(--serif);font-size:27px;font-weight:600;letter-spacing:-.01em;
  margin:56px 0 6px;text-wrap:balance}
h3{font-size:16px;font-weight:600;margin:30px 0 8px;letter-spacing:-.005em}
.eyebrow{font-family:var(--mono);font-size:11.5px;text-transform:uppercase;
  letter-spacing:.11em;color:var(--accent);margin:0 0 4px;font-weight:600}
p{margin:0 0 15px;max-width:68ch}
ul,ol{max-width:68ch;padding-left:20px;margin:0 0 15px}
li{margin-bottom:7px}
b,strong{font-weight:600}
code,.num{font-family:var(--mono);font-size:.9em;font-variant-numeric:tabular-nums}
a{color:var(--accent)}
.lede{border-left:3px solid var(--accent);padding:2px 0 2px 18px;margin:0 0 28px}
.lede p{font-size:17.5px}
.scroll{overflow-x:auto;margin:20px 0 26px;border:1px solid var(--rule);border-radius:3px;
  background:var(--raise)}
table{border-collapse:collapse;width:100%;font-size:13.5px;font-variant-numeric:tabular-nums}
th,td{padding:9px 13px;text-align:right;white-space:nowrap;border-bottom:1px solid var(--rule)}
th:first-child,td:first-child{text-align:left}
thead th{font-family:var(--mono);font-size:11px;text-transform:uppercase;letter-spacing:.07em;
  color:var(--faint);font-weight:600;background:var(--ground)}
tbody tr:last-child td{border-bottom:none}
tr.hi td{background:var(--good-soft)}
tr.lo td{background:var(--bad-soft)}
td.n{font-family:var(--mono)}
.verdict{display:inline-block;font-family:var(--mono);font-size:11px;font-weight:600;
  text-transform:uppercase;letter-spacing:.07em;padding:3px 9px;border-radius:2px;
  vertical-align:middle;margin-left:10px}
.v-adopt{background:var(--good-soft);color:var(--good)}
.v-test{background:var(--warn-soft);color:var(--warn)}
.v-no{background:var(--bad-soft);color:var(--bad)}
.split{display:grid;grid-template-columns:1fr 1fr;gap:0;border:1px solid var(--rule);
  border-radius:3px;overflow:hidden;margin:18px 0 22px}
.split>div{padding:16px 18px;background:var(--raise)}
.split>div+div{border-left:1px solid var(--rule)}
.split h4{margin:0 0 8px;font-size:12px;font-family:var(--mono);text-transform:uppercase;
  letter-spacing:.07em;font-weight:600}
.for h4{color:var(--good)} .against h4{color:var(--bad)}
.split ul{margin:0;padding-left:17px;font-size:14.5px}
@media(max-width:620px){.split{grid-template-columns:1fr}
  .split>div+div{border-left:none;border-top:1px solid var(--rule)}}
.callout{background:var(--accent-soft);border-radius:3px;padding:18px 20px;margin:24px 0;
  font-size:15px}
.callout p{margin:0;max-width:none}
.callout p+p{margin-top:10px}
figure.plot{margin:0 0 22px;border:1px solid var(--rule);border-radius:3px;
  background:var(--raise);overflow:hidden}
figure.plot figcaption{font-family:var(--mono);font-size:11.5px;letter-spacing:.05em;
  text-transform:uppercase;color:var(--soft);padding:9px 14px;border-bottom:1px solid var(--rule)}
figure.plot figcaption b{color:var(--ink)}
.canvas{overflow-x:auto}
.canvas svg{display:block;width:100%;height:auto}
body.zoom .canvas svg{width:auto;max-width:none;height:560px}
.controls{display:flex;flex-wrap:wrap;gap:8px;margin:18px 0 20px;align-items:center}
button{font-family:var(--mono);font-size:12px;letter-spacing:.04em;padding:7px 14px;
  border:1px solid var(--rule);background:var(--raise);color:var(--soft);border-radius:2px;
  cursor:pointer;font-weight:600}
button[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:#fff}
:root[data-theme="dark"] button[aria-pressed="true"],
  :root:not([data-theme="light"]) button[aria-pressed="true"]{color:#14130E}
button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.foot{margin-top:64px;padding-top:22px;border-top:1px solid var(--rule);
  font-size:13.5px;color:var(--faint)}
.foot code{font-size:12px}
@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
</style>"""


BODY = f"""
<div class="wrap">
<p class="eyebrow">A0 prokaryotic two-input AND gate &middot; decision memo</p>
<h1>Five architecture changes, measured</h1>
<p class="dek">Our gate does not gate at equilibrium. Here is what the literature does
differently, which of five proposed fixes actually works in our own numbers, and what we
should order.</p>
<div class="meta">
  <span>17 Sep 2026</span><span>ViennaRNA 2.7.2, 37&nbsp;&deg;C</span>
  <span>mCherry, 711&nbsp;nt</span><span>branch offer/fold-engine-p-open</span>
</div>

<div class="lede">
<p><b>Bottom line, and it changed late.</b> Our equilibrium model says every design we have
fails: <code>separation</code> is <span class="num">0.00</span> on all of them. A kinetic
reading of the same molecules says the opposite &mdash; the gate's designed mechanism is
present and large, worth between <span class="num">10&times;</span> and
<span class="num">9,470&times;</span> in trigger A's nucleation rate. The two disagree because
the model measures end states and the architecture is built on a <i>path</i>.</p>
<p>So the finding is not "here is the fix". It is <b>our ranking statistic was wrong, and the
architecture may not need fixing at all</b>. We have one modification that does raise
equilibrium separation &mdash; closing the AUG on a strong lock &mdash; and it buys nothing
kinetically while costing ON-state accessibility. It belongs in the panel as a
<i>contrast arm</i>, not as the answer.</p>
</div>

<h2>What is actually wrong</h2>
<p>The gate is supposed to need both triggers. At equilibrium, trigger A alone already does
the whole job: it occupies <span class="num">35.93</span> of its 36 nt on the switch in
state 10 and <span class="num">35.93</span> in state 11 &mdash; a difference of
<span class="num">0.004</span> nt. There is nothing left for trigger B to enable, so every
candidate returns <code>separation</code> <span class="num">0.00</span>.</p>

<p>Trigger B is not idle. It dismantles about 19 bp of the switch's own structure. But that
structure is the inhibitory hairpin, which lies outside the window the ribosome reads, and
the coupling between trigger B's binding energy and the opening cost of that window is
<b>exactly zero</b>: adding B lowers the constrained and the unconstrained ensembles by the
identical <span class="num">&minus;90.34&nbsp;kcal/mol</span>.</p>

<div class="scroll"><table>
<thead><tr><th>state</th><th>P_open (all 30 nt open at once)</th><th>dG_open</th>
<th>relative to 11</th></tr></thead>
<tbody>
<tr><td>00 &middot; neither</td><td class="n">6.23 &times; 10<sup>&minus;16</sup></td>
  <td class="n">21.58</td><td class="n">1.4 &times; 10<sup>&minus;10</sup></td></tr>
<tr><td>01 &middot; B only</td><td class="n">2.05 &times; 10<sup>&minus;15</sup></td>
  <td class="n">20.84</td><td class="n">4.6 &times; 10<sup>&minus;10</sup></td></tr>
<tr class="lo"><td>10 &middot; A only</td><td class="n">4.47 &times; 10<sup>&minus;6</sup></td>
  <td class="n">7.59</td><td class="n">1.0000</td></tr>
<tr class="lo"><td>11 &middot; both</td><td class="n">4.47 &times; 10<sup>&minus;6</sup></td>
  <td class="n">7.59</td><td class="n">1.0000</td></tr>
</tbody></table></div>
<p style="font-size:14px;color:var(--soft)">Candidate x@260. Note that
<code>P_open</code> is tiny in <i>every</i> tube, the ON state included &mdash; requiring 30
nucleotides to be unpaired simultaneously is a severe condition, so only the ratios carry
meaning, never the absolute values.</p>

<h2>First: can our own metric be trusted?</h2>
<p>Before comparing variants we checked whether the observable we rank on has any
relationship with real performance. Green 2014 Table&nbsp;S1 publishes
<b>168 toehold switches</b> with full sequences and a measured ON/OFF spanning 1 to 292. We
applied <i>our</i> observables to them unchanged &mdash; same window, same <code>p_open</code>,
same <code>A_M</code> &mdash; and took Spearman rank correlation.</p>

<div class="scroll"><table>
<thead><tr><th>our observable</th><th>&rho; vs measured ON/OFF</th><th>|z|</th>
<th>verdict</th></tr></thead>
<tbody>
<tr class="lo"><td><code>separation</code> &mdash; what we rank on</td><td class="n">&minus;0.107</td>
  <td class="n">1.38</td><td>not significant</td></tr>
<tr><td><code>separation</code> over a 9-nt window</td><td class="n">&minus;0.107</td>
  <td class="n">1.38</td><td>not significant</td></tr>
<tr><td><code>dG_open</code> OFF state</td><td class="n">&minus;0.362</td><td class="n">4.67</td>
  <td>significant, wrong sign</td></tr>
<tr class="hi"><td><code>A_M</code> gain, ON &minus; OFF</td><td class="n">+0.320</td>
  <td class="n">4.13</td><td>significant</td></tr>
<tr class="hi"><td>mean over the <i>same</i> W_rank, gain</td><td class="n">+0.317</td>
  <td class="n">4.09</td><td>significant</td></tr>
<tr><td>start codon accessibility, gain</td><td class="n">+0.241</td><td class="n">3.11</td>
  <td>significant</td></tr>
</tbody></table></div>

<div class="callout">
<p><b>The window is fine. The statistic is wrong.</b> Compare row 5 with row 1: identical
window, identical tubes, mean-unpaired instead of joint <code>p_open</code>, and the
correlation moves from &minus;0.11 to +0.32. Narrowing the joint window to 9 nt changes
nothing.</p>
<p>Requiring 30 &mdash; or 9 &mdash; nucleotides to be unpaired <i>simultaneously</i> is
dominated by the single most-paired base, and <code>P_open</code> runs 10<sup>&minus;6</sup>
to 10<sup>&minus;16</sup> for every real switch, so the dynamic range sits in a tail that is
mostly noise. Our <code>separation</code> would have <b>deselected</b> Green's best
switches: the ten that actually performed best (192&ndash;292) landed at our ranks 111, 151,
90, 121, 161, 96, 80, 164, 45 and 125 of 168.</p>
<p>This bears on the instruction to compute accessibility from the partition function rather
than as an average. On 168 bench-measured constructs, <b>the average predicts and the joint
partition-function form does not.</b> &rho;&nbsp;=&nbsp;0.32 is modest, but VISTA's strongest
single feature is r&nbsp;=&nbsp;0.30, so it is in line with the field.</p>
</div>

<h2>What the equilibrium model cannot see</h2>
<p>Kim attribute their working AND gate to <i>binding probability</i> and enforced
<i>sequential binding</i> &mdash; rate quantities. Our model reports end states. To find out
whether that gap matters here, ask what trigger A finds <b>on arrival</b>, which means reading
its foothold off the configuration the switch is in <i>before</i> A binds, not after.</p>

<ul>
<li><b>Path to state 10</b> &mdash; trigger A arrives at an untriggered switch. Its foothold is
<code>free(x*)</code> in tube <b>00</b>, where the inhibitory hairpin is shut.</li>
<li><b>Path to state 11</b> &mdash; trigger B binds first and opens that hairpin, so trigger A
arrives at configuration <b>01</b>.</li>
</ul>

<div class="scroll"><table>
<thead><tr><th>design</th><th>free(x*) in 00</th><th>free(x*) in 01</th>
<th>nucleation rate, 01 / 00</th><th>equilibrium separation</th></tr></thead>
<tbody>
<tr class="hi"><td>x@448 baseline</td><td class="n">0.0057</td><td class="n">0.5738</td>
  <td class="n"><b>9,470&times;</b></td><td class="n">0.00</td></tr>
<tr class="hi"><td>x@117 baseline</td><td class="n">0.0013</td><td class="n">0.3215</td>
  <td class="n"><b>160&times;</b></td><td class="n">0.00</td></tr>
<tr class="hi"><td>x@260 baseline</td><td class="n">0.0043</td><td class="n">0.2839</td>
  <td class="n"><b>160&times;</b></td><td class="n">&minus;0.00</td></tr>
<tr><td>x@522 baseline</td><td class="n">0.0017</td><td class="n">0.1412</td>
  <td class="n">10&times;</td><td class="n">0.00</td></tr>
</tbody></table></div>

<div class="callout">
<p><b>The designs our model rejects outright carry a 10&times; to 9,470&times; kinetic
advantage for the ON path.</b> Trigger B opening the inhibitory hairpin takes <code>x*</code>
from 0.4% free to 28&ndash;57% free. That is the designed mechanism, working, and an end-state
model cannot see it because given infinite time trigger A arrives anyway.</p>
<p>The ordering is corroborated rather than assumed: trigger B's own toehold <code>r2*</code>
is <b>31&ndash;53% free</b> in the OFF state, so B is the only trigger that can bind quickly,
and <code>free(x*|00)</code> agrees with <code>locked(00)</code>&nbsp;&asymp;&nbsp;0.99
measured independently from the pair-probability decomposition.</p>
<p><b>And the AUG closure adds nothing here.</b> Its footholds are identical to the
baseline's, because the closure changes the <i>main</i> hairpin while the foothold lives in
the <i>secondary</i> one. It buys equilibrium separation the bench may not need, at a cost in
<code>A_M(11)</code> the bench certainly will.</p>
</div>

<p><b>What this is not.</b> The slope (one decade per nucleotide) and the saturation (~6 nt)
are from Zhang &amp; Winfree 2009, measured on <b>DNA at 25&nbsp;&deg;C in 1 M Na<sup>+</sup></b>;
we fold <b>RNA at 37&nbsp;&deg;C</b>. The foothold itself is still an equilibrium quantity
&mdash; of the <i>starting</i> configuration, which is the right input to a rate model, but
not a simulation of one. This is an order-of-magnitude argument that the mechanism exists and
is invisible to our metric. It is not a predicted rate, and it is in no score anywhere.</p>

<h2>How we are answering this</h2>
<p>Five positions, adopted. They change what the model is <i>for</i> rather than softening a
threshold.</p>
<ol>
<li><b>Rank on the mean form.</b> It is the only statistic that calibrated
(&rho;&nbsp;=&nbsp;+0.32 against 168 measured switches, where the joint form gave
&minus;0.11). Joint probability and its energy conversion are <b>reported beside it, never
ranked on</b>.</li>
<li><b>Every &tau; threshold becomes report-only</b> until AND-gate bench data exists. A
threshold taken from an uncalibrated model is the fitting-to-the-metric trap, and it is the
specific risk that was flagged at the start of this project.</li>
<li><b>The kinetic ratio becomes a standing reported column.</b> It is the column that says
"the equilibrium model is the thing that is wrong about this design".</li>
<li><b>The baseline enters the panel as a first-class arm</b>, not a control. On this
evidence it may be the best arm we have.</li>
<li><b><code>aug_paired</code> stays as the contrast arm.</b> Together the two make the panel
<i>discriminate between the hypotheses</i> rather than assume one: if they perform the same
at the bench, the metric was the problem; if the closure wins, the leak was real.</li>
</ol>

<h2>How our architecture differs from theirs</h2>
<p>The single clearest difference: <b>every published design stops the trigger short of the
loop, and ours does not.</b></p>

<div class="scroll"><table>
<thead><tr><th>design</th><th>ascending arm</th><th>trigger covers</th><th>left free</th>
<th>measured ON/OFF</th></tr></thead>
<tbody>
<tr class="lo"><td><b>Ours (A0)</b></td><td class="n">18 nt</td><td class="n">18 &mdash; all</td>
  <td class="n">0</td><td>&mdash;</td></tr>
<tr><td>Green 2014, 1st generation</td><td class="n">18 nt</td><td class="n">18 &mdash; all</td>
  <td class="n">0</td><td class="n">43 mean</td></tr>
<tr class="hi"><td>Green 2014, forward-engineered</td><td class="n">18 nt</td><td class="n">15</td>
  <td class="n">3, weak <code>AUA</code></td><td class="n">406 mean</td></tr>
<tr><td>Kim 2019 (the AND gate)</td><td class="n">18 nt</td><td class="n">15</td>
  <td class="n">3, next to the loop</td><td>works at a&nbsp;=&nbsp;4</td></tr>
<tr><td>Green 2026 VISTA</td><td class="n">9+3&times;3+6</td><td class="n">6</td>
  <td>the whole top</td><td class="n">up to 137</td></tr>
</tbody></table></div>

<p>Green's first generation used <i>our</i> rule. Their forward-engineered generation pulled
the trigger back 3 nt &mdash; Fig.&nbsp;3A lists it as one of four deliberate changes,
annotated &ldquo;3 nt shift&rdquo; &mdash; and mean ON/OFF went from 43 to 406. <b>We adopted
the rule the field moved away from.</b> Other differences worth recording: Kim's start codon
sits in a <b>1&times;1 bulge</b>, not a 3&times;3 loop; his two hairpins are deliberately
<b>unequal</b> (19 bp inhibitory against 17 bp primary) where ours are equal by construction;
and both papers add a 26-nt stabilising hairpin we lack.</p>

<div class="callout">
<p><b>A caution about our ON-state observable.</b> VISTA's specified ON structure keeps the
6-bp upper stem <b>paired</b>, with the RBS still in its loop and only the start codon freed.
The architecture with the best published data never opens the whole window at all &mdash;
which is consistent with the calibration result above, and is a second reason to stop ranking
on joint <code>p_open</code>.</p>
</div>

<h2>The five changes, measured</h2>
<p>Each modification was built as an actual switch on the same base candidates, folded in all
four tubes, and reported with every observable. Six base candidates, 66 switches, medians
below. Nothing is filtered.</p>

<div class="scroll"><table>
<thead><tr><th>variant</th><th>separation</th><th>sep excl. 10</th><th>mean-form sep</th>
<th>A_M(11)</th><th>A_M(10)</th><th>AUG(11)</th></tr></thead>
<tbody>
<tr><td>baseline</td><td class="n">0.00</td><td class="n">13.50</td><td class="n">0.000</td>
  <td class="n">0.461</td><td class="n">0.461</td><td class="n">0.502</td></tr>
<tr><td>upper3 &mdash; Green's 3-nt shift</td><td class="n">0.02</td><td class="n">12.20</td>
  <td class="n">0.008</td><td class="n">0.490</td><td class="n">0.421</td><td class="n">0.408</td></tr>
<tr><td>upper6 &mdash; whole upper stem</td><td class="n">2.11</td><td class="n">11.77</td>
  <td class="n">0.088</td><td class="n">0.322</td><td class="n">0.118</td><td class="n">0.452</td></tr>
<tr class="hi"><td><b>aug_paired</b> &mdash; pair the start codon</td><td class="n">6.77</td>
  <td class="n">21.66</td><td class="n">0.189</td><td class="n">0.404</td><td class="n">0.007</td>
  <td class="n">0.444</td></tr>
<tr class="lo"><td>stop_before_bulge</td><td class="n">8.58</td><td class="n">15.80</td>
  <td class="n">0.043</td><td class="n">0.076</td><td class="n">0.001</td><td class="n">0.006</td></tr>
<tr><td>stabiliser &mdash; 5&prime; hairpin</td><td class="n">0.00</td><td class="n">13.50</td>
  <td class="n">0.000</td><td class="n">0.461</td><td class="n">0.461</td><td class="n">0.502</td></tr>
</tbody></table></div>

<p><code>stop_before_bulge</code> has the highest raw separation and is the trap in the table:
<code>A_M(11)</code> is <span class="num">0.076</span> and the start codon sits at
<span class="num">0.006</span>. It is shut in every state. It turns off without turning on.</p>

<h3>1 &middot; Upper 3 nt of the main stem <span class="verdict v-test">test, don't commit</span></h3>
<div class="split">
<div class="for"><h4>For</h4><ul>
<li>Green's own 43 &rarr; 406 improvement includes this change.</li>
<li>Kim's constructs independently obey the same 15-of-18 rule.</li>
<li>Costs nothing: the 3 bp stay closed, just not trigger-derived.</li>
</ul></div>
<div class="against"><h4>Against</h4><ul>
<li><b>In our architecture it does essentially nothing:</b> separation 0.02, mean-form 0.008.</li>
<li>Green changed four things at once; the 3-nt shift is not isolated in their data either.</li>
<li>Taking it to 6 nt (<code>upper6</code>) helps more on separation (2.11) and gives the
    best start-codon accessibility of any variant (0.825), but <b>still does not gate</b>:
    <code>A_M(10)</code> stays at 0.425, twice &tau;4a, and <code>A_M(11)&minus;A_M(10)</code>
    is 0.016. It moves the metrics without gating &mdash; a third category, distinct from
    both &ldquo;no effect&rdquo; and &ldquo;works&rdquo;.</li>
<li><b>Direction of travel, correctly attributed.</b> Green 2014's forward-engineered switches
    and Kim both stop at <b>3 nt</b>, which is <code>upper3</code>. But VISTA goes much
    further than <code>upper6</code>: its trigger invades only <b>6 bp of the stem in total</b>,
    leaving the inner lower stem, the whole bulge and the entire upper stem as invariant
    conserved sequence. So decoupling more than 3 nt is not unprecedented &mdash; it is the
    VISTA direction, and <code>stop_before_bulge</code> (9 of 18) is our closest approach to
    it, with VISTA further still.</li>
</ul></div>
</div>
<p>Our architecture differs from Green's in the one way that matters here: we have
<b>no exposed toehold</b> (a&nbsp;=&nbsp;0), so trigger A's advantage does not come from the
top of the stem. Shortening its reach there removes something it was not relying on.</p>

<h3>2 &middot; Pair the AUG bulge to the switch instead of to trigger A
<span class="verdict v-adopt">adopt</span></h3>
<div class="split">
<div class="for"><h4>For</h4><ul>
<li><b>The only change that lifts separation off zero</b> while keeping the gate switchable.</li>
<li>Median separation +6.77, best sep-excluding-10 (21.66), best mean-form (0.189).</li>
<li><code>A_M(10)</code> falls to 0.007 &mdash; &tau;4a passes for the first time.</li>
<li><code>A_M(11)</code> holds at 0.404 and the start codon stays accessible at 0.444.</li>
<li>Mechanistically motivated: it removes trigger A's built-in 3-bp advantage.</li>
</ul></div>
<div class="against"><h4>Against</h4><ul>
<li><b>Requires the strong secondary lock.</b> Alone it does nothing (see below).</li>
<li>Breaks R1 over 3 nt and removes the 3&times;3 loop R7 specifies.</li>
<li>Untested at the bench in this architecture; no published precedent for a&nbsp;=&nbsp;0.</li>
<li>On 3&times;3-class candidates it buries the start codon (AUG 0.115) &mdash; pair
    selection matters.</li>
</ul></div>
</div>

<p><b>The interaction is the finding.</b> Pairing the AUG does nothing on a lock-free stem,
and the lock alone does nothing. Both are required:</p>

<div class="scroll"><table>
<thead><tr><th>candidate</th><th>secondary stem</th><th>lock</th><th>baseline sep</th>
<th>aug_paired sep</th><th>A_M(10)</th><th>A_M(11)</th></tr></thead>
<tbody>
<tr><td>x@260</td><td>unlocked</td><td class="n">+2.4</td><td class="n">0.00</td>
  <td class="n">0.00</td><td class="n">0.384</td><td class="n">0.384</td></tr>
<tr class="hi"><td>x@260</td><td>strongest</td><td class="n">&minus;14.6</td><td class="n">0.00</td>
  <td class="n">5.91</td><td class="n">0.009</td><td class="n">0.384</td></tr>
<tr><td>x@117</td><td>unlocked</td><td class="n">+11.3</td><td class="n">0.00</td>
  <td class="n">0.00</td><td class="n">0.114</td><td class="n">0.114</td></tr>
<tr><td>x@117</td><td>strongest</td><td class="n">&minus;18.4</td><td class="n">0.00</td>
  <td class="n">12.00</td><td class="n">0.007</td><td class="n">0.111</td></tr>
<tr><td>x@448</td><td>unlocked</td><td class="n">+6.2</td><td class="n">0.00</td>
  <td class="n">0.00</td><td class="n">0.503</td><td class="n">0.503</td></tr>
<tr class="hi"><td>x@448</td><td>strongest</td><td class="n">&minus;20.5</td><td class="n">0.00</td>
  <td class="n">6.77</td><td class="n">0.004</td><td class="n">0.479</td></tr>
</tbody></table></div>
<p style="font-size:14px;color:var(--soft)">x@117 reaches the highest separation and is
still a bad design: <code>A_M(11)</code> 0.111 and start codon 0.002. Separation alone is not
a sufficient criterion &mdash; this is exactly why the panel reports every observable.</p>

<h3>3 &middot; AUG bulge geometry <span class="verdict v-adopt">select on it</span></h3>
<p><b>Only the ascending side is designable.</b> The descending side <i>is</i> the start
codon. So every bulge change is a change to <code>bulge*</code>, and <code>bulge*</code> is
<code>revcomp(trigger_A[6:9])</code> &mdash; trigger-derived. Today the loop is not a design
choice at all; it is an accident of which window we picked.</p>

<p><b>The loop cannot be asymmetric.</b> Both sides contribute exactly 3 nt, so if <i>k</i>
positions pair, <code>3&minus;k</code> are unpaired on <b>each</b> side. 1&times;2 and
0&times;2 cannot arise from this geometry, only from a register shift in the real fold. But
<b>which</b> positions pair does vary, and a 1&times;1 mid-helix is a different structure from
a 1&times;1 against the junction. Census over all 1036 surviving pairs:</p>

<div class="scroll"><table>
<thead><tr><th>pattern</th><th>loop</th><th>where it sits</th><th>pairs</th><th>share</th></tr></thead>
<tbody>
<tr><td class="n">o..</td><td class="n">2&times;2</td><td>at the arm base</td><td class="n">241</td><td class="n">23.3%</td></tr>
<tr><td class="n">.o.</td><td class="n">2&times;2</td><td>split</td><td class="n">229</td><td class="n">22.1%</td></tr>
<tr><td class="n">...</td><td class="n">3&times;3</td><td><b>what R7 specifies</b></td><td class="n">214</td><td class="n">20.7%</td></tr>
<tr><td class="n">oo.</td><td class="n">1&times;1</td><td>at the arm base</td><td class="n">183</td><td class="n">17.7%</td></tr>
<tr><td class="n">o.o</td><td class="n">1&times;1</td><td>mid-helix</td><td class="n">73</td><td class="n">7.0%</td></tr>
<tr><td class="n">ooo</td><td class="n">0&times;0</td><td>no loop at all</td><td class="n">38</td><td class="n">3.7%</td></tr>
<tr><td class="n">..o</td><td class="n">2&times;2</td><td>by the RBS loop</td><td class="n">34</td><td class="n">3.3%</td></tr>
<tr><td class="n">.oo</td><td class="n">1&times;1</td><td>by the RBS loop</td><td class="n">24</td><td class="n">2.3%</td></tr>
</tbody></table></div>
<p><b>R7 specifies a 3&times;3 loop and 79% of our candidates do not have one.</b> It was
never controlled, only assumed.</p>

<div class="callout">
<p><b>A correction to the first draft of this page.</b> It recommended selecting the
2&times;2 class, on four candidates per class. That used the wrong variable.
<code>aug_paired</code> sets <code>bulge*</code> to <code>CAU</code>, which <b>removes the
loop entirely</b> &mdash; the main stem becomes a continuous 18 bp helix &mdash; so after the
modification there is no 2&times;2 left to select. What survives the change, and what
predicts the outcome, is <b>how many of its three pairs trigger A keeps</b> once
<code>bulge*</code> is <code>CAU</code>.</p>
</div>

<div class="scroll"><table>
<thead><tr><th>trigger A keeps</th><th>pairs available</th><th>n folded</th><th>separation</th>
<th>A_M(10)</th><th>A_M(11)</th><th>AUG(11)</th></tr></thead>
<tbody>
<tr><td class="n">0 of 3</td><td class="n">327 &middot; 31.6%</td><td class="n">6</td>
  <td class="n">5.91</td><td class="n">0.009</td><td class="n">0.220</td><td class="n">0.229</td></tr>
<tr><td class="n">1 of 3</td><td class="n">437 &middot; 42.2%</td><td class="n">6</td>
  <td class="n">10.36</td><td class="n">0.007</td><td class="n">0.111</td><td class="n">0.002</td></tr>
<tr class="hi"><td class="n"><b>2 of 3</b></td><td class="n">238 &middot; 23.0%</td><td class="n">6</td>
  <td class="n">4.99</td><td class="n">0.006</td><td class="n">0.411</td><td class="n">0.640</td></tr>
<tr class="lo"><td class="n">3 of 3</td><td class="n">34 &middot; 3.3%</td><td class="n">6</td>
  <td class="n">1.68</td><td class="n">0.352</td><td class="n">0.479</td><td class="n">0.642</td></tr>
</tbody></table></div>

<p><b>This is a trade-off with an optimum, not a monotone preference.</b> Across 24 folded
designs, how much trigger A retains correlates
&rho;&nbsp;=&nbsp;<span class="num">&minus;0.355</span> with separation and
&rho;&nbsp;=&nbsp;<span class="num">+0.581</span> with <code>A_M(11)</code>: take more away
from trigger A and the OFF state improves while the ON state collapses. <b>Keeping 2 of 3 is
the optimum</b> &mdash; the only row that clears &tau;4a on <code>A_M(10)</code> (0.006)
while holding <code>A_M(11)</code> at 0.411 and leaving the start codon accessible at 0.640.
Keeping 3 leaks (<code>A_M(10)</code> 0.352); keeping 0 or 1 turns off without turning on.
238 of our pairs qualify.</p>

<h3>3b &middot; How far to close it &mdash; a designed variable, not a switch</h3>
<p>The first version of this analysis tested only the extreme. Since <code>bulge*</code> is
ours to choose, it can be designed to pair <i>any</i> number of the start codon's three
positions: <code>CAU</code> pairs all three and removes the loop, <code>CCU</code> leaves the
middle unpaired as a designed 1&times;1, <code>CCC</code> leaves two as a designed 2&times;2.
Medians over four candidates, all on the strongest-lock stem:</p>

<div class="scroll"><table>
<thead><tr><th>closure</th><th>bulge*</th><th>separation</th><th>mean-form sep</th>
<th>A_M(10)</th><th>A_M(11)</th><th>AUG(11)</th></tr></thead>
<tbody>
<tr><td>none &mdash; baseline</td><td class="n">trigger-derived</td><td class="n">0.00</td>
  <td class="n">0.000</td><td class="n">0.506</td><td class="n">0.506</td><td class="n">0.502</td></tr>
<tr><td>2&times;2 designed</td><td class="n">CCC</td><td class="n">0.66</td>
  <td class="n">0.133</td><td class="n">0.404</td><td class="n">0.506</td><td class="n">0.502</td></tr>
<tr class="hi"><td><b>1&times;1 designed</b></td><td class="n">CCU</td><td class="n">2.05</td>
  <td class="n"><b>0.225</b></td><td class="n">0.297</td><td class="n"><b>0.505</b></td>
  <td class="n">0.502</td></tr>
<tr class="hi"><td><b>closed entirely</b></td><td class="n">CAU</td><td class="n"><b>6.77</b></td>
  <td class="n">0.219</td><td class="n"><b>0.009</b></td><td class="n">0.404</td>
  <td class="n">0.444</td></tr>
</tbody></table></div>

<p><code>A_M(10)</code> falls monotonically with closure depth &mdash; 0.506, 0.404, 0.297,
0.009 &mdash; which is the leak responding exactly as the mechanism predicts. But the two
end points are not ranked the same way by the two separation forms. On the <b>joint</b> form
full closure wins outright (6.77 against 2.05). On the <b>mean</b> form &mdash; the one the
168-switch calibration says actually tracks performance &mdash; they are level
(<span class="num">0.219</span> against <span class="num">0.225</span>), and the 1&times;1
keeps <code>A_M(11)</code> at 0.505 where full closure drops it to 0.404.</p>

<div class="callout">
<p><b>And it is strongly candidate-dependent, which is the practical point.</b> On x@117,
full closure reaches separation <span class="num">12.00</span> and <b>kills the gate</b>:
<code>A_M(11)</code> 0.111 and the start codon 0.002 accessible. The designed 1&times;1 on the
same candidate gives separation <span class="num">8.24</span> with <code>A_M(11)</code>
<b>0.701</b> and the start codon <b>0.939</b> &mdash; the best result anywhere in this study,
on every axis at once. On x@448 and x@522 the same 1&times;1 does almost nothing (0.39 and
0.03) while full closure still works.</p>
<p>So closure depth is not a setting to fix once. It is a per-candidate choice, and both
settings have to be carried into the panel to find out which the molecule prefers.</p>
</div>

<h3>4 &middot; Unequal stems, 19 bp inhibitory / 17 bp main
<span class="verdict v-test">not needed for mechanism</span></h3>
<div class="split">
<div class="for"><h4>For</h4><ul>
<li><b>Comparability with Kim.</b> Matching his geometry makes our construct interpretable
    against his bench data &mdash; a legitimate reason on its own, independent of mechanism,
    and the reason this option is on the list.</li>
<li>Plausible mechanism: the inhibitory hairpin should out-hold the main one.</li>
</ul></div>
<div class="against"><h4>Against</h4><ul>
<li><b>We already have the mechanism.</b> Measured across 24 designs, our secondary hairpin
    is <i>already</i> more stable than our main one by a median
    <span class="num">5.7&ndash;7.9&nbsp;kcal/mol</span> &mdash; the gap the 19/17 asymmetry
    exists to create. We get it from the lock rather than from length.</li>
<li><b>And the gap does not predict the outcome.</b> Secondary-minus-main stability against
    separation: &rho;&nbsp;=&nbsp;<span class="num">&minus;0.128</span>; against
    <code>A_M(11)</code>: <span class="num">+0.168</span>. Neither significant at n&nbsp;=&nbsp;24.
    Secondary hairpin stability alone: &rho;&nbsp;=&nbsp;<span class="num">&minus;0.030</span>.</li>
<li>Requires changing <code>ARM_LEN</code> and the assembly, not a sequence patch, so it
    costs real work and re-opens R1.</li>
</ul></div>
</div>
<p><b>Verdict:</b> worth doing only if the lab wants direct comparability with Kim&rsquo;s
numbers. On our own measurements it buys nothing mechanistically, because we already have the
stability asymmetry it is designed to produce.</p>

<h3>5 &middot; 5&prime; stabilising hairpin <span class="verdict v-adopt">adopt &mdash; free</span></h3>
<div class="split">
<div class="for"><h4>For</h4><ul>
<li>Both Kim and Green use one; a strong 5&prime; stem-loop blocks RNase&nbsp;E, raising
    transcript half-life.</li>
<li><b>Measured effect on every logic observable: none.</b> Identical to baseline to three
    decimals in all four states.</li>
<li>Folds cleanly on its own: 7-bp stem, 6-nt loop, &minus;15.2 kcal/mol.</li>
</ul></div>
<div class="against"><h4>Against</h4><ul>
<li>Adds 26 nt of synthesis.</li>
<li>Benefit is to stability, which our model does not predict &mdash; we are taking it on
    the literature's word.</li>
</ul></div>
</div>
<p><b>On the trigger side it is meaningless for us</b> and should not be ordered: Kim's
triggers are synthetic transcripts he controls, ours are windows of real mCherry mRNA. We
cannot prepend anything to an endogenous transcript, and in the validation all four control
constructs share the same backbone, so its stability cancels.</p>

<h2>Every form, all four states</h2>
<p>Accessibility is reported three ways in this project and they are not interchangeable:
the <b>joint</b> probability that the whole window is open at once, its energy conversion
<code>dG_open</code>&nbsp;=&nbsp;&minus;RT&nbsp;ln&nbsp;P, and the <b>mean</b> per-base
unpaired probability. The 168-switch calibration says the mean form is the one that tracks
real performance, so both are shown wherever a claim rests on either. Candidate x@448,
B-anchored stem, lock &minus;20.5.</p>

<div class="scroll"><table>
<thead><tr><th>design</th><th>state</th><th>P_open &mdash; joint</th><th>dG_open</th>
<th>mean over W_rank</th><th>A_M &mdash; main stem</th><th>AUG alone</th></tr></thead>
<tbody>
<tr><td rowspan="4">baseline</td><td>00</td><td class="n">1.49 &times; 10<sup>&minus;18</sup></td>
  <td class="n">25.30</td><td class="n">0.4307</td><td class="n">0.1104</td><td class="n">0.606</td></tr>
<tr><td>01</td><td class="n">1.34 &times; 10<sup>&minus;14</sup></td><td class="n">19.69</td>
  <td class="n">0.4538</td><td class="n">0.1103</td><td class="n">0.606</td></tr>
<tr class="lo"><td>10</td><td class="n">4.1536 &times; 10<sup>&minus;5</sup></td><td class="n">6.22</td>
  <td class="n">0.5899</td><td class="n">0.5055</td><td class="n">0.502</td></tr>
<tr class="lo"><td>11</td><td class="n">4.1539 &times; 10<sup>&minus;5</sup></td><td class="n">6.22</td>
  <td class="n">0.5899</td><td class="n">0.5056</td><td class="n">0.502</td></tr>
<tr><td rowspan="4"><b>aug_paired</b></td><td>00</td><td class="n">4.01 &times; 10<sup>&minus;23</sup></td>
  <td class="n">31.78</td><td class="n">0.3671</td><td class="n">0.0043</td><td class="n">0.001</td></tr>
<tr><td>01</td><td class="n">1.13 &times; 10<sup>&minus;18</sup></td><td class="n">25.47</td>
  <td class="n">0.3901</td><td class="n">0.0042</td><td class="n">0.001</td></tr>
<tr class="hi"><td>10</td><td class="n">6.68 &times; 10<sup>&minus;10</sup></td><td class="n">13.02</td>
  <td class="n">0.3743</td><td class="n">0.0043</td><td class="n">0.001</td></tr>
<tr class="hi"><td>11</td><td class="n">3.93 &times; 10<sup>&minus;5</sup></td><td class="n">6.25</td>
  <td class="n">0.5796</td><td class="n">0.4795</td><td class="n">0.476</td></tr>
</tbody></table></div>

<div class="callout">
<p><b>The clearest single number in this study.</b> In the baseline, the ribosome window is
<b>exactly as open with trigger A alone as with both triggers</b>:
P_open(11)&nbsp;/&nbsp;P_open(10)&nbsp;=&nbsp;<span class="num">1.000</span>. After closing the
AUG it is <span class="num">58,848</span>. The gate goes from no discrimination at all
against its worst OFF state to nearly five orders of magnitude.</p>
<p>All three forms agree in direction for the first time: joint 1.00&nbsp;&rarr;&nbsp;58,848&times;,
energy 0.00&nbsp;&rarr;&nbsp;+6.77 kcal/mol, mean-form 0.0000&nbsp;&rarr;&nbsp;+0.1895. And
the start codon behaves as a switch should &mdash; sequestered at 0.001 in all three OFF
states, exposed at 0.476 in the ON state, where the baseline leaves it at 0.502 in every
state including the ones that should be off.</p>
</div>

<h2>What the four states actually look like</h2>
<p>Candidate x@448, strongest-lock stem. Real ViennaRNA minimum-free-energy folds &mdash;
nothing idealised, every base lettered, switch coloured by domain, triggers in saturated fill.
Compare state 10 between the two variants: that is the whole result.</p>
<div class="controls">
  <button id="b-base" aria-pressed="true">baseline</button>
  <button id="b-aug" aria-pressed="false">aug_paired</button>
  <button id="b-zoom" aria-pressed="false">zoom to detail</button>
</div>
<div id="figs-baseline">{figure_panels("baseline")}</div>
<div id="figs-aug" hidden>{figure_panels("aug_paired")}</div>

<h2>Which to optimise first</h2>
<p>The natural plan is to fix the main hairpin first and then tune the secondary, since many
secondary stems share one main hairpin. <b>That order would have told us the modification
does not work</b> &mdash; and for most of this investigation it did exactly that.</p>

<p><b>In the baseline the intuition is right.</b> The secondary stem has no effect on state 10
whatsoever: across twelve builds spanning the Pareto front, <code>dG_open(10)</code> swings
<span class="num">0.00</span> kcal/mol while <code>dG_open(00)</code> swings 0.83 and
<code>dG_open(01)</code> swings 4.48. Whatever the inhibitory hairpin is doing, it does not
reach the ribosome window once trigger A is present.</p>

<p><b>After the AUG is closed, the secondary stem decides everything.</b> Nine stems spanning
the whole front, each at every closure depth:</p>

<div class="scroll"><table>
<thead><tr><th>lock energy</th><th>scheme</th><th>baseline</th><th>2&times;2</th><th>1&times;1</th>
<th>closed</th></tr></thead>
<tbody>
<tr class="hi"><td class="n">&minus;14.6</td><td>B-anchored</td><td class="n">&minus;0.00</td>
  <td class="n">0.66</td><td class="n">2.05</td><td class="n"><b>5.91</b></td></tr>
<tr><td class="n">&minus;10.1</td><td>mixed</td><td class="n">0.00</td><td class="n">0.00</td>
  <td class="n">0.00</td><td class="n">0.79</td></tr>
<tr class="lo"><td class="n">&minus;8.3</td><td>B-anchored</td><td class="n">0.00</td>
  <td class="n">&minus;0.00</td><td class="n">0.00</td><td class="n">0.00</td></tr>
<tr class="lo"><td class="n">&minus;7.0 to &minus;0.2</td><td>6 more stems</td><td class="n">0.00</td>
  <td class="n">0.00</td><td class="n">0.00</td><td class="n">0.00</td></tr>
</tbody></table></div>

<p><b>Lock energy is a threshold, not a gradient.</b> Only 2 of 9 stems support any closure at
all. Below about &minus;10&nbsp;kcal/mol every closure depth reads 0.00, so a main-hairpin
sweep run on a weak stem returns nothing and looks like a failed hypothesis.</p>

<div class="callout">
<p><b>So the order is secondary first, then main</b> &mdash; and it does <i>not</i> require
testing every crossing.</p>
<p>1. Sort the Pareto front by <code>lock_energy</code>. This is a cheap scalar and needs no
folding. 2. Keep the strongest few. 3. Fold the closure depths on those alone.</p>
<p>That is justified because <b>lock energy is a sufficient statistic for the secondary
stem</b>: separation tracks it at &rho;&nbsp;=&nbsp;<span class="num">&minus;0.72</span>
(1&times;1) and <span class="num">&minus;0.61</span> (closed), while the scheme label adds
nothing once lock energy is known &mdash; every scheme shows a median of 0.00 at every
closure, because scheme and lock energy are confounded across the front. The cost is a sort
plus a handful of folds, not <code>stems &times; closures</code>.</p>
</div>

<h2>Who is actually holding the nucleation site</h2>
<p><code>A_S</code> is an <i>unpaired</i> probability over <code>x*</code>, so it cannot tell
<b>held shut by the switch's own stem</b> from <b>held by trigger A</b>. Both are paired, both
read as inaccessible, and they are opposite situations: the first is the lock working, the
second is the leak. Decomposing the same matrix three ways &mdash; paired to <code>sw_x</code>
(locked), paired to trigger A (engaged), unpaired (free) &mdash; shows what
<code>A_S</code> was hiding.</p>

<div class="scroll"><table>
<thead><tr><th>lock</th><th>scheme</th><th>locked (00)</th><th>locked (10)</th>
<th>engaged by A (10)</th><th>separation once closed</th></tr></thead>
<tbody>
<tr class="hi"><td class="n">&minus;18.4</td><td>B-anchored</td><td class="n">0.999</td>
  <td class="n"><b>0.418</b></td><td class="n">0.581</td><td class="n"><b>12.00</b></td></tr>
<tr class="hi"><td class="n">&minus;14.6</td><td>B-anchored</td><td class="n">0.995</td>
  <td class="n"><b>0.254</b></td><td class="n">0.737</td><td class="n"><b>5.91</b></td></tr>
<tr><td class="n">&minus;14.3</td><td>mixed</td><td class="n">0.999</td><td class="n">0.000</td>
  <td class="n">1.000</td><td class="n">6.61</td></tr>
<tr class="lo"><td class="n">&minus;11.8</td><td>mixed</td><td class="n">0.995</td>
  <td class="n">0.000</td><td class="n">1.000</td><td class="n">0.00</td></tr>
<tr class="lo"><td class="n">&minus;9.2</td><td>mixed</td><td class="n">0.995</td>
  <td class="n">0.000</td><td class="n">0.999</td><td class="n">&minus;0.00</td></tr>
<tr class="lo"><td class="n">&minus;8.1</td><td>B-anchored</td><td class="n">0.982</td>
  <td class="n">0.000</td><td class="n">0.999</td><td class="n">&minus;0.00</td></tr>
<tr class="lo"><td class="n">&minus;5.5 to &minus;2.5</td><td>4 more</td><td class="n">0.856&ndash;0.995</td>
  <td class="n">0.000</td><td class="n">0.999&ndash;1.000</td><td class="n">0.00</td></tr>
</tbody></table></div>

<div class="callout">
<p><b>The inhibitory hairpin is not weak. It is out-competed.</b> Read the two locked columns
against each other: with no trigger present the lock holds essentially perfectly &mdash;
0.982 to 0.999 on almost every stem, including every stem that fails. Add trigger A and it
collapses to <b>0.000</b> on 12 of 14. The design is not failing to form its lock; trigger A
is tearing it open, which is the same story as the main hairpin told one domain over.</p>
<p>And in state 11 the mechanism is exactly as drawn: <code>engaged by A</code> has a median
of <span class="num">0.999</span> across every stem. Trigger A always takes the nucleation
site when it should. The problem was never that it fails to &mdash; it is that it also does
so when trigger B is absent.</p>
</div>

<p><b>Which of these should the pipeline select on?</b> Over 14 stems on two trigger pairs,
against separation once the AUG is closed:</p>
<div class="scroll"><table>
<thead><tr><th>candidate axis</th><th>&rho;</th><th>needs folding?</th><th>note</th></tr></thead>
<tbody>
<tr class="hi"><td><code>lock_energy</code></td><td class="n">&minus;0.707</td><td>no</td>
  <td>best predictor, and free</td></tr>
<tr><td><code>locked(00)</code></td><td class="n">+0.689</td><td>yes</td><td>&mdash;</td></tr>
<tr><td><code>locked(10)</code></td><td class="n">+0.641</td><td>yes</td>
  <td>sufficient but <b>not necessary</b></td></tr>
<tr><td><code>engaged_A(10)</code></td><td class="n">&minus;0.311</td><td>yes</td><td>&mdash;</td></tr>
<tr><td><code>free(10)</code></td><td class="n">+0.279</td><td>yes</td><td>&mdash;</td></tr>
</tbody></table></div>

<p><b>Select on <code>lock_energy</code>.</b> It is the strongest predictor and it costs no
folding at all. <code>locked(10)</code> looked binary on the first seven stems &mdash; every
working design had it above zero and every failing one at exactly zero &mdash; but the eighth
broke it: at lock &minus;14.3 the baseline design has <code>locked(10)</code> = 0.000 and
still reaches separation 6.61 once closed. So a non-zero <code>locked(10)</code> is
sufficient, not necessary, and it belongs in the report as a diagnostic rather than a
filter.</p>

<p><b>Regardless of selection, this decomposition should replace <code>A_S</code>.</b> An
unpaired probability cannot express the distinction the architecture turns on, and
&tau;6 (<code>A_S(11) &gt; 0.5</code>) is unsatisfiable precisely because <code>x*</code> is
<i>supposed</i> to be paired in state 11 &mdash; to trigger A. The three-way split says that
directly: engaged 0.999, locked 0.000, free 0.001.</p>

<h2>What this says about the stem schemes</h2>
<p>Scheme C exists because of an assumption: that <b>trigger A needs help binding</b>. It
resolves each contested position in the inhibitory stem in favour of trigger A
(&ldquo;A-anchored&rdquo;), of trigger B (&ldquo;B-anchored&rdquo;), of the lock, or of
neither (&ldquo;unlocked&rdquo;, the all-<code>both</code> build). The equilibrium result
<b>inverts that premise</b> &mdash; trigger A needs no help at all, it needs hindering &mdash;
and the consequence shows up directly in which schemes can reach a working lock.</p>

<p>Census over the <b>full Pareto fronts of 25 trigger pairs</b>, 1,576 builds, no folding
required. The threshold column counts builds reaching the weakest lock energy observed to
support any AUG closure:</p>

<div class="scroll"><table>
<thead><tr><th>scheme</th><th>builds</th><th>median lock</th><th>strongest</th><th>weakest</th>
<th>reach &le; &minus;10 kcal/mol</th></tr></thead>
<tbody>
<tr class="hi"><td>B-anchored</td><td class="n">331</td><td class="n">&minus;11.7</td>
  <td class="n">&minus;26.4</td><td class="n">+7.9</td><td class="n"><b>198 &middot; 60%</b></td></tr>
<tr class="hi"><td>mixed</td><td class="n">1061</td><td class="n">&minus;11.2</td>
  <td class="n">&minus;24.2</td><td class="n">+6.7</td><td class="n"><b>644 &middot; 61%</b></td></tr>
<tr class="lo"><td>A-anchored</td><td class="n">163</td><td class="n">&minus;4.9</td>
  <td class="n">&minus;14.6</td><td class="n">+10.1</td><td class="n"><b>15 &middot; 9%</b></td></tr>
<tr class="lo"><td>unlocked</td><td class="n">21</td><td class="n">+2.1</td>
  <td class="n">&minus;9.0</td><td class="n">+11.3</td><td class="n"><b>0 &middot; 0%</b></td></tr>
</tbody></table></div>

<p><b>B-anchored provides the strongest lock on 25 of 25 pairs.</b> A-anchored reaches a
working lock on 9% of its builds against 60&ndash;61% for B-anchored and mixed; the unlocked
build never does, which is true by construction since it carries no lock at any position.</p>

<div class="callout">
<p><b>Three things follow, and they are different from each other.</b></p>
<p>1. The scheme <i>label</i> carries no information once lock energy is known &mdash; that is
why separation by scheme shows a median of 0.00 in every cell of the factorisation table. Do
not select on the label.</p>
<p>2. The scheme nonetheless <b>determines which lock energies are reachable</b>, and that is
decisive. Select on <code>lock_energy</code>, and A-anchored will disqualify itself.</p>
<p>3. The premise scheme C was built on is the one the investigation overturned. Resolving
contested positions in trigger A's favour is now known to be the wrong direction, and the
census shows A-anchored is exactly the scheme that cannot reach a working lock. The machinery
is still worth having &mdash; it is what <i>generates</i> the strong locks &mdash; but its
selection rule flips.</p>
</div>

<h2>One modification makes another meaningful</h2>
<p>Two of the effects here exist only in combination, which is worth stating plainly because
it is why earlier passes found nothing.</p>
<ul>
<li><b>Closing the AUG needs the lock, and the lock needs the closure.</b> Measured in both
directions on three candidates: neither alone moves <code>separation</code> off
<span class="num">0.00</span>; together they reach
<span class="num">+5.91</span>&ndash;<span class="num">12.00</span>. The mechanism is
symmetric &mdash; closing the AUG makes trigger A need the extra <code>len_x</code> pairs
from <code>x*</code>, and only a locked inhibitory hairpin withholds them in state 10.</li>
<li><b>A variable that does not exist until you make the change.</b> In the baseline,
<code>bulge*</code> is <code>revcomp(trigger_A[6:9])</code> by construction, so trigger A
pairs all three positions in <i>every</i> candidate &mdash; "how much trigger A retains" is a
constant and carries no information. Replace <code>bulge*</code> and it becomes variable, and
then it is the strongest single predictor we have of the ON state
(&rho;&nbsp;=&nbsp;<span class="num">+0.581</span>). The reverse also holds: the natural bulge
class predicts nothing once the loop has been removed, because there is no loop left.</li>
</ul>
<p>The practical consequence is that these five cannot be evaluated one at a time. A panel
that varies one factor at a time would have concluded that none of them works.</p>

<h2>What is missing from the list</h2>
<ol>
<li><b>The exposed toehold, a.</b> We use a&nbsp;=&nbsp;0. Kim's AND works at a&nbsp;=&nbsp;4
and degenerates to a one-input switch at a&nbsp;=&nbsp;10; Green uses 12&ndash;30. <b>We sit
outside the tested range entirely</b>, at the extreme. This is arguably a larger difference
than any of the five, and it is the one Kim actually varied and measured.</li>
<li><b>The ranking statistic.</b> Switching from joint <code>p_open</code> to the mean form is
the best-evidenced change available to us (&rho; &minus;0.11 &rarr; +0.32 on 168 measured
constructs) and it is a code change, not a synthesis cost.</li>
<li><b><code>main_pre</code> is both the reporter's first three codons and a slice of trigger
A.</b> It sits inside the ribosome window and inside trigger A's footprint at once. Decoupling
it costs an N-terminal extension and is the one lever we have never tested.</li>
<li><b>The linker competes with the stem.</b> In the folds above, the run of C's after the AUG
pairs the linker rather than the ascending arm.</li>
<li><b>RBS loop size</b> &mdash; Green widened it from 11 to 15 nt as one of the same four
forward-engineering changes.</li>
</ol>

<h2>Recommendation</h2>
<div class="lede">
<p><b>Order a panel that tells the two hypotheses apart. Do not order a fix for a problem we
have not confirmed exists.</b></p>
</div>
<ol>
<li><b>Change the code, not the molecule, first.</b> Rank on the mean form; report joint
probability, joint energy and mean side by side; make every &tau; gate report-only; add the
kinetic ratio as a standing column. This is the only change with bench evidence behind it and
it costs nothing to make.</li>
<li><b>Build the baseline.</b> It carries a 10&times;&ndash;9,470&times; kinetic advantage and
our metric rejects it. If it works, that is the single most informative result available to
us, and it costs one construct.</li>
<li><b>Build <code>aug_paired</code> on the strongest-lock stem</b> as the contrast arm, with
both closure depths (<code>CAU</code> and <code>CCU</code>) since they differ per candidate.
Select on <code>A_M(11)</code> and start-codon accessibility as well as separation &mdash;
never separation alone.</li>
<li><b>Pick candidates with a high kinetic ratio</b>, which is a criterion the equilibrium
score cannot supply: x@448 at 9,470&times; is a better bet than x@522 at 10&times;, and
nothing in <code>separation</code> distinguishes them.</li>
<li><b>Select the secondary stem on <code>lock_energy</code></b> &mdash; a sort, no folding,
&rho;&nbsp;=&nbsp;&minus;0.707. Drop A-anchored, which reaches a working lock on 9% of builds
against 60&ndash;61% for B-anchored and mixed.</li>
<li><b>Replace <code>A_S</code> with the locked / engaged / free decomposition.</b> Same
matrix, no extra cost, and the only form that distinguishes the lock working from the lock
being torn open.</li>
<li><b>Make R6 report-only.</b> It requires the lock to be weaker than trigger B's grip so B
can displace it &mdash; but B has a 32-nt toehold that is 31&ndash;53% exposed in the OFF
state and does not need a weak lock, while lock strength is the axis we have found to matter.
Keep the invasion-stall cap, which guards the real failure. The same applies to scheme C's
excluded fourth per-position option: both exclusions were judged on the premise that helping
trigger A is good, which is the premise this investigation overturned.</li>
<li><b>Add the 5&prime; stabilising hairpin</b> to every switch construct. Free in our model,
supported in the literature, and it makes our constructs comparable to Kim's.</li>
<li><b>Hold</b> the 3-nt shift and the 19/17 stems. Neither is supported by our measurements;
the first measured near zero, the second was not measured at all and the stability gap it
exists to create is already present.</li>
<li><b>Raise with the supervisor.</b> Our a&nbsp;=&nbsp;0 sits outside the range anyone has
tested &mdash; Kim's AND works at a&nbsp;=&nbsp;4 and degenerates at a&nbsp;=&nbsp;10. And
more fundamentally: for this architecture the equilibrium model cannot distinguish a working
gate from a broken one, so the bench is not a confirmation step. It is the measurement.</li>
</ol>

<div class="foot">
<p><b>Reproduce.</b> <code>modification_panel.py</code> (the variant table),
<code>green_calibration.py</code> (the 168-switch correlation),
<code>four_state_figures.py</code> (these figures),
<code>window_probabilities.py</code> (per-base probabilities),
<code>strand_occupancy.py</code> (where each strand goes). All under
<code>src/engine/gates/notebooks/toehold_and/</code>.</p>
<p><b>Caveats.</b> Every number is ViennaRNA at 37&nbsp;&deg;C, single precision &mdash;
differences below 3&times;10<sup>&minus;5</sup> kcal/mol are unresolved, not zero. Green's 168
switches are single-input, so they calibrate our observables, not our gate. The modification
medians are over six base candidates; the interaction table over three. No weight is fitted to
any data anywhere in this work.</p>
</div>
</div>
<script>
(function(){{
  var base=document.getElementById('figs-baseline'), aug=document.getElementById('figs-aug');
  var bb=document.getElementById('b-base'), ba=document.getElementById('b-aug'),
      bz=document.getElementById('b-zoom');
  function show(which){{
    var isBase = which==='base';
    base.hidden=!isBase; aug.hidden=isBase;
    bb.setAttribute('aria-pressed', String(isBase));
    ba.setAttribute('aria-pressed', String(!isBase));
  }}
  bb.addEventListener('click',function(){{show('base');}});
  ba.addEventListener('click',function(){{show('aug');}});
  bz.addEventListener('click',function(){{
    var on=document.body.classList.toggle('zoom');
    bz.setAttribute('aria-pressed',String(on));
    bz.textContent = on ? 'fit to width' : 'zoom to detail';
  }});
}})();
</script>
"""

(HERE / "report.html").write_text(HEAD + BODY, encoding="utf-8")
print("wrote", HERE / "report.html", (HERE / "report.html").stat().st_size, "bytes")
