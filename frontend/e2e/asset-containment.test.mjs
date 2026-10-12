/** Runs standalone and as part of the RNA viewer browser harness. */
import assert from "node:assert/strict";
import { posix, win32 } from "node:path";
import { isContainedAsset } from "./asset-containment.mjs";

for (const [paths, root] of [[posix, "/repo/static/app"], [win32, "C:\\repo\\static\\app"]]) {
  for (const name of ["assets/index.js", "assets/index.css", "assets/nested/icon.svg", "assets/..safe.js"]) {
    assert(isContainedAsset(root, paths.resolve(root, name), paths), `Accept ${paths.sep}: ${name}`);
  }
  for (const name of ["assets", "assets/..", "assets/../index.html", "assets/../../secret",
    "assets/../assets-sibling/secret", "assets/nested/../../../secret"]) {
    assert(!isContainedAsset(root, paths.resolve(root, name), paths), `Reject ${paths.sep}: ${name}`);
  }
}
const windowsRoot = "C:\\repo\\static\\app";
for (const asset of ["D:\\repo\\static\\app\\assets\\index.js", "\\\\server\\share\\index.js",
  win32.resolve(windowsRoot, "assets/..\\..\\secret"),
  win32.resolve(windowsRoot, "assets\\..\\assets-sibling\\secret")]) {
  assert(!isContainedAsset(windowsRoot, asset, win32), `Reject Windows escape: ${asset}`);
}
assert(isContainedAsset(windowsRoot, "c:\\REPO\\static\\app\\assets\\index.js", win32));
console.log("Asset containment: POSIX and Windows assets accepted; traversal, siblings, drives and UNC escapes rejected.");
