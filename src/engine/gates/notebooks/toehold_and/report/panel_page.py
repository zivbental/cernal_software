"""Assemble the panel report page from ``head.html``, ``script.html`` and ``panel_data.json``.

    uv run python src/engine/gates/notebooks/toehold_and/report/panel_page.py

Writes ``report/panel.html``, ready to publish. Run ``panel_data.py`` first -- it produces the
JSON this reads.

The three inputs sit beside this file rather than in a session scratchpad, which is what made the
report unrebuildable once a session ended. ``head.html`` is the prose and styling, ``script.html``
the viewer, and the swaps below are the edits that turn the generic scaffold into this panel's
page; each one asserts its anchor, so a scaffold change fails loudly instead of silently producing
a page with last month's numbers in it.
"""

# ruff: noqa: E501
#
# E501 is off for this file alone, and only for E501. Almost every line here is a literal of the
# report's own HTML prose -- whole paragraphs and table rows quoted verbatim so that each swap can
# assert its anchor against the scaffold. Wrapping them at 100 columns would insert line breaks
# into the anchors, which is how an anchor stops matching and a rebuild silently keeps last month's
# text. The Python in this file is short and stays inside the limit; the rest is content.

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
head = (HERE / "head.html").read_text(encoding="utf-8")
script = (HERE / "script.html").read_text(encoding="utf-8")
data = json.loads((HERE / "panel_data.json").read_text(encoding="utf-8"))


def swap(text, old, new, label):
    assert old in text, f"anchor missing: {label}"
    return text.replace(old, new, 1)


# The title and h1 stay put on purpose: this is the same artifact the panel has always been
# published to, and readers recognise it by that name. The change of substance goes in the
# subtitle, not in the identity.

head = swap(
    head,
    """<p class="sub">Sixteen A0 two-input AND gates arranged so that <strong>each row differs from
another in exactly one thing</strong>: which objective chose it, which secondary-arm geometry
it uses, or which trigger pair it sits on. A bench result therefore points at one cause.</p>""",
    """<p class="sub"><strong>Six A0 two-input AND gates to build</strong>: two trigger pairs
&times; three arms, one geometry. The sweep is finished &mdash; __N_JOINED__ designs scored and
fully joined, 100% coverage &mdash; and the arms were <strong>measured against every library anyone has put on a
bench</strong> rather than argued for. Two of the three are settled: <strong>IED gain</strong>,
the only term that keeps a positive sign on all three libraries, and the <strong>A_M ratio</strong>,
the strongest single term on both of Green's. <strong>The third arm is still open</strong>, and the
block below is the measurement that decides it. <strong>Opening SEP</strong> sets the floor rather
than the order, and accessibility selects the trigger pairs instead of hiding inside a score.</p>

<div class="panel" style="margin-top:14px">
  <h3>The third arm, measured: what each candidate adds that the first two do not</h3>
  <p class="note" style="margin-top:0">An arm earns a bench slot by <em>disagreeing</em> with the
  arms already there &mdash; two arms that rank a cell the same way spend two constructs on one
  question. So the test is Spearman <strong>inside a cell</strong>, against the two arms that stay,
  over the 85 cells with four or more gating designs. Median across cells, with the mean and sd
  because a median alone has argued both sides here before:</p>
  <div class="scroll" style="margin-top:10px"><table><thead><tr><th>candidate third arm</th>
    <th>vs IED gain</th><th>vs A_M ratio</th><th>|&rho;| worst</th>
    <th>its own spread in a cell</th><th>Green 168</th></tr></thead><tbody>
    <tr><td class="mono">dG arm (ON)</td><td class="bad">&minus;0.856
      <span class="dimv">(&minus;0.69&plusmn;0.42)</span></td>
      <td class="bad">&minus;0.541 <span class="dimv">(&minus;0.40&plusmn;0.54)</span></td>
      <td class="bad">0.856</td><td class="bad">0.87 kcal/mol</td>
      <td class="win">+0.315 <span class="dimv">as dG_open_on</span></td></tr>
    <tr><td class="mono">opening SEP</td><td>+0.341
      <span class="dimv">(+0.22&plusmn;0.50)</span></td>
      <td class="win">&minus;0.036 <span class="dimv">(&minus;0.06&plusmn;0.50)</span></td>
      <td class="win">0.341</td><td class="win">3.87 kcal/mol</td>
      <td class="bad">&minus;0.107</td></tr>
    <tr><td class="mono">Barrier</td><td class="win">&minus;0.118
      <span class="dimv">(&minus;0.05&plusmn;0.58)</span></td>
      <td>+0.429 <span class="dimv">(+0.27&plusmn;0.55)</span></td>
      <td>0.429</td><td class="win">3.92 kcal/mol</td><td>+0.179</td></tr>
  </tbody></table></div>
  <p class="note"><strong>dG arm (ON) is the same arm as IED gain.</strong> &rho; &minus;0.856
  inside a cell, beyond |0.8| in 52 of the 85 cells &mdash; and on both chosen pairs it picks
  <em>literally the same design</em>, so the panel spends six bench slots on
  <strong>four</strong> designs. The measured overlap reported earlier, 51%, counted only how often
  the two arms' argmins coincide, which hid this: rank agreement is far stronger than argmin
  agreement.</p>
  <p class="note"><strong>And the ON ceiling is why.</strong> dG arm (ON) is &rho; +1.0000 with
  <span class="mono">open_11</span>, the feasibility ceiling every row already clears at
  <span class="mono">&le; 4.0</span>. The filter has already done the arm's job, which leaves it a
  median within-cell range of <strong>0.87 kcal/mol</strong> to order &mdash; a quarter of what
  either alternative has. That is not an argument for removing the ceiling: a ceiling removes
  designs whose AND-ness is a ratio between two near-zeros, and dropping it readmitted designs at
  <span class="mono">open_11</span> up to 32.</p>
  <p class="note"><strong>Opening SEP is the independent one, and its external sign is the reason
  to test it rather than the reason not to.</strong> |&rho;| at most 0.341 against either arm,
  &minus;0.036 against the A_M ratio &mdash; near-orthogonal &mdash; with 3.87 kcal/mol of spread
  to order with. Swapping it in gives <strong>6 distinct measurements of 6</strong> with no extra
  constraint, against 4 of 6 for dG arm (ON). It scores <span class="mono">&minus;0.107</span> on
  Green's 168, but every library we hold is <strong>single-input</strong>, where AND-ness does not
  exist and the SEP had to be evaluated as its two-state analogue. A fair analogue is not the same
  function, so a wrong sign there is a reason to put it on the bench, not to assume it.
  <strong>Both panels are on this page</strong> &mdash; the <em>panel: three</em> and
  <em>panel: sep3</em> views &mdash; and switching between them is one click.</p>
</div>""",
    "subtitle",
)

