// Patches gaussian-splat-renderer-for-lam@0.0.8 (runs on npm postinstall).
// Bug: on iOS < 16.4 it picks the NON-shared sorter WASM module but always hands the worker SHARED
// memory, so WebAssembly.instantiate fails with a LinkError and the avatar never appears.
// Fix: tell the worker which kind of memory the chosen module expects.
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import path from 'node:path'

const require = createRequire(import.meta.url)
const file = path.join(path.dirname(require.resolve('gaussian-splat-renderer-for-lam/package.json')), 'build/gaussian-splat-renderer-for-lam.module.js')
let src = readFileSync(file, 'utf8')
const MARK = '/* bwithu-patched */'
if (src.includes(MARK)) process.exit(0)

const initAnchor = "            // Super hacky\n            'Constants': {"
const memoryAnchor = '                    memory: new WebAssembly.Memory({\n                        initial: totalPagesRequired,\n                        maximum: totalPagesRequired,\n                        shared: true,'
if (!src.includes(initAnchor) || !src.includes(memoryAnchor)) {
  console.error('[patch-lam-renderer] anchors not found; renderer version changed?')
  process.exit(1)
}
src = src.replace(initAnchor, `            ${MARK} 'sharedWasmMemory': sourceWasm !== SorterWasmNoSIMDNonShared && sourceWasm !== SorterWasmNonShared,\n${initAnchor}`)
src = src.replace(memoryAnchor, memoryAnchor.replace('shared: true,', 'shared: e.data.init.sharedWasmMemory !== false,'))
writeFileSync(file, src)
console.log('[patch-lam-renderer] patched', path.basename(file))
