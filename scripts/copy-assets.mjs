// Copies non-TypeScript build assets (the bundled ONNX model + its license
// notice) into dist/ after `tsc` compiles the source. tsc only emits .js
// from .ts, so this is a required, separate step -- not optional polish.
import { cp, mkdir } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, '..');
const srcModels = join(root, 'src', 'score', 'models');
const distModels = join(root, 'dist', 'score', 'models');

await mkdir(distModels, { recursive: true });
await cp(srcModels, distModels, { recursive: true });
console.log(`Copied ${srcModels} -> ${distModels}`);
