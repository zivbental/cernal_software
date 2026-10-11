# cernal-rnaviz drawing integration

Source: https://github.com/talberez/cernal-rnaviz
Pinned commit: `aa112e17a76941233987bb4287c2c66511c40d13`
Copyright 2026 iGEM TAU 2026 Team, Tel Aviv University. Apache-2.0.
The upstream LICENSE and NOTICE are included unchanged in this directory.

`drawing.tsx` adapts the single-strand renderer in
`src/cernal_rnaviz/web/js/render/{single,common}.js`, the bounding-box and
outward-vector helpers in `web/js/utils.js`, and constants/styles from
`web/js/constants.js` and `web/css/{tokens,structure-svg}.css`.

Changes: typed React elements replace HTML interpolation and global DOM/state;
rotation, selection and zoom are component-local; known gate regions are passed
as index ranges; SVG title/description and keyboard selection are accessible.
The palette follows upstream CSS (rather than the differing README legend).

The viewer draws the stored structure using the upstream node/link format. It
does not call the upstream folding API, mutate sequences, recompute energies,
load external fonts, use browser storage or transmit sequence data to another
service. Backend geometry uses the existing installed ViennaRNA dependency and
the licensed cernal-rnaviz layout conversion, separately attributed there.

No upstream server, private repository history, configuration or documentation
is redistributed. Updates should be reviewed against the pinned source, with
rendering, data-validation and navigation regression tests.
