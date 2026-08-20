import path from 'node:path'

export const REPO_ROOT = path.resolve(process.cwd(), '..')
export const IMAGES = {
  original: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_original.png'),
  enhanced: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_enhanced.png'),
  hazard: path.join(REPO_ROOT, 'datasets/real/derived/lroc_nearside_synthetic_hazard.png'),
  psrShaded: path.join(REPO_ROOT, 'datasets/real/derived/psr_site001_shaded.png'),
  psrHazard: path.join(REPO_ROOT, 'datasets/real/derived/psr_site001_synth_hazard.png'),
  noise: path.join(process.cwd(), 'tests', 'fixtures', 'noise.png'),
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
