# cernal-rnaviz drawing integration

Source: https://gitlab.igem.org/2026/software/tau-israel/rna-vizualizer
Pinned commit: `cfc0d0811e0a1a02027e483195d77b59ce0b7f06`
Copyright 2026 iGEM TAU 2026 Team, Tel Aviv University. Apache-2.0.
The upstream LICENSE and NOTICE are included unchanged in this directory.

`drawing.tsx` adapts the single-strand renderer in
`src/cernal_rnaviz/web/js/render/{single,common}.js`, the bounding-box and
outward-vector helpers in `src/cernal_rnaviz/web/js/utils.js`, and
constants/styles from `src/cernal_rnaviz/web/js/constants.js` and
`src/cernal_rnaviz/web/css/{tokens,structure-svg}.css`.

Changes: typed React elements replace HTML interpolation and global DOM/state;
rotation, selection and zoom are component-local; known gate regions are passed
as index ranges; SVG title/description and keyboard selection are accessible.
The app reuses the upstream canvas fit-to-viewport sizing so large structures
remain inside the CERNAL candidate panel until users zoom in.
The palette follows upstream CSS (rather than the differing README legend).

The viewer draws the stored structure using the upstream node/link format. It
does not call the upstream folding API, mutate sequences, recompute energies,
load external fonts, use browser storage or transmit sequence data to another
service. Backend geometry uses the existing installed ViennaRNA dependency and
the licensed cernal-rnaviz layout conversion, separately attributed there.

No upstream server, private repository history, configuration or documentation
is redistributed. Updates should be reviewed against the pinned source, with
rendering, data-validation and navigation regression tests.