# ---- replace the whole grid + geometries + objectives block -------------------------------
OLD = head[
    head.index("  <h3>The grid</h3>") : head.index(
        '<div class="panel" style="margin-top:16px">\n  <h3>How to read a card</h3>'
    )
]
NEW = """  <h3>Which objective is right &mdash; measured, not argued</h3>
  <p class="note" style="margin-top:0">Every objective can be computed on switches somebody has
  already measured at the bench, so the choice between them is decidable rather than a matter of
  taste. Spearman against measured ON/OFF, <strong>signed so positive means the objective points
  the right way</strong>, on all three libraries we have.</p>
  <p class="note"><strong>These are measurements of Green's and VISTA's data and they stand; what
  changed is which of them the panel uses.</strong> The table below was written when the three
  ranking arms were the A_M ratio, the Barrier and their combination. They are now
  <strong>IED gain</strong> and the <strong>A_M ratio</strong>, with the third still open &mdash;
  see the block at the top of this page. <span class="mono">combined</span> is off the panel
  because it is +0.60 with the A_M ratio and +0.57 with the Barrier over our own gating set, so it
  cannot disagree with either; the Barrier is off it because <span class="mono">ied_gain</span> is
  the stronger term on every library and the Barrier remains available as the third arm. Nothing
  in this table was recomputed or revised &mdash; only its bearing on the panel.</p>
  <div class="scroll" style="margin-top:12px"><table><thead><tr><th>objective</th>
    <th>what it is</th><th>Green 168<br><span class="dimv">first-generation</span></th>
    <th>Green 13<br><span class="dimv">forward-engineered</span></th>
    <th>VISTA 189<br><span class="dimv">Robson/Green 2026</span></th></tr></thead><tbody>
    <tr><td><strong>combined</strong></td><td class="dimv">pct(A_M ratio, Barrier, access)</td><td class="win">+0.366</td>
      <td class="win">+0.591</td><td class="bad">&minus;0.097</td></tr>
    <tr><td><strong>A_M ratio</strong></td><td class="dimv">A_M(11) / max(A_M OFF)</td><td class="win">+0.306</td>
      <td class="win">+0.698</td><td class="bad">&minus;0.016</td></tr>
    <tr><td>combined with SEP</td><td class="dimv">pct(SEP, Barrier, access)</td><td>+0.213</td>
      <td>+0.526</td><td class="bad">&minus;0.144</td></tr>
    <tr><td><strong>Barrier</strong></td><td class="dimv">find_saddle, kcal/mol</td><td>+0.179</td>
      <td>+0.280</td><td class="bad">&minus;0.130</td></tr>
    <tr><td>opening SEP</td><td class="dimv">open-energy difference &mdash; the floor</td><td class="bad">&minus;0.107</td>
      <td class="bad">&minus;0.033</td><td class="bad">&minus;0.070</td></tr>
  </tbody></table></div>
  <p class="note"><strong>Green's two libraries agree on everything that decides the panel:</strong>
  the SEP at or below zero, the ratio and the combination on top, the barrier weakest of the positive ones. On the 168 no
  leave-one-out range straddles zero, so that ordering is not one influential switch. They
  <em>disagree</em> on the ratio against the combination &mdash; the combination wins on the 168, the ratio wins on the 13 &mdash; which is
  the measured reason <strong>both stay in the panel</strong> instead of one being dropped.</p>
  <p class="note">Two things to hold against that agreement. n&nbsp;=&nbsp;13 is small: there opening SEP's
  leave-one-out range is <span class="mono">[&minus;0.315,&nbsp;+0.147]</span> and straddles zero.
  And the two libraries are <strong>not independent</strong> &mdash; same lab, same design rules,
  same reporter &mdash; so "two datasets agree" is weaker than it sounds. Reproduce all of it with
  <span class="mono">objective_vs_green.py</span>; the barrier had never been computed on any of
  these switches before.</p>

  <h3 style="margin-top:18px">The objectives against each other</h3>
  <p class="note" style="margin-top:0">Spearman over the <strong>1,317</strong> designs that
  survive every filter and gate, signed so <strong>positive means the two agree about which design
  is better</strong>. This is the table that says what the panel is actually testing, and it is
  remeasured for this build &mdash; the previous version ran over 3,829 designs, a population two
  filters ago.</p>
  <div class="scroll" style="margin-top:10px"><table><thead><tr><th></th>
    <th>IED gain</th><th>A_M ratio</th><th>opening SEP</th><th>dG arm (ON)</th><th>Barrier</th>
    <th>combined</th></tr></thead><tbody>
    <tr><td><strong>IED gain</strong></td><td class="dimv">&mdash;</td><td>+0.50</td>
      <td class="win">&minus;0.14</td><td class="bad">+0.44</td><td class="win">+0.08</td>
      <td>+0.48</td></tr>
    <tr><td><strong>A_M ratio</strong></td><td>+0.50</td><td class="dimv">&mdash;</td>
      <td class="win">+0.08</td><td>+0.30</td><td>&minus;0.28</td><td class="bad">+0.60</td></tr>
    <tr><td><strong>opening SEP</strong></td><td class="win">&minus;0.14</td>
      <td class="win">+0.08</td><td class="dimv">&mdash;</td><td class="win">&minus;0.15</td>
      <td>&minus;0.17</td><td class="win">&minus;0.07</td></tr>
    <tr><td>dG arm (ON)</td><td class="bad">+0.44</td><td>+0.30</td>
      <td class="win">&minus;0.15</td><td class="dimv">&mdash;</td><td>+0.48</td>
      <td class="bad">+0.64</td></tr>
    <tr><td>Barrier</td><td class="win">+0.08</td><td>&minus;0.28</td><td>&minus;0.17</td>
      <td>+0.48</td><td class="dimv">&mdash;</td><td class="bad">+0.57</td></tr>
    <tr><td>combined</td><td>+0.48</td><td class="bad">+0.60</td><td class="win">&minus;0.07</td>
      <td class="bad">+0.64</td><td class="bad">+0.57</td><td class="dimv">&mdash;</td></tr>
  </tbody></table></div>
  <p class="note"><strong>Read this table pooled, and then read the one at the top of the page
  instead.</strong> Pooled over 1,317 designs it answers "do these two agree across the whole
  population", which is not the question the panel asks: every row of the panel compares designs
  <em>inside one cell</em>, where the trigger pair and the geometry are fixed. The two answers
  differ sharply &mdash; pooled, dG arm (ON) against IED gain is +0.44; within a cell it is
  &minus;0.856. Pooled correlation is diluted by between-cell variation that the panel holds
  fixed by construction, so <strong>the within-cell numbers are the ones that decide an arm</strong>
  and these are context.</p>
  <p class="note"><span class="mono">combined</span> is the clearest case: +0.60 with the A_M
  ratio, +0.64 with dG arm (ON) and +0.57 with the Barrier &mdash; it agrees with everything, which
  is what an aggregate of them does, and it is why it is no longer one of the three.</p>
  <p class="note">The floor, <strong>opening SEP</strong>, is the most independent column here
  (|&rho;| &le; 0.17 against everything) &mdash; exactly what a floor should be, and also the
  reason it is the leading candidate for the third arm.</p>

  <h3 style="margin-top:18px">VISTA inverts every objective, and we do not know why</h3>
  <p class="note" style="margin-top:0">All five are at or below zero on VISTA's 189 switches. That
  is not one metric flipping &mdash; it is the whole family, which means VISTA's ON/OFF is driven
  by something none of these objectives models. <strong>Two explanations were tested and both
  failed:</strong></p>
  <div class="scroll" style="margin-top:10px"><table><thead><tr><th>the guess</th>
    <th>the test</th><th>verdict</th></tr></thead><tbody>
    <tr><td>VISTA's OFF states are not really shut, so there is nothing to open</td>
      <td class="dimv"><span class="mono">dG_open_off</span> in both libraries: median
      <span class="mono">17.76</span> against Green's <span class="mono">17.77</span>, mean
      17.71 against 17.69, minimum 10.4&nbsp;kcal/mol</td>
      <td class="bad">no &mdash; identically shut</td></tr>
    <tr><td>VISTA's toeholds are occluded, so no trigger can nucleate</td>
      <td class="dimv">They <em>are</em> twice as occluded &mdash; toehold-18 defect median
      <span class="mono">0.568</span> against <span class="mono">0.303</span> and the 13's
      <span class="mono">0.245</span>. But <strong>matching on it does not rescue the
      correlation</strong>: inside the band both libraries occupy (0.229&ndash;0.601) combined is
      <span class="mono win">+0.347</span> on Green and <span class="mono bad">&minus;0.081</span>
      on VISTA; in the tightest sub-band, <span class="mono win">+0.484</span> against
      <span class="mono bad">&minus;0.509</span> on switches with the <em>same</em> toehold
      accessibility (VISTA n&nbsp;=&nbsp;11 there &mdash; a direction, not a magnitude)</td>
      <td class="bad">no &mdash; the sign survives matching</td></tr>
  </tbody></table></div>
  <p class="note">A sign that survives matching is not explained by the axis matched on. So VISTA
  is a <strong>warning about generalisation, not a vote</strong>: it says these objectives are
  calibrated to Green's design regime and should not be assumed to carry outside it. The panel is
  built on Green's two libraries and says so.</p>
  <p class="note"><strong>Green's endogenous sensors are not a third opinion.</strong> Tables S4
  and S5 carry sensor sequences, target subsequences and plasmid names &mdash; there is
  <strong>no measured ratio column</strong>, so there is nothing to correlate against. The
  Figure&nbsp;4 numbers exist only in the figures.</p>

  <div class="two" style="margin-top:14px">
    <div>
      <h3>The opening SEP is demoted, not deleted</h3>
      <p class="note" style="margin-top:0">the opening SEP is the quantity the design theory recommends, and
      on Green's data a <em>larger</em> open-energy difference goes with a <em>worse</em> measured
      ON/OFF. That is a real result, but it is narrower than it looks: it says opening SEP ranks badly
      <strong>among designs that already gate</strong>, not that AND-ness is meaningless. So opening SEP
      keeps the job it stands up in &mdash; the <strong>gating floor</strong>. Every row here
      already satisfies <span class="mono">SEP &le; &minus;2.0&nbsp;kcal/mol</span>; above that
      line the order comes from the three objectives that point forwards.</p>
      <p class="note"><strong>The caveat that keeps opening SEP on the cards.</strong> Green's switches are
      <strong>single-input</strong>, so AND-ness does not exist there. the SEP was evaluated as its
      two-state analogue <span class="mono">dG_open(ON) &minus; dG_open(OFF)</span> &mdash; the
      same quantity one trigger short. A fair analogue is not the same function, which is why a
      wrong sign is a reason to <em>test</em> opening SEP at the bench rather than to assume it.</p>
    </div>
    <div>
      <h3>The arms that rank, as of this build</h3>
      <p class="note" style="margin-top:0">Two are settled and the third is open. The block at the
      top of this page is the measurement that decides the third; this is what each arm is.</p>
      <dl>
        <div><dt>IED gain</dt><dd>
          <span class="mono">ied(00) &minus; ied(11)</span> over the RBS-loop-to-linker span, 57
          nt. The <strong>only term we hold that keeps a positive sign on all three measured
          libraries</strong> &mdash; +0.345, +0.495, +0.116. Its two halves point opposite ways,
          which is what a gain needs: a closed OFF state helps and an open ON state helps.</dd></div>
        <div><dt>A_M ratio</dt><dd>
          <span class="mono">A_M(11) / max[A_M(00), A_M(01), A_M(10)]</span>. The strongest single
          term on both of Green's libraries, +0.306 and +0.698. Unbounded, so a near-zero
          denominator inflates it &mdash; which is a real defect, measured below.</dd></div>
        <div><dt>the third</dt><dd><strong>open.</strong> <span class="mono">dG arm (ON)</span>
          duplicates IED gain within a cell at &rho; &minus;0.856 and buys four designs for six
          slots; <span class="mono">opening SEP</span> is near-independent and buys six, at the
          cost of a negative sign on Green's single-input data;
          <span class="mono">Barrier</span> sits between them. Both built panels are on this page
          as views.</dd></div>
      </dl>
      <p class="note"><strong>Two arms left the panel on measurement, not taste.</strong>
      <span class="mono">A_M gain</span> is out because <span class="mono">ied_gain</span> ranks it
      at &rho;&nbsp;+0.929 within a cell &mdash; four of six constructs on one question.
      <span class="mono">dG rbs-linker</span> is out because it is an OFF-state MFE of an isolated
      subsequence: two designs in one cell with an identical &minus;7.20 differ 2.4&times; in how
      far the stem opens in tube 11, so it is blind to the only difference between them.</p>
    </div>
  </div>

  <h3 style="margin-top:18px">The A_M ratio is capturing one bulge geometry</h3>
  <p class="note" style="margin-top:0">The A_M window is
  <span class="mono">main_z(6) + AUG(3) + main_pre(9)</span> = 18 nt, so <strong>the AUG is inside
  it</strong>. That makes the following a direct consequence rather than a coincidence. Remeasured
  for this build over the <strong>1,317</strong> gating designs:</p>
  <div class="scroll"><table><thead><tr><th>closure</th><th>n</th><th>share</th>
    <th>median A_M ratio</th><th>median worst-OFF A_M</th><th>median A_M(11)</th>
    </tr></thead><tbody>
    <tr><td class="mono">closed_*</td><td>93</td><td>7.1%</td><td class="bad">58.37</td>
      <td class="bad">0.0090</td><td>0.507</td></tr>
    <tr><td class="mono">open / pair*</td><td>1,224</td><td>92.9%</td><td>4.97</td>
      <td>0.1207</td><td class="win">0.592</td></tr>
  </tbody></table></div>
  <p class="note"><strong>7.1% of the population holds 76 of the top 100 by A_M ratio</strong>
  &mdash; and does it with a <em>lower</em> median A_M(11). A closed AUG bulge shuts the window in
  the OFF tubes, the denominator falls to 0.0077 against 0.1220, and the ratio rises even though
  the ON state got worse. The five most extreme designs in the sweep all have a worst-OFF A_M
  between 0.0011 and 0.0017, which is where a ratio of 300&ndash;380 comes from. The panel's own
  315.6 design is one of them: A_M(11) 0.532, worst-OFF 0.0017,
  <span class="mono">closed_CGU</span>.</p>
  <p class="note"><strong>And no library we have can arbitrate it</strong>, which is the part that
  decides what to do. Green's 168 switches have a worst-OFF A_M spanning
  <span class="mono">0.1228&ndash;0.1739</span> &mdash; a factor of 1.4, with
  <strong>none</strong> below 0.10. VISTA's 189 span 0.1282&ndash;0.5933, also none below 0.10.
  Our own population spans <span class="mono">0.0011&ndash;0.5895</span>, a factor of 536, with
  <strong>35%</strong> below 0.10. So on Green's data the denominator is very nearly a constant,
  the ratio is <em>A_M(11) rescaled</em>, and every repair ties exactly: flooring the denominator
  at 0.01, 0.05 or 0.10, capping the ratio at 20&times;, or taking its log all give
  <span class="mono">+0.306</span> on G168 and <span class="mono">+0.698</span> on G13, identical
  to the raw ratio. <strong>Green validated A_M(11), not the ratio.</strong> The denominator that
  drives our tail was never tested by any measured library, and it misbehaves on ours.</p>

  <h3 style="margin-top:18px">Green's ON/OFF is an ON-state measurement, in his own words</h3>
  <p class="note" style="margin-top:0">From the Extended Experimental Procedures, S13:
  &ldquo;ON/OFF ratios as opposed to fluorescence output in the ON and OFF states alone were used
  for quantitative analysis since <strong>fluorescence OFF levels varied relatively little over
  the library compared to ON levels, leaving ON/OFF ratios essentially a measure of ON state
  fluorescence</strong>.&rdquo;</p>
  <p class="note">So both sides of every correlation on this page are ON-state quantities. That is
  the same conclusion the structural side reached independently &mdash; his worst-OFF A_M spans a
  factor of 1.4 &mdash; arrived at from the measurement rather than from the fold.
  <strong>Consequence: nothing in any library we hold validates an OFF-state or an AND-ness
  term.</strong> It is the reason the opening SEP can be at &minus;0.107 without that being
  evidence against AND-ness, and the reason an energy metric for ranking should be an
  <em>ON</em> energy, with the OFF side left to the filters.</p>
  <p class="note">Two more things from S13 that agree with the table below, measured here
  independently. Green found &ldquo;the RBS/mRNA secondary structure terms constitute the category
  of parameters with the strongest overall correlation&rdquo;, with
  <span class="mono">&Delta;G<sub>RBS-linker</sub></span> the best of them &mdash; and our top two
  are <span class="mono">ied_rbs_linker_on</span> (+0.356) and
  <span class="mono">dG_rbs_linker</span> (+0.334) over that same span. He also reports that
  &ldquo;strong correlations were not observed for the first-generation switch library when
  analyzed as a whole&rdquo;, which is why a best-in-table figure of +0.36 is the expected
  ceiling here and not a sign something is broken. Caveat on the parameter set: he used Mathews
  1999 for analysis and Serra &amp; Turner 1995 for design; ViennaRNA 2.7.2 here defaults to
  Turner 2004.</p>

  <h3 style="margin-top:18px">Removing the AUG from the A_M window breaks it</h3>
  <p class="note" style="margin-top:0">The arm is
  <span class="mono">main_z(6) + AUG(3) + main_pre(9)</span> and the statistic is a plain per-base
  mean, so the 15-nt mean without the AUG is exact arithmetic on stored values &mdash;
  <span class="mono">(18&middot;A_M &minus; 3&middot;aug) / 15</span>, no refolding. Tested both
  ways:</p>
  <div class="scroll"><table><thead><tr><th>metric</th><th>G168</th><th>G13</th>
    <th>closed_* in our top 100</th><th>spread on G168</th></tr></thead><tbody>
    <tr><td class="mono">A_M_ratio &mdash; 18 nt, with the AUG</td><td class="win">+0.306</td>
      <td class="win">+0.698</td><td class="bad">89/100</td><td>2.25&ndash;6.96</td></tr>
    <tr><td class="mono">A_M_ratio &mdash; 15 nt, AUG removed</td><td class="bad">&minus;0.236</td>
      <td>+0.374</td><td class="win">9/100</td><td class="bad">32.7&ndash;453.9</td></tr>
    <tr><td class="mono">A_M_gain &mdash; 18 nt, the DIFFERENCE</td><td class="win">+0.320</td>
      <td>+0.560</td><td class="win">5/100</td><td>0.21&ndash;0.80</td></tr>
  </tbody></table></div>
  <p class="note"><strong>The AUG triplet is both the ratio's entire validated signal and the
  mechanism of its architecture capture.</strong> Remove it and the correlation on G168
  <em>inverts</em>, from +0.306 to &minus;0.236, while the capture does drop to 9/100. The reason
  is in the architecture: <span class="mono">aug_off</span> on Green's 168 spans
  <strong>0.644&ndash;0.983</strong> &mdash; his AUG sits <em>open</em> in a bulge in the OFF state
  while the stem around it is shut, so the AUG's openness is most of what
  <span class="mono">A_M_off</span> measures (3&times;0.8/18 &asymp; 0.13, matching his observed
  0.12&ndash;0.17). Strip it out and the denominator becomes the near-zero stem, the ratio spans
  33&ndash;454, and it orders by stem noise.</p>
  <p class="note">Our ordinary designs match his: worst OFF-state <span class="mono">aug</span>
  median <strong>0.667</strong>. Our <span class="mono">closed_*</span> designs sit at
  <strong>0.001</strong> &mdash; a 667&times; difference in that one quantity, and an architecture
  no switch in any measured library has. Green's own S6.2 names this: ensemble optimisation
  &ldquo;can lead to additional base pairs in the stem of switch RNA at its base <strong>or in the
  AUG bulge region</strong>&rdquo;, which he calls a defect that &ldquo;occurred often in the
  forward-engineered toehold switches&rdquo; &mdash; and the forward-engineered set is exactly
  where <span class="mono">A_M_ratio</span> scores best (+0.698). So the question of whether a shut
  AUG bulge helps or hurts is open, not settled, and 175 of our designs bet on it.</p>
  <p class="note"><strong>So the fix is not the window, it is the statistic.</strong>
  <span class="mono">A_M_gain</span> &mdash; the difference instead of the ratio, same 18-nt window
  &mdash; is <em>better</em> than the ratio on G168 (+0.320 against +0.306), bounded
  (&minus;0.17&ndash;0.82 on our population against 0.45&ndash;383.6), and
  <strong>architecture-neutral</strong>: closed_* median 0.444 against 0.432 for everything else,
  and 5 of the top 100 against their 4.7% population share. It costs G13, where the ratio keeps
  +0.698 against the difference's +0.560 &mdash; and that is an n=13 set on which Pearson and
  Spearman disagree by up to 0.48. <strong>This recommendation was acted on, and not as written.</strong>
  <span class="mono">A_M_gain</span> did not become an arm: once <span class="mono">ied_gain</span>
  was measured it turned out to rank <span class="mono">A_M_gain</span> at &rho;&nbsp;+0.929
  <em>within a cell</em>, so the two would have spent four of six constructs on one question, and
  <span class="mono">ied_gain</span> is the stronger of them on every library (+0.345 / +0.495 /
  +0.116 against +0.320 / +0.560 / &minus;0.026 &mdash; and it is the one that does not flip sign
  on VISTA). So the panel kept the A_M <em>ratio</em> for the signal Green validated and took
  <span class="mono">ied_gain</span> for the gain, rather than carrying two gains. The
  <span class="mono">closed_*</span> half of the recommendation stands and is unresolved: those 93
  designs are still scored on the same axis as open-bulge ones, and the closure is on every card so
  it can be read.</p>

  <h3 style="margin-top:18px">Every metric against every measured library</h3>
  <p class="note" style="margin-top:0">Signed Spearman, so positive means the metric points the
  right way; Pearson in brackets. Built by
  <span class="mono">metric_correlations.py</span>, which folds each published switch through the
  same <span class="mono">FoldEngine</span>. The window matters: two metrics over the same span
  compare <em>statistics</em>, two over different spans are not comparable at all.
  <strong>Kim 2019 is absent deliberately</strong> &mdash; his four constructs are a null test for
  a two-input gate, trigger B moves A_M by 1e&minus;13, so the AND axis has no variance, and four
  points could not carry a correlation even if it did.</p>
  <div class="scroll"><table><thead><tr><th>metric</th><th>window</th><th>G168 (n=168)</th>
    <th>G13 (n=13)</th><th>VISTA (n=189)</th></tr></thead><tbody>
    <tr><td class="mono">ied_rbs_linker_on</td><td class="dimv">RBS loop..linker</td>
      <td class="win">+0.356 [+0.324]</td><td class="win">+0.390 [+0.521]</td><td>&minus;0.096</td></tr>
    <tr><td class="mono">dG_rbs_linker</td><td class="dimv">RBS loop..linker</td>
      <td>+0.334 [+0.274]</td><td>+0.263 [<strong>+0.693</strong>]</td><td>&minus;0.134</td></tr>
    <tr><td class="mono">A_M_gain</td><td class="dimv">arm, 18 nt</td>
      <td class="win">+0.320 [+0.277]</td><td>+0.560 [+0.708]</td><td>&minus;0.026</td></tr>
    <tr><td class="mono">mean_wrank_gain</td><td class="dimv">W_rank, 31 nt</td>
      <td>+0.317 [+0.316]</td><td>+0.330 [+0.581]</td><td>&minus;0.005</td></tr>
    <tr><td class="mono">A_M_on</td><td class="dimv">arm, 18 nt</td>
      <td>+0.315 [+0.271]</td><td>+0.527 [+0.678]</td><td>&minus;0.050</td></tr>
    <tr><td class="mono">dG_open_on</td><td class="dimv">W_rank, 31 nt</td>
      <td>+0.315 [+0.215]</td><td>+0.478 [+0.729]</td><td>&minus;0.074</td></tr>
    <tr><td class="mono">A_M_ratio</td><td class="dimv">arm, 18 nt</td>
      <td>+0.306 [+0.288]</td><td class="win">+0.698 [+0.685]</td><td>&minus;0.016</td></tr>
    <tr><td class="mono">aug_gain</td><td class="dimv">AUG, 3 nt</td>
      <td>+0.241 [+0.258]</td><td>+0.610 [+0.670]</td><td>+0.123</td></tr>
    <tr><td class="mono">aug_on</td><td class="dimv">AUG, 3 nt</td>
      <td>+0.240 [+0.236]</td><td>+0.560 [+0.661]</td><td>+0.080</td></tr>
    <tr><td class="mono">mean_wrank_off</td><td class="dimv">W_rank, 31 nt</td>
      <td>+0.140 [+0.186]</td><td>+0.615 [+0.763]</td><td>+0.036</td></tr>
    <tr><td class="mono">aug_off</td><td class="dimv">AUG, 3 nt</td>
      <td>+0.091 [+0.169]</td><td>+0.516 [+0.605]</td><td>+0.068</td></tr>
    <tr><td class="mono">k_analogue12</td><td class="dimv">toehold, first 12 nt</td>
      <td>+0.023</td><td>&minus;0.154</td><td>&minus;0.118</td></tr>
    <tr><td class="mono">A_M_off</td><td class="dimv">arm, 18 nt</td>
      <td>&minus;0.046 [+0.089]</td><td>+0.648 [+0.721]</td><td>+0.021</td></tr>
    <tr><td class="mono">narrow_sep</td><td class="dimv">AUG, 3 nt</td>
      <td class="bad">&minus;0.107</td><td>+0.170</td><td>+0.035</td></tr>
    <tr><td class="mono">separation</td><td class="dimv">W_rank, 31 nt</td>
      <td class="bad">&minus;0.107 [&minus;0.154]</td>
      <td>&minus;0.033 [<strong>+0.449</strong>]</td><td>&minus;0.070</td></tr>
    <tr><td class="mono">dG_OFF</td><td class="dimv">whole switch</td>
      <td>&minus;0.284</td><td>&minus;0.253</td><td class="dimv">&mdash;</td></tr>
    <tr><td class="mono">ied_rbs_linker_gain</td><td class="dimv">RBS loop..linker</td>
      <td class="bad">&minus;0.345</td><td class="bad">&minus;0.495</td><td>&minus;0.116</td></tr>
    <tr><td class="mono">dG_open_off</td><td class="dimv">W_rank, 31 nt</td>
      <td class="bad">&minus;0.362 [&minus;0.312]</td><td>&minus;0.236 [+0.066]</td>
      <td>&minus;0.024</td></tr>
  </tbody></table></div>

  <p class="note"><strong>The subtraction collapse, explained.</strong> It is not a property of
  subtraction &mdash; three of the four differences are fine, and two are the best metrics in the
  table:</p>
  <div class="scroll"><table><thead><tr><th>difference</th><th>OFF term</th><th>ON term</th>
    <th>the difference</th><th></th></tr></thead><tbody>
    <tr><td class="mono">separation</td><td class="bad">&minus;0.362</td><td>+0.315</td>
      <td class="bad">&minus;0.107</td><td class="dimv">collapses</td></tr>
    <tr><td class="mono">A_M_gain</td><td>&minus;0.046</td><td>+0.315</td>
      <td class="win">+0.320</td><td class="dimv">survives</td></tr>
    <tr><td class="mono">mean_wrank_gain</td><td>+0.140</td><td>+0.309</td>
      <td class="win">+0.317</td><td class="dimv">survives</td></tr>
    <tr><td class="mono">aug_gain</td><td>+0.091</td><td>+0.240</td><td>+0.241</td>
      <td class="dimv">survives</td></tr>
  </tbody></table></div>
  <p class="note">Only the <em>energy</em> difference collapses, and the reason is in its OFF
  term: <span class="mono">dG_open_off</span> carries a strong correlation pointing the
  <strong>wrong way</strong> (&minus;0.362). Subtracting a strongly wrong-signed term from a
  right-signed one cancels it &mdash; 0.315 &minus; 0.362 lands near the observed &minus;0.107.
  The mean-unpaired differences keep their signal because their OFF terms are near zero. The
  mechanism behind the wrong sign: in Green's library a very stable OFF stem is also one that
  fails to open in the ON state, so <span class="mono">dG_open_off</span> partly measures "too
  stable to work at all".</p>
  <p class="note"><strong>Pearson versus Spearman.</strong> On G168 the gap is small &mdash; at
  most 0.079, on <span class="mono">aug_off</span>. On <strong>G13</strong> it is large and
  changes conclusions: <span class="mono">dG_rbs_linker</span> is +0.263 by rank and
  <strong>+0.693</strong> linearly, and <span class="mono">separation</span> is &minus;0.033 by
  rank and <strong>+0.449</strong> linearly &mdash; a sign flip. With n=13 and ON/OFF spanning
  three orders of magnitude, Pearson is set by one or two switches. That is where "good Pearson,
  bad Spearman" comes from, and it is a reason to read the rank correlation, not a second result.</p>

  <h3 style="margin-top:18px">A-anchored designs are inert, not leaky</h3>
  <p class="note" style="margin-top:0">Of 4,046 A-anchored designs scored, <strong>392</strong>
  pass every feasibility test except the scheme filter, and <strong>0</strong> gate. The reason is
  not a marginal score:</p>
  <div class="scroll"><table><thead><tr><th>scheme</th><th>pass all but scheme</th>
    <th>opening SEP, median</th><th>A_M ratio, median</th><th>A_M(11), median</th><th>gating</th>
    </tr></thead><tbody>
    <tr><td class="mono">A-anchored</td><td>392</td><td class="bad">0.000</td>
      <td class="bad">1.000</td><td>0.637</td><td class="bad">0</td></tr>
    <tr><td class="mono">mixed</td><td>6,761</td><td>&minus;2.134</td><td>2.566</td><td>0.605</td>
      <td class="win">3,459</td></tr>
    <tr><td class="mono">B-anchored</td><td>8,062</td><td>&minus;1.936</td><td>2.486</td>
      <td>0.590</td><td class="win">3,994</td></tr>
  </tbody></table></div>
  <p class="note">A-anchored's opening SEP runs from <span class="mono">&minus;0.000</span> to
  <span class="mono">0.000</span> across all 392 &mdash; identically flat &mdash; and its A_M
  ratio has a median of exactly <strong>1.000</strong>. A ratio of 1.000 means A_M(11) equals the
  worst OFF state: <strong>the triggers do not change the switch at all</strong>. Meanwhile
  A_M(11) is 0.637, <em>higher</em> than either working scheme, and the barrier is unremarkable.
  So these designs open fine and open the same amount with or without triggers.</p>
  <p class="note">That answers the fair objection that A-anchored is being judged by the metric
  with the weakest support. It is not: it is flat on <em>every</em> state-dependent metric at once
  while healthy on the state-independent ones, and a weakly-correlated metric can still correctly
  report zero variance. The second half of the idea needs no change &mdash;
  <span class="mono">mixed</span> is <strong>already in the panel</strong>, not a dead scheme:
  23,490 scored, 3,459 gating, and it holds the highest A_M ratio in the entire sweep (383.6).</p>

  <h3 style="margin-top:18px">Why these two trigger pairs</h3>
  <p class="note" style="margin-top:0">The rule is <span class="mono">pick_six</span>, and it is
  <strong>maximise the worst arm</strong>: a pair is a candidate only when its cell can serve every
  arm the panel emits, and candidates are then ranked on the <em>worst</em> of the three arms'
  percentiles. Percentiles because the arms are in different units &mdash; a probability
  difference, a ratio and kcal/mol &mdash; so a raw comparison between them means nothing. A pair
  has to serve all three rather than being carried by one.</p>
  <p class="note">(This block previously described <span class="mono">pick</span>, which sorts on
  <span class="mono">(&minus;splits, &minus;quality)</span> across two geometries and is the
  <em>survey</em> path, not the bench panel. It named pairs 645/446/4 and 625/124/6, which no
  build has used for some time.)</p>
  <p class="note"><strong>And the rule has a cost worth seeing.</strong> Maximising the worst arm
  means a pair strong on two arms and weak on one loses to a pair that is middling on all three.
  Measured on this build, with opening SEP as the third arm, over the 56 candidate pairs:</p>
  <div class="scroll"><table><thead><tr><th>rank</th><th>pair</th><th>worst percentile</th>
    <th>best A_M ratio in the cell</th><th>cell</th><th></th></tr></thead><tbody>
    <tr class="win"><td>1</td><td class="mono">507/260/4</td><td>16.1</td><td>12.7</td><td>28</td>
      <td class="dimv">chosen</td></tr>
    <tr class="win"><td>2</td><td class="mono">53/605/5</td><td>28.6</td><td>9.6</td><td>21</td>
      <td class="dimv">chosen</td></tr>
    <tr><td>3</td><td class="mono">601/54/5</td><td>33.9</td><td>15.0</td><td>9</td><td></td></tr>
    <tr><td>4</td><td class="mono">612/439/4</td><td>37.5</td><td class="win">82.0</td><td>8</td>
      <td class="bad">all three arms pick one design</td></tr>
    <tr><td>30</td><td class="mono">414/361/4</td><td>&mdash;</td><td class="win">96.0</td>
      <td>10</td><td class="dimv">splits three ways; weak on opening SEP</td></tr>
  </tbody></table></div>
  <p class="note"><strong>So the low A_M ratios on the panel are the rule's doing, not the
  population's.</strong> The pair holding the best A_M ratio available anywhere, 96.0, splits three
  ways and is still at rank 30, because its opening SEP runs &minus;3.63 to &minus;4.96 against
  507/260/4's &minus;9.83. Pinning it &mdash;
  <span class="mono">--pin 414/361/4,507/260/4</span> &mdash; gives A_M ratios of
  <strong>88.8 / 96.0 / 94.9</strong> on the first pair and still 6 distinct measurements of 6, at
  the price of that pair's SEP. The next-best A_M pair, 612/439/4 at 82.0 and rank 4, is not an
  option at all: all three arms land on one design there, so it buys 4 of 6.</p>
  <p class="note">The first hypothesis tested here was that <em>splitting three ways</em> is what
  costs the A_M ratio. It is not &mdash; &rho;(best A_M in cell, how many arms split) is
  <strong>+0.146</strong>, so splitting pairs have slightly <em>higher</em> A_M, and the 96.0 pair
  is one of the 20 that split. Which arm is third, and the maximise-the-worst rule, are what
  decide it.</p>

  <h3 style="margin-top:18px">The reference was corrected, and what that actually cost</h3>
  <p class="note" style="margin-top:0">The mCherry reference was corrected at six positions &mdash;
  <span class="mono">62, 356, 434, 482, 578, 590</span> &mdash; and <strong>all six are at codon
  base 3</strong>, so the protein is unchanged. A switch's trigger-derived domains
  (<span class="mono">r2*</span>, <span class="mono">sw_x</span>, <span class="mono">x*</span>,
  <span class="mono">main_pre_star</span>, <span class="mono">k1_star</span>) are the reverse
  complement of the window <em>as it was</em>, so a design covering a corrected base encodes a base
  that is not in the transcript, and its energies, A_M values and barrier were all computed on that
  mismatch. <span class="mono">transcript_drift.py</span> recomputes the list from git and names
  every affected design and pair.</p>
  <p class="note"><strong>The counts in this section are from the drift analysis as it ran</strong>,
  against the population and the filters of that build &mdash; the accessibility floor was
  <span class="mono">l_green</span>, since replaced by <span class="mono">l_local</span> on
  RNAplfold, and two filters have been added since. They are kept because the conclusion they
  support is about the ORDER of magnitude of the loss, which no later filter can increase: every
  filter added since removes designs, so the 1,037 that would have reached the gating set can only
  have fallen. Rerun <span class="mono">transcript_drift.py</span> for current figures.</p>
  <p class="note"><strong>53.9% of the sweep covers one</strong> &mdash; 31,735 of 58,876 designs
  across 633 of 1,043 trigger pairs. That figure is also badly misleading on its own, which is the
  point of the table:</p>
  <div class="scroll"><table><thead><tr><th>designs covering a corrected base</th><th>count</th>
    </tr></thead><tbody>
    <tr><td>total</td><td>31,735</td></tr>
    <tr><td class="dimv">already failing the ON ceiling</td><td class="dimv">21,169</td></tr>
    <tr><td class="dimv">already failing the accessibility floor <span class="dimv">(l_green,
      the version in force when this was measured)</span></td><td class="dimv">3,615</td></tr>
    <tr><td class="dimv">already failing the engaged-arm floor</td><td class="dimv">1,662</td></tr>
    <tr><td class="dimv">already failing the gating SEP</td><td class="dimv">1,650</td></tr>
    <tr><td class="dimv">already failing something else</td><td class="dimv">2,602</td></tr>
    <tr><td><strong>would have reached the gating set</strong></td>
      <td class="win"><strong>1,037 &mdash; 3.3%</strong></td></tr>
  </tbody></table></div>
  <p class="note">So the real loss is <strong>1,037 designs across 90 trigger pairs</strong>, not
  31,735 &mdash; most of the affected set was already rejected by a threshold computed over a
  region the correction never touched. And the panel gives up nothing measurable:</p>
  <div class="scroll"><table><thead><tr><th>best in the gating set</th><th>with the filter</th>
    <th>without it</th></tr></thead><tbody>
    <tr><td class="mono">A_M ratio</td><td class="win">383.567</td><td>383.567</td></tr>
    <tr><td class="mono">A_M gain</td><td class="win">0.822</td><td>0.822</td></tr>
    <tr><td class="mono">opening SEP</td><td class="win">&minus;14.460</td><td>&minus;14.460</td></tr>
    <tr><td class="mono">Barrier</td><td>19.500</td><td>19.300</td></tr>
  </tbody></table></div>
  <p class="note">The gating set halves, 2,404 to 1,367, and <strong>the top of every distribution
  is identical</strong>; the barrier gives up 0.2&nbsp;kcal/mol, inside the findpath heuristic's own
  error. <strong>A full re-fold is therefore not warranted.</strong> The 1,037 are also exactly
  recoverable without the generator: the trigger-derived domains are reverse complements, so a
  corrected transcript base maps to one determined switch position, and only re-folding is needed.
  The one exception is the scheme's <strong>conflict positions</strong>, where a base is an
  assignment between serving A, serving B and serving the lock &mdash; a correction there can
  change which assignment is best, and those need the generator rather than a patch.</p>

  <h3 style="margin-top:18px">Seven arms, and which of them are the same arm twice</h3>
  <p class="note" style="margin-top:0">Every arm is on the page because the choice between them is
  a judgement for the bench, and an arm that is not shown cannot be compared. But some of them
  measure the same thing, and the cross-correlations over the 1,367 gating designs say which:</p>
  <div class="scroll"><table><thead><tr><th>pair of arms</th><th>Spearman</th><th>reading</th>
    </tr></thead><tbody>
    <tr><td class="mono">IED rbs-linker vs A_M gain</td><td class="bad">&minus;0.750</td>
      <td class="dimv">agree strongly (IED is lower-better) &mdash; nearly one arm</td></tr>
    <tr><td class="mono">IED rbs-linker vs dG arm</td><td>+0.522</td><td class="dimv">related</td></tr>
    <tr><td class="mono">dG arm vs Barrier</td><td>+0.342</td><td class="dimv">partly related</td></tr>
    <tr><td class="mono">Barrier vs A_M ratio</td><td>+0.284</td><td class="dimv">weak</td></tr>
    <tr><td class="mono">IED rbs-linker vs Barrier</td><td class="win">+0.161</td>
      <td class="dimv">nearly independent</td></tr>
    <tr><td class="mono">Barrier vs A_M gain</td><td class="win">&minus;0.113</td>
      <td class="dimv">nearly independent</td></tr>
  </tbody></table></div>
  <p class="note"><strong>So the IED cannot replace the Barrier as a third arm, even though it is
  the better predictor.</strong> It duplicates A_M gain at 0.75 while the Barrier is almost
  orthogonal to it at 0.11 &mdash; swapping them would leave a panel of two arms that agree. Against
  Green's measured switches the IED is far stronger (+0.356 and +0.390 against the Barrier's +0.179
  and +0.280), so the two facts point opposite ways: the Barrier earns its slot by
  <em>disagreeing</em>, not by predicting. Only the bench settles that, which is why both are
  shown rather than one being chosen here.</p>
  <p class="note"><span class="mono">dG rbs-linker</span> is Green's own strongest single parameter
  and is <strong>not</strong> the same number as the IED over that span: he folds the
  RBS-loop-through-linker stretch <em>by itself</em> and reports its MFE, while the IED is that
  region's mean pairing probability <em>inside the whole molecule</em>. On his 168 they are +0.334
  and +0.356. It is computed here as a subsequence, exactly as he did it, and with his sign &mdash;
  less negative is better, a stiff refolded stem in front of the ribosome being what he reports
  correlating with lower dynamic range.</p>

  <h3 style="margin-top:18px">From 390,814 designs to __N_FEASIBLE__</h3>
  <p class="note" style="margin-top:0">Counted from the files, not recalled. Two different
  reductions happen here and conflating them is easy: the first is <em>coverage</em> (how many
  designs a stage reached) and the second is <em>filtering</em> (how many passed).</p>
  <div class="scroll"><table><thead><tr><th>stage</th><th>designs</th><th>what happens</th>
    </tr></thead><tbody>
    <tr><td class="mono">*_folded_*.csv</td><td>390,814</td><td class="dimv">folded: AUG(11), the
      x* lock terms, A_M per tube, d_off</td></tr>
    <tr><td class="mono">obj*.csv</td><td>210,148</td><td class="dimv">reached the energy scorer
      &mdash; the remaining 180,666 were never submitted to it</td></tr>
    <tr><td class="dimv">&minus; stopped at the ON ceiling</td><td class="bad">&minus;169,855</td>
      <td class="dimv">written with <span class="mono">skipped=on_ceiling</span> and no
      <span class="mono">andness</span>. Cheapest-first scoring measures the ON tube first and
      returns before the OFF tubes and the barrier, which is the 5.2&times; speedup</td></tr>
    <tr><td class="dimv">&minus; duplicate switch</td><td class="bad">&minus;17,962</td>
      <td class="dimv">one switch scored under more than one family; the first is kept and
      <span class="mono">andness</span> agrees to six decimals</td></tr>
    <tr><td><strong>joined population</strong></td><td><strong>58,876</strong></td>
      <td class="dimv">folded <em>and</em> fully energy-scored</td></tr>
    <tr><td><strong>feasible</strong></td><td class="win"><strong>__N_FEASIBLE__</strong></td>
      <td class="dimv">passed all eleven thresholds below</td></tr>
    <tr><td><strong>gating</strong></td><td class="win"><strong>__N_GATING__</strong></td>
      <td class="dimv">and opening SEP &le; &minus;2.0</td></tr>
  </tbody></table></div>
  <p class="note"><strong>Nothing feasible was discarded by the early return.</strong> Of the
  153,878 rows carrying <span class="mono">skipped=on_ceiling</span>, <strong>0</strong> have an
  <span class="mono">open_11</span> at or under the 4.0 ceiling; of the remaining
  <span class="mono">andness</span>-less rows, all 21,876 are over the ceiling too. Every design
  dropped for a missing score is one the ON ceiling would have rejected anyway &mdash; checked,
  because "it was going to fail anyway" is exactly the claim that needs a count behind it.</p>

  <h3 style="margin-top:18px">The eleven feasibility thresholds</h3>
  <p class="note" style="margin-top:0">Read out of <span class="mono">objective_panel.feasible</span>
  and <strong>remeasured for this build</strong> &mdash; the previous version of this table said
  nine and carried counts from an older run. The reject column is each filter <em>alone</em> over
  the 60,337 joined rows, so they overlap and do not sum. Note the convention that makes them
  safe: a threshold compares against <span class="mono">None</span> first and an unmeasured value
  is <strong>kept</strong> &mdash; unmeasured is not failed.</p>
  <div class="scroll"><table><thead><tr><th>threshold</th><th>constant</th><th>rejects alone</th>
    <th>what it is</th></tr></thead><tbody>
    <tr><td class="mono">open_11 &le; 4.0</td><td class="mono">ON_CEILING</td><td>39,470 (65.4%)</td>
      <td class="dimv">kcal/mol to open the main stem's arms in the ON tube</td></tr>
    <tr><td class="mono">l_local &ge; 0.3369</td><td class="mono">L_LOCAL_FLOOR</td>
      <td>27,979 (46.4%)</td><td class="dimv">endogenous reachability of the trigger windows, on
      RNAplfold through the engine's own profiler</td></tr>
    <tr><td class="mono">aug_11 &gt; 0.2</td><td class="mono">AUG_FLOOR</td><td>23,067 (38.2%)</td>
      <td class="dimv">AUG unpaired probability in the ON tube</td></tr>
    <tr><td class="mono">lower3 grip</td><td class="mono">GRIP_BREAK_MAX</td><td>11,897 (19.7%)</td>
      <td class="dimv">a forced stem-base level may cost trigger A at most one of the bottom
      three pairs</td></tr>
    <tr><td class="mono">lock01 &ge; 0.20</td><td class="mono">LOCK01_FLOOR</td><td>5,513 (9.1%)</td>
      <td class="dimv">B alone frees x*; the 4-term mean dilutes this away</td></tr>
    <tr><td class="mono">scheme not dead</td><td class="mono">DEAD_SCHEMES</td><td>4,422 (7.3%)</td>
      <td class="dimv">A-anchored and unlocked: 0 of 4,330 ever gated</td></tr>
    <tr><td class="mono">engaged_arm_11 &ge; 0.3</td><td class="mono">ARM_FLOOR</td>
      <td>907 (1.5%)</td><td class="dimv">share of main_pre* paired to trigger A in the ON tube,
      over the whole ensemble</td></tr>
    <tr><td class="mono">not offtarget FIRES</td><td class="dimv">categorical</td><td>569 (0.9%)</td>
      <td class="dimv">opens on a decoy with no real trigger</td></tr>
    <tr><td class="mono">hairpin_worst &ge; 0.3</td><td class="mono">HAIRPIN_FLOOR</td>
      <td>515 (0.9%)</td><td class="dimv">weakest of the four intended duplexes in the OFF tube</td></tr>
    <tr><td class="mono">lock &ge; 0.3</td><td class="mono">LOCK_FLOOR</td><td>444 (0.7%)</td>
      <td class="dimv">geometric mean of the four x* lock terms</td></tr>
    <tr class="win"><td class="mono">engages_stem_mfe &gt; 0</td><td class="mono">STEM_MFE_FLOOR</td>
      <td>178 of 2,446 (7.3%)</td><td class="dimv"><strong>new.</strong> Does trigger A touch the
      ascending arm in the <em>single most probable</em> structure of the ON tube &mdash; the
      structure the figures on this page draw</td></tr>
    <tr><td class="mono">no rare codon</td><td class="mono">RARE_CODONS</td><td class="dimv">upstream</td>
      <td class="dimv">in the first 3 codons after the AUG; applied in the scorer, so it rejects
      nothing here &mdash; those designs never reached this population</td></tr>
  </tbody></table></div>
  <p class="note"><strong>The new threshold's denominator is different, and that matters.</strong>
  <span class="mono">engages_stem_mfe</span> costs one cofold of the ON tube per design, so it is
  measured over the <strong>2,446 designs that already passed everything else</strong>, not over
  all 60,337 &mdash; its 7.3% is not comparable with the percentages above it. Over the gating set
  it rejects <strong>163 of 1,480</strong>, 11.0%.</p>
  <p class="note"><strong>Why it exists when <span class="mono">engaged_arm_11</span> already
  does.</strong> That one sums pair probabilities across the whole ensemble; this reads the MFE. A
  design can pass the first and fail this one, and then its own picture of the ON tube shows a shut
  main hairpin &mdash; which is how this was noticed, from the figures rather than from a column.
  The line is drawn by the histogram and not chosen: over the 2,446, <strong>178 sit at exactly
  0.000</strong>, then only <strong>5</strong> designs in the whole interval (0,&nbsp;0.2), then
  the mass at median 0.556 (sd 0.096, max 1.000). Raising the floor to 0.2 would cost 5 more
  designs; to 0.4, 165 &mdash; a much stronger claim, which this does not make.</p>
  <p class="note"><strong>What it cost, and what it changed.</strong> 1,317 of 1,480 gating designs
  kept, 92 of 96 trigger pairs survive, 94 of 100 cells still hold three or more designs, and the
  best value of every arm is unchanged &mdash; A_M ratio 383.567, A_M gain 0.822, Barrier 19.360,
  IED gain 0.304 &mdash; except <span class="mono">opening SEP</span>, which gives up 0.19 kcal/mol
  (&minus;14.460 to &minus;14.274). It is <em>not</em> cosmetic, though: it moved the panel. Pair
  <span class="mono">645/251/4</span> kept 5 of its 9 designs but lost the ones two arms had
  chosen, so it fell out of the top two and the six are now built on
  <span class="mono">414/361/4</span> and <span class="mono">507/260/4</span>. Afterwards
  <strong>0 of the 37 cards on this page</strong> draw a shut main hairpin in their ON tube, where
  4 did before.</p>
  <p class="note">Four of these <strong>can only fire after a join</strong> &mdash;
  <span class="mono">l_local</span>, <span class="mono">hairpin_worst</span>,
  <span class="mono">engages_stem_mfe</span> and the off-target verdict live in side tables, and a
  build that forgot the join silently kept every design they would have removed.</p>

  <h3 style="margin-top:18px">How <span class="mono">combined</span> should pick, measured</h3>
  <p class="note" style="margin-top:0">The current rule is a weighted mean of two percentiles, which
  lets a weak A_M ratio be bought back by a strong barrier. The alternative is an
  <strong>&epsilon;-constraint</strong>: inside each cell keep only designs holding at least
  &epsilon; of the cell's best A_M ratio, then take the lowest barrier among those. Both rules run
  over all 292 cells below. &ldquo;A_M, % of cell best&rdquo; is the column that matters &mdash; it
  is how much of the achievable A_M ratio each rule gives away.</p>
  <div class="scroll"><table><thead><tr><th>rule</th><th>A_M median</th><th>A_M mean</th>
    <th>A_M, % of cell best</th><th>Barrier mean</th><th>agrees with the A_M pick</th>
    </tr></thead><tbody>
    <tr><td>A_M ratio alone</td><td>5.2</td><td>15.8</td><td class="win">100%</td><td>29.6</td>
      <td>100%</td></tr>
    <tr><td><strong>combined</strong>, weighted mean &mdash; as it is now</td><td>4.9</td>
      <td class="bad">7.3</td><td class="bad">85%</td><td>28.0</td><td>57%</td></tr>
    <tr><td>&epsilon;-constraint, &epsilon;=0.70</td><td>5.0</td><td>14.8</td><td>93%</td>
      <td>29.1</td><td>37%</td></tr>
    <tr><td><strong>&epsilon;-constraint, &epsilon;=0.80</strong></td><td>5.0</td>
      <td class="win">15.2</td><td class="win">95%</td><td>29.2</td><td>41%</td></tr>
    <tr><td>Barrier alone</td><td>3.8</td><td class="bad">4.5</td><td class="bad">66%</td>
      <td class="win">27.3</td><td>17%</td></tr>
  </tbody></table></div>
  <p class="note"><strong>The weighted mean is a bad trade and the &epsilon;-constraint is a good
  one.</strong> The weighted mean gives up more than half the achievable A_M ratio &mdash; mean
  15.8 down to 7.3 &mdash; to buy 1.6 kcal/mol of barrier. At &epsilon;=0.80 the constraint keeps
  15.2, which is 96% of what the A_M arm itself achieves, and still gains 0.38 kcal/mol on average
  (max 12.2) while reordering 154 of the 292 cells. The cause is the heavy tail: a percentile mean
  reads an A_M ratio of 300 and one of 10 as 7 percentile points apart, while in ratio space they
  are 30&times; apart. The constraint works in the space the quantity lives in.</p>
  <p class="note">The honest limit: 0.38 kcal/mol mean is <em>small</em>, and the barrier is a
  findpath upper bound. So the &epsilon;-constraint is better than the weighted mean mainly because
  it <strong>costs almost nothing</strong>, not because the barrier it buys is large. &epsilon;=0.80
  leaves a median of 3 designs to choose among and only 58 of 292 cells with a single option, so it
  still has something to order; &epsilon;=0.90 drops that to 90 cells with no choice.</p>

  <h3 style="margin-top:18px">What the two scales actually span</h3>
  <p class="note" style="margin-top:0">Measured over the <strong>3,741</strong> designs that gate,
  through the panel's own <span class="mono">load &rarr; feasible &rarr; gating</span> path. Both
  questions below &mdash; is an A_M ratio near 50 poor, is a 5&nbsp;kcal/mol barrier spread
  meaningful &mdash; were being answered from the twelve rows on this page, which is the smallest
  and least representative sample available.</p>
  <div class="scroll"><table><thead><tr><th></th><th>n</th><th>min</th><th>p50</th><th>p90</th>
    <th>p99</th><th>max</th><th>mean</th><th>sd</th></tr></thead><tbody>
    <tr><td><strong>A_M ratio</strong></td><td>3,741</td><td>0.5</td><td>4.5</td><td>9.5</td>
      <td>78.4</td><td class="win">383.6</td><td>7.5</td><td>16.7</td></tr>
    <tr><td><strong>Barrier</strong> kcal/mol</td><td>3,741</td><td class="win">19.3</td>
      <td>28.8</td><td>33.8</td><td>37.3</td><td>39.9</td><td>28.7</td><td>3.6</td></tr>
    <tr><td class="dimv">best A_M ratio per cell</td><td>292</td><td>1.2</td><td>5.2</td>
      <td>49.8</td><td>112.6</td><td>383.6</td><td>15.8</td><td>35.5</td></tr>
  </tbody></table></div>

  <p class="note"><strong>The A_M ratio near 50 is not poor &mdash; it is the 98th percentile.</strong>
  The distribution is heavy-tailed: the median gating design sits at <span class="mono">4.5</span>
  and p90 is only <span class="mono">9.5</span>, so the panel's <span class="mono">47.7</span> and
  <span class="mono">315.6</span> are at roughly the 98th and above the 99.9th. The rows reading
  1&ndash;9 are the <em>Barrier</em> and <em>combined</em> picks, which are ranked on something
  else; they are not the A_M arm underperforming. Inside each of the four panel cells the A_M arm
  took <strong>exactly the cell maximum</strong> &mdash; 47.7 of 47.7, 9.0 of 9.0, 9.8 of 9.8,
  315.6 of 315.6 &mdash; and two of those cells cap near 9, so within these pairs and geometries
  this <em>is</em> the ceiling. The best cell anywhere in the sweep is <span class="mono">383.6</span>
  (pair 507/260/4); this panel already holds the second best.</p>

  <p class="note"><strong>The Barrier's percentiles are not inverted.</strong> Lower is better, so
  the percentile is <span class="mono">100 &minus; (share strictly below)</span>: a 24.6 design
  earns the <em>84th</em> and a 27.4 design the <em>58th</em>. The better design gets the higher
  number, which is the intended direction on all four arms.</p>

  <p class="note"><strong>What the Barrier measures, and the case against it as a standalone
  arm.</strong> It is the height of the folding saddle from
  <span class="mono">findpath</span> &mdash; the activation energy of the OFF&rarr;ON refold, an
  <em>upper bound</em> along a heuristic direct path rather than the true minimum-barrier one. The
  whole ranked population spans <strong>20.6</strong> kcal/mol and 80% of it fits inside
  <strong>9.7</strong>, so a ~5 kcal/mol within-cell range is about a quarter of the entire scale,
  not a narrow slice of a wide one. That also means the percentile moves fast for small energy
  differences, and those differences are bounded by the findpath heuristic, so the ordering inside
  a cell should be read as approximate.</p>
  <p class="note"><strong>Recommendation, for a decision rather than a silent change:</strong> keep
  the Barrier as a <em>term inside</em> <span class="mono">combined</span>, where it measurably
  lifts the A_M ratio (+0.306 alone &rarr; +0.345 with it on Green's 168), and <strong>retire it as
  a standalone arm</strong>. Its standalone picks are the designs that have failed mechanistic
  checks by three independent routes: <span class="mono">hairpin_worst</span> at 0.000 and 0.003
  (the main stem never forms), <span class="mono">main_pre*</span> engaged by A at or below 0.047
  in all four (A takes the lock and leaves the stem shut), and a near-mean global barrier despite
  being the within-cell best. All three are consistent with one cause: a design with no stem to
  open has little to activate, so minimising the activation energy selects for it. That is a real
  argument against the arm, not against the term.</p>

  <h3 style="margin-top:18px">A correction, because it changed the conclusion's strength</h3>
  <p class="note" style="margin-top:0">An earlier, ad-hoc version of this measurement built combined with SEP
  and combined from <strong>two</strong> terms instead of three &mdash; it dropped
  <span class="mono">access</span> &mdash; and put combined with SEP at <strong>+0.074</strong>, which supported
  a much stronger claim ("the SEP version is nothing") than the data does. The third term moves combined with SEP by
  <strong>+0.139</strong> and reorders it above the barrier. The conclusions that survived are
  the ones stated above; the measurement now lives in a script that builds the aggregate exactly
  the way the panel builds it, rather than in a one-off.</p>

  <h3 style="margin-top:18px">Accessibility selects trigger pairs; it does not rank designs</h3>
  <p class="note" style="margin-top:0">Only the combination carried an
  <span class="mono">access</span> term, so the three objectives were not comparable. The fix was
  not to add it to the other two &mdash; it was to notice what the term can and cannot do.
  <span class="mono">access</span> is the cost of opening the two trigger windows on the
  endogenous transcript: a property of the <strong>trigger pair</strong>, not of the design. On
  this sweep it is <strong>exactly constant</strong> inside all 324 (pair, geometry) cells, spread
  <span class="mono">0.000000&nbsp;kcal/mol</span>.</p>
  <p class="note">A constant inside a cell is a constant offset in a percentile mean, so
  <span class="mono">(the A_M ratio%&nbsp;+&nbsp;Bar%&nbsp;+&nbsp;acc%)/3</span> and
  <span class="mono">(the A_M ratio%&nbsp;+&nbsp;Bar%)/2</span> rank the designs in a cell
  <strong>identically</strong>. Checked directly: of the 14 cells where the two picks differ,
  <strong>0</strong> are a genuine reordering and all 14 are ties broken differently. The term
  never ranked a design. What it did rank was trigger <em>pairs</em> &mdash; silently, inside a
  number presented as design quality, and in only one of the three objectives.</p>
  <p class="note">So it now selects pairs explicitly: among the pairs carrying enough gating
  designs in both geometries, <strong>the most accessible one wins its slot</strong>. A declared
  ranking rather than a threshold, because nothing calibrates a cutoff on transcript opening cost
  and an undeclared one is an invisible filter.</p>
  <p class="note"><strong>What it costs, measured on both Green libraries.</strong> Percentile
  aggregates against measured ON/OFF:</p>
  <div class="scroll" style="margin-top:8px"><table><thead><tr><th>aggregate</th>
    <th>Green 168</th><th>Green 13</th></tr></thead><tbody>
    <tr><td>A_M ratio alone</td><td>+0.306</td><td class="win">+0.698</td></tr>
    <tr><td>Barrier alone</td><td>+0.179</td><td>+0.280</td></tr>
    <tr><td><strong>A_M ratio + Barrier</strong> &mdash; combined, as it is now</td><td>+0.345</td>
      <td>+0.644</td></tr>
    <tr><td>A_M ratio + Barrier + access &mdash; combined, as it was</td><td class="win">+0.366</td>
      <td>+0.591</td></tr>
  </tbody></table></div>
  <p class="note">The third term is worth <strong>+0.021</strong> on the 168 and
  <strong>costs 0.053</strong> on the 13, where the A_M ratio alone beats every aggregate. And Green's third
  term is not even the same quantity: there <span class="mono">access</span> is proxied by
  <span class="mono">dG_open(ON)</span>, a <strong>design</strong> property, so his data never
  validated a pair-level accessibility term at all. A term worth ±0.02, of disputed sign, measured
  through a proxy of a different kind, that cannot reorder a single design &mdash; it belongs where
  it does real work.</p>

  <h3 style="margin-top:18px">The finished sweep, and what it changed</h3>
  <p class="note" style="margin-top:0">The run is complete &mdash; <strong>100% coverage of every
  eligible design in all five families</strong>, 159,100 of 159,100. The apparent 52&ndash;58% in
  the progress table was an accounting artefact, twice over: the denominator counted designs the
  free rare-codon screen rejects before any folding (51.6% of the closure-filtered set, so a
  finished run reads ~54%), and the numerator counted rows scored in earlier passes under looser
  filters, which is how <span class="mono">p3</span> reached 125%.</p>
  <div class="scroll" style="margin-top:10px"><table><thead><tr><th></th>
    <th>mid-run (this page, v8)</th><th>finished</th></tr></thead><tbody>
    <tr><td>designs scored</td><td>45,023</td><td class="win">58,876</td></tr>
    <tr><td>feasible</td><td>3,081</td><td class="win">16,284</td></tr>
    <tr><td>gating</td><td>1,523</td><td class="win">8,166</td></tr>
    <tr><td>trigger pairs controlled in both geometries</td><td class="bad">5</td>
      <td class="win">179</td></tr>
    <tr><td>the long slot</td><td class="dimv">len_x 7 &mdash; len_x 6 had 0 usable pairs</td>
      <td class="win">len_x 6</td></tr>
  </tbody></table></div>
  <p class="note">So both panel pairs changed. <span class="mono">len_x&nbsp;6</span> was absent
  from v7 because only 4,034 of its designs had been scored, not because it failed &mdash; and
  with the sweep finished it holds the long slot outright.</p>

  <h3 style="margin-top:18px">Accessibility no longer picks the pairs &mdash; it predicts nothing</h3>
  <p class="note" style="margin-top:0">Accessibility used to select the trigger pairs: most
  accessible wins its slot. Over the finished sweep's <strong>179 controlled pairs</strong>, a
  pair's accessibility does not predict the quality of its best design, on either definition
  &mdash; signed so positive would mean "more accessible pairs carry better gates":</p>
  <div class="scroll" style="margin-top:10px"><table><thead><tr><th>definition</th>
    <th>combined</th><th>A_M ratio</th><th>opening SEP</th></tr></thead><tbody>
    <tr><td><span class="mono">l_green</span> &mdash; Green 2014 Eq. 4</td>
      <td class="bad">&minus;0.102</td><td>+0.132</td><td>+0.005</td></tr>
    <tr><td><span class="mono">open_penalty</span> energy &mdash; ours</td>
      <td>+0.064</td><td class="bad">&minus;0.038</td><td>+0.056</td></tr>
  </tbody></table></div>
  <p class="note">Both are noise, and the two definitions agree with each other only at
  <span class="mono">&rho;&nbsp;=&nbsp;&minus;0.200</span> &mdash; they measure different things
  and neither predicts this one. <strong>The cost was concrete:</strong> the most accessible pair
  carries a best <span class="mono">combined</span> of <strong>62.7</strong> against the best
  pair's <strong>95.4</strong>, and that best pair ranks <strong>96 of 179</strong> on
  accessibility. So the rule was discarding good gates for a property that does not predict them.
  Pairs are now ranked by best <span class="mono">combined</span>, and accessibility is reported
  per row. No threshold is invented &mdash; a genuinely unreachable window would need a hard
  filter, and none exists yet.</p>

  <h3 style="margin-top:18px">The one-pair panel exists now</h3>
  <p class="note" style="margin-top:0">The layout you would want &mdash; one trigger pair showing
  every objective in each geometry &mdash; <strong>was 0 of 26 pairs</strong> when 13% of the
  sweep was scored. On the finished sweep the three objectives split three ways in
  <strong>173 of 460</strong> gating cells, and <strong>36 pairs</strong> have <em>both</em>
  geometries splitting all three ways. So the panel is now exactly that, twice over: 2 pairs
  &times; 2 geometries &times; 3 objectives = <strong>12 rows, every cell a genuine three-way
  comparison</strong>, with the second pair a long overlap so the length is still represented.</p>

  <h3 style="margin-top:18px">Two trigger pairs, one of them a long overlap</h3>
  <p class="note" style="margin-top:0"><strong>Two and not six.</strong> A previous version gave
  every <span class="mono">len_x</span> its own slot. That covered the overlap length but spread
  the panel over <strong>six transcript sites</strong>, so almost every row differed from almost
  every other in the trigger pair <em>as well as</em> in the objective &mdash; a bench result would
  have pointed at two causes at once. Two slots now: one long overlap, one short. Inside a slot a
  <strong>properly controlled</strong> pair beats a more accessible but thinner one, because a
  cell holding a single design cannot split the objectives at all.</p>
  <p class="note">Every version before that sat on <span class="mono">len_x&nbsp;=&nbsp;4</span>
  throughout, which confounds the objective comparison with the overlap length &mdash; which is
  why one slot is reserved for a long overlap. What the unfinished sweep supports:</p>
  <div class="scroll" style="margin-top:8px"><table><thead><tr><th>len_x</th><th>scored</th>
    <th>feasible</th><th>gating</th><th>pairs controlled</th><th>best SEP / combined</th>
    </tr></thead><tbody>
    <tr><td class="mono">4</td><td>38,059</td><td>11,096</td><td>5,353</td>
      <td class="win">122</td><td class="dimv">&minus;15.03 / 95.4</td></tr>
    <tr><td class="mono">5</td><td>13,275</td><td>3,670</td><td>2,010</td><td class="win">44</td>
      <td class="dimv">&minus;15.90 / 93.7</td></tr>
    <tr><td class="mono">6</td><td>5,474</td><td>766</td><td>382</td><td>8</td>
      <td class="dimv">&minus;9.33 / 90.6</td></tr>
    <tr><td class="mono">7</td><td>2,054</td><td>752</td><td>421</td><td>5</td>
      <td class="dimv">&minus;11.87 / 79.2</td></tr>
  </tbody></table></div>
  <p class="note">Every length is now pair-controllable, <span class="mono">len_x&nbsp;6</span>
  included &mdash; it had 0 usable pairs at 13% of the sweep and has 8 now. The long slot is
  <span class="mono">len_x&nbsp;7</span> because it carries the best-quality long pair, not because
  6 is unavailable. Note <span class="mono">len_x&nbsp;8</span>: 14 designs scored, 0 feasible.</p>
  <p class="note"><strong>Why nine rows and not twelve.</strong> Where a cell does not split
  three ways the objectives agreed, and an agreement is recorded rather than padded out with a
  design nothing chose. Both cells are now properly controlled &mdash; the single-design cells
  that capped v7 at seven rows are gone.</p>

  <div class="two" style="margin-top:14px">
    <div>
      <h3>What the mid-run panel could not do</h3>
      <p class="note" style="margin-top:0">At 13% of the sweep, of the 26 pairs with enough
      feasible designs in both geometries, <strong>0</strong> split even four ways across five
      objectives and the best-distinctness pair did not gate at all. That constraint is gone: see
      above, 36 pairs now give a complete three-objective panel in both geometries.</p>
      <p class="note">So the panel is <strong>2 pairs &times; 2 geometries &times; 3
      objectives</strong> &mdash; 12 rows, 12 distinct constructs. Where a cell does not split, the
      row records <em>which objectives agreed</em> rather than inventing a rival, and every card
      names what its own comparison holds fixed.</p>
    </div>
    <div>
      <h3>The two geometries</h3>
      <dl>
        <div><dt style="color:var(--teal)">naive 18nt</dt><dd>161-nt switch, secondary arm
          <span class="mono">k2* = 18 &minus; len_x</span>. The default build.</dd></div>
        <div><dt style="color:var(--open)">Kim 20/17/AUA</dt><dd>165-nt switch: Kim 2019's
          20-nt arm, 17-nt invasion, AUA cap.</dd></div>
      </dl>
      <p class="note">Holding the pair across both took the right key. On
      <span class="mono">(a_start, b_start)</span> <strong>0 of 2,078</strong> pairs are shared,
      and that was reported here as structurally impossible. It is not:
      <span class="mono">b_end</span> is <em>identical</em> in both and
      <span class="mono">b_start</span> differs by 1&nbsp;nt only because trigger B's window is
      50&nbsp;nt in the naive build and 49 in Kim's. Same location, different length. On
      <span class="mono">(a_start, b_end, len_x)</span>, <strong>1,020 of 1,042</strong> are
      shared.</p>
    </div>
  </div>

  <h3 style="margin-top:18px">Rare codons are excluded, not flagged</h3>
  <p class="note" style="margin-top:0">A rare <em>E.&nbsp;coli</em> codon in the first three
  codons after the AUG can stall the ribosome as translation starts, so such a construct can fail
  for a reason that has nothing to do with its gate &mdash; and the result would be
  uninterpretable. They must be <strong>excluded</strong> rather than reported because they are
  <strong>enriched among the designs the model likes</strong>: 48.4% of gating designs carry one
  against 31.4% of non-gating ones. AGG and CGG are G-rich, so they strengthen pairing &mdash;
  the folding score rewards what the cell punishes. That is a confound, not a coincidence.</p>
</div>

"""
head = head.replace(OLD, NEW, 1)

