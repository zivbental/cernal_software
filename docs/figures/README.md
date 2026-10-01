# CERNAL technical figures

This directory contains publication-ready, deterministic SVG diagrams for the CERNAL software wiki.

## Figure system

- All canvases are 1600 px wide and use the same spacing, type scale, palette, node shapes, arrow markers, and caption treatment.
- SVG files are self-contained: no external fonts, images, scripts, stylesheets, or network resources.
- Every SVG includes an accessible `<title>` and `<desc>`, semantic group IDs, and text labels in addition to color.
- The palette uses dark blue for product/platform flow, teal for implemented scientific computation, amber for configuration-dependent boundaries, violet for models/dependencies, and neutral gray for planned or absent capability.
- Status is never encoded by color alone: the maturity matrix uses explicit column headings and cell text.
- Source order, coordinates, and IDs are stable so the files produce deterministic diffs.

## Maintainable source

The SVG files are directly editable XML. The `source/` directory preserves Mermaid descriptions of each figure's logical topology. For the three diagrams that originally appeared as Mermaid blocks in `igem-software-wiki.md`, the `.mmd` files preserve the original source exactly.

When facts change, update the wiki text/table, the corresponding `.mmd` file, and the SVG together. Do not add claims to a figure that are not supported by the adjacent wiki section.
