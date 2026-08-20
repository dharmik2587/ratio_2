import path from 'node:path'
import zlib from 'node:zlib'

export const REPO_ROOT = path.resolve(process.cwd(), '..')
export const IMAGES = {
  original: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_original.png'),
  enhanced: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_enhanced.png'),
  hazard: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_synthetic_hazard.png'),
  psrShaded: path.join(REPO_ROOT, 'datasets/real/derived/psr_site001_shaded.png'),
  psrHazard: path.join(REPO_ROOT, 'datasets/real/derived/psr_site001_synth_hazard.png'),
}

// ---------------------------------------------------------------- noise PNG
// Deterministic random-noise PNG generated in-process (no fixture files, no
// dependencies), so the suite is self-contained in a fresh clone. The noise is
// intentionally unrelated to any lunar scene: it must fail comparability.

const CRC_TABLE = (() => {
  const table = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1
    table[n] = c >>> 0
  }
  return table
})()

function crc32(buf) {
  let c = 0xffffffff
  for (let i = 0; i < buf.length; i++) c = CRC_TABLE[(c ^ buf[i]) & 0xff] ^ (c >>> 8)
  return (c ^ 0xffffffff) >>> 0
}

function chunk(type, data) {
  const out = Buffer.alloc(8 + data.length + 4)
  out.writeUInt32BE(data.length, 0)
  out.write(type, 4, 'ascii')
  data.copy(out, 8)
  out.writeUInt32BE(crc32(out.subarray(4, 8 + data.length)), 8 + data.length)
  return out
}

export function noisePng(size = 256, seed = 42) {
  // xorshift32 for determinism
  let state = seed >>> 0
  const next = () => {
    state ^= state << 13; state >>>= 0
    state ^= state >>> 17
    state ^= state << 5; state >>>= 0
    return state
  }
  const raw = Buffer.alloc(size * (size * 3 + 1))
  let o = 0
  for (let y = 0; y < size; y++) {
    raw[o++] = 0 // filter: none
    for (let x = 0; x < size * 3; x++) raw[o++] = next() & 0xff
  }
  const ihdr = Buffer.alloc(13)
  ihdr.writeUInt32BE(size, 0)
  ihdr.writeUInt32BE(size, 4)
  ihdr[8] = 8   // bit depth
  ihdr[9] = 2   // color type: truecolor
  ihdr[10] = 0; ihdr[11] = 0; ihdr[12] = 0
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk('IHDR', ihdr),
    chunk('IDAT', zlib.deflateSync(raw, { level: 9 })),
    chunk('IEND', Buffer.alloc(0)),
  ])
}

export function noiseFile() {
  return { name: 'noise.png', mimeType: 'image/png', buffer: noisePng() }
}

// NOTE: each FileDrop card replaces its <input> with a preview once a file is
// set, so inputs must be resolved per-card, not by global index.
export async function uploadPair(page, original = IMAGES.original, enhanced = IMAGES.hazard) {
  const cardInput = index => page.locator('.file-card').nth(index).locator('input[type="file"]')
  await cardInput(0).setInputFiles(original)
  await cardInput(1).setInputFiles(enhanced)
  await page.getByRole('button', { name: /VERIFY IMAGE PAIR/ }).click()
  await page.getByText('Visual evidence workspace').waitFor()
}
