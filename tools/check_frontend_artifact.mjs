/** Keep the shared SPA artifact far below the coordinator's rejected data archive. */
import assert from 'node:assert/strict';
import { lstat, readdir, stat } from 'node:fs/promises';
import { resolve } from 'node:path';

const root = resolve(import.meta.dirname, '../src/static/app');
const rootInfo = await lstat(root);
assert(rootInfo.isDirectory() && !rootInfo.isSymbolicLink(), 'Artifact root must be a real directory');
assert((await stat(resolve(root, 'index.html'))).isFile(), 'Missing built SPA');
let bytes = 0;
let files = 0;
async function measure(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    assert(!entry.isSymbolicLink(), `Unexpected artifact symlink: ${path}`);
    if (entry.isDirectory()) await measure(path);
    else {
      assert(entry.isFile(), `Unexpected artifact entry: ${path}`);
      bytes += (await stat(path)).size;
      files += 1;
    }
  }
}
await measure(root);
assert(bytes < 8 * 1024 * 1024, `SPA artifact is ${bytes} bytes; must stay below 8 MiB`);
console.log(`SPA artifact: ${files} files, ${bytes} uncompressed bytes (limit: 8 MiB).`);