# The heading used to be hard-coded to a count that then went stale on every rebuild -- "The
# sixteen" while twenty rows rendered. Named rather than counted: the count is already on the page
# in the filter bar, live and correct, and a second copy baked into HTML can only disagree with it.
head = swap(head, "<h2>The designs</h2>", "<h2>The designs, one card each</h2>", "panel heading")
head = swap(
    head, '<span class="lbl">objective</span>', '<span class="lbl">chosen by</span>', "filter label"
)

# The card-reading and closing panels still describe four objectives and 16 rows.
head = re.sub(
    r"Keeping all four gave 4 distinct designs out of 8 rows; these two give 16 of 16\.",
    "",
    head,
    count=1,
)

# The exporter goes AFTER the viewer, because it reads `window.SHOWN`, which `render` sets.
# The two funnel counts come from the data file, not from the prose. Written out by hand they
# went stale on every filter change -- the page said 7,568 feasible and 3,741 gating while the
# build beside it had 2,268 and 1,317.
head = head.replace("__N_FEASIBLE__", f"{data['n_population']:,}")
head = head.replace("__N_JOINED__", f"{data.get('n_joined') or 0:,}")
head = head.replace("__N_GATING__", f"{data.get('n_gating') or 0:,}")

out = (
    head
    + script.replace("/*__DATA__*/{}", json.dumps(data, separators=(",", ":")))
    + (HERE / "export_xlsx.html").read_text(encoding="utf-8")
)
(HERE / "panel.html").write_text(out, encoding="utf-8")
print(
    f"built panel.html, {len(out):,} bytes; {len(data['cands'])} rows, "
    f"{len({c['seq'] for c in data['cands']})} distinct, "
    f"pairs {sorted({c['pair'] for c in data['cands']})}"
)
