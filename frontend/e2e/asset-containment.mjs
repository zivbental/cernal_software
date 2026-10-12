import path from "node:path";

/** Lexical containment for fixture assets, using native path separators. */
export function isContainedAsset(root, asset, paths = path) {
  const relative = paths.relative(paths.resolve(root, "assets"), asset);
  return relative !== "" && relative !== ".." &&
    !relative.startsWith(`..${paths.sep}`) && !paths.isAbsolute(relative);
}
