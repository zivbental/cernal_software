# Superseded: these barriers are not barriers

Every `b_10` in this folder is **`E(end) − E(start)`**: the energy difference between
the two end states of the path, with no path in it. It is not an activation barrier and
it should not be read as one.

The call that produced it was
`path_findpath_saddle(start, end, CEILING)`. Two things were wrong with that:

- the third argument is the search **width**, not a ceiling, so `CEILING = 20_000` went
  in as the width and the `raw >= CEILING` guard compared an energy in dekacal/mol
  against a width — it never rejected anything it was meant to;
- the value returned was not the saddle. On every design rebuilt it came back exactly
  equal to the energy of the end structure. Measured at search widths 10, 100 and
  20,000, which all agree with each other and disagree with the path.

That is why **11% of the values here are negative**, which a maximum over a path
containing its own start cannot be.

## What replaced it

`docs/assets/barrier/` holds the same designs measured from the path itself — the
highest energy the refolding path actually reaches, above where it started. Nothing
there is negative, and a path from a structure to itself is exactly zero.

| | superseded | corrected |
|---|---|---|
| range, kcal/mol | −1.70 … +5.50 | +4.50 … +25.20 |
| median | +1.50 | +10.60 |
| negative | 11.8% | 0 |
| ρ with the equilibrium leak | −0.035 | +0.528 |

## Why it is kept

`tools/barrier_compare.py` joins the two runs design by design, which is how the
correction was checked rather than asserted. Delete this folder only when that
comparison is no longer wanted.

**Nothing published should cite these numbers.** The model page was rebuilt on the
corrected run; see §7.6.
