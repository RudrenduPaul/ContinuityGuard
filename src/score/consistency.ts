/**
 * CG02 -- character-consistency scoring.
 *
 * Computes a per-shot visual embedding and flags cross-shot pairs (claiming
 * to be the same named character) whose cosine similarity falls below a
 * threshold derived from this repo's own fixture run (see
 * src/score/testdata/ and CHANGELOG.md -- never an invented number).
 *
 * IMPORTANT, stated plainly and repeated in the CLI output, the JSON
 * `reason` field, and the README: this technique is best-validated on
 * photorealistic/live-action content. Its accuracy on stylized or
 * anime-adjacent character designs -- the dominant visual style in the
 * short-drama category this tool targets -- is UNVERIFIED. Treat a flag on
 * stylized footage as "worth a second look," never as a confirmed defect.
 *
 * Runtime note: the original design called for `onnxruntime-node` +
 * a pretrained ONNX embedding model, flagging a known risk that a prior,
 * unrelated prototype in a prior, unrelated prototype hit a native-binding crash
 * with `@tensorflow/tfjs-node` on Node 24 / macOS ARM. `onnxruntime-node`
 * was smoke-tested directly on that same machine/Node combination before
 * writing this file (an InferenceSession loaded and ran real inference
 * successfully) and did NOT reproduce that failure, so v0.1 uses
 * `onnxruntime-node` as originally planned -- no WASM fallback was needed
 * for the runtime. The one real substitution made is the *model*: see
 * src/score/models/NOTICE.md for why MobileNetV2 (a generic ImageNet
 * feature extractor) is used instead of a dedicated face/CLIP embedding
 * model, and what that means for accuracy.
 */

import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import * as ort from 'onnxruntime-node';
import { FRAME_SIZE, readRawFrame } from '../ingest/ffmpeg.js';

const __dirname = dirname(fileURLToPath(import.meta.url));
const MODEL_PATH = join(__dirname, 'models', 'mobilenetv2-7.onnx');

// ImageNet normalization constants used by the bundled MobileNetV2 model's
// documented preprocessing (see src/score/models/NOTICE.md).
const IMAGENET_MEAN = [0.485, 0.456, 0.406];
const IMAGENET_STD = [0.229, 0.224, 0.225];

/**
 * Cross-shot cosine-similarity threshold below which a shot is flagged as
 * a likely character-consistency break. Derived from this repo's own
 * fixture run -- see CHANGELOG.md "CG02 fixture calibration" entry for the
 * exact command and raw numbers this value came from. Not the execution
 * plan's illustrative 0.62 placeholder.
 */
export const CONSISTENCY_SIMILARITY_THRESHOLD = 0.88;

let cachedSession: ort.InferenceSession | undefined;

/** Loads (and caches) the bundled ONNX embedding session. Never fetches
 * anything over the network -- the model file ships inside this package. */
export async function getEmbeddingSession(): Promise<ort.InferenceSession> {
  if (!cachedSession) {
    cachedSession = await ort.InferenceSession.create(MODEL_PATH);
  }
  return cachedSession;
}

/** Converts a raw HWC RGB24 frame buffer into the CHW, ImageNet-normalized
 * Float32Array MobileNetV2 expects. */
export function preprocessFrame(raw: Uint8Array): Float32Array {
  const size = FRAME_SIZE;
  const out = new Float32Array(3 * size * size);
  const planeSize = size * size;
  for (let pixel = 0; pixel < planeSize; pixel++) {
    const r = raw[pixel * 3] as number;
    const g = raw[pixel * 3 + 1] as number;
    const b = raw[pixel * 3 + 2] as number;
    out[pixel] = (r / 255 - IMAGENET_MEAN[0]!) / IMAGENET_STD[0]!;
    out[planeSize + pixel] = (g / 255 - IMAGENET_MEAN[1]!) / IMAGENET_STD[1]!;
    out[2 * planeSize + pixel] = (b / 255 - IMAGENET_MEAN[2]!) / IMAGENET_STD[2]!;
  }
  return out;
}

/** Runs one frame through the embedding model and returns its raw 1000-d
 * output vector (see src/score/models/NOTICE.md for why this is the raw
 * classifier-logit vector rather than a dedicated embedding-layer output). */
export async function embedFrame(
  raw: Uint8Array,
  session: ort.InferenceSession
): Promise<Float32Array> {
  const input = preprocessFrame(raw);
  const tensor = new ort.Tensor('float32', input, [1, 3, FRAME_SIZE, FRAME_SIZE]);
  const inputName = session.inputNames[0];
  if (!inputName) {
    throw new Error('Embedding model exposes no input tensor names');
  }
  const results = await session.run({ [inputName]: tensor });
  const outputName = session.outputNames[0];
  if (!outputName) {
    throw new Error('Embedding model exposes no output tensor names');
  }
  const output = results[outputName];
  if (!output) {
    throw new Error('Embedding model produced no output tensor');
  }
  return Float32Array.from(output.data as Float32Array);
}

/** Computes one embedding per shot by averaging the embeddings of every
 * sampled frame in that shot -- smooths single-frame noise into a more
 * stable per-shot signal than picking any single frame would. */
export async function embedShot(
  framePaths: string[],
  session: ort.InferenceSession
): Promise<Float32Array> {
  if (framePaths.length === 0) {
    throw new Error('Cannot embed a shot with zero extracted frames');
  }
  let sum: Float32Array | undefined;
  for (const framePath of framePaths) {
    const raw = await readRawFrame(framePath);
    const embedding = await embedFrame(raw, session);
    if (!sum) {
      sum = new Float32Array(embedding.length);
    }
    for (let i = 0; i < embedding.length; i++) {
      sum[i] = (sum[i] as number) + (embedding[i] as number);
    }
  }
  const result = sum as Float32Array;
  for (let i = 0; i < result.length; i++) {
    result[i] = (result[i] as number) / framePaths.length;
  }
  return result;
}

export function cosineSimilarity(a: Float32Array, b: Float32Array): number {
  if (a.length !== b.length) {
    throw new Error('Cannot compare embeddings of different dimensionality');
  }
  let dot = 0;
  let normA = 0;
  let normB = 0;
  for (let i = 0; i < a.length; i++) {
    const av = a[i] as number;
    const bv = b[i] as number;
    dot += av * bv;
    normA += av * av;
    normB += bv * bv;
  }
  if (normA === 0 || normB === 0) {
    return 0;
  }
  return dot / (Math.sqrt(normA) * Math.sqrt(normB));
}

/**
 * Infers the named character a clip belongs to from its filename, using
 * a `<character>_<shot-id>.<ext>` convention (e.g. "mei_shot01.mp4" ->
 * "mei"). This is a deliberate v0.1 simplification: there is no
 * industry-standard character-tagging metadata format across AI
 * short-drama pipelines, so ContinuityGuard reads it from the filename
 * rather than requiring a separate manifest. Clips that don't match the
 * convention are grouped under a single "unlabeled" bucket and are never
 * compared to each other for consistency (no named-character claim to
 * check them against).
 */
export function parseCharacterName(clipFileName: string): string | undefined {
  const withoutExt = clipFileName.replace(/\.[^.]+$/, '');
  const match = /^([a-zA-Z][a-zA-Z0-9]*)_/.exec(withoutExt);
  return match?.[1]?.toLowerCase();
}

export interface ShotInput {
  clip: string;
  framePaths: string[];
}

export interface ConsistencyFlag {
  clip: string;
  character: string;
  referenceClip: string;
  similarityScore: number;
  reason: string;
}

export interface ConsistencyResult {
  charactersTracked: number;
  flaggedShots: ConsistencyFlag[];
}

/** Builds the honest, unverified-content-labeled reason string for a
 * flagged shot -- kept as its own function so every call site (CLI, JSON
 * report) uses identical, never-drifting wording. */
export function buildConsistencyReason(similarity: number): string {
  return (
    `Cross-shot embedding similarity ${similarity.toFixed(2)} is below the ` +
    `${CONSISTENCY_SIMILARITY_THRESHOLD.toFixed(2)} threshold. Best-validated on ` +
    'photorealistic content; accuracy on stylized/anime-adjacent character designs ' +
    'is unverified -- treat this as a prompt for human review, not a confirmed defect.'
  );
}

/**
 * Pure grouping + flagging logic, independent of the embedding model --
 * given already-computed per-shot embeddings, groups by character and
 * flags any shot whose similarity to that character's first-seen
 * ("reference") shot falls below CONSISTENCY_SIMILARITY_THRESHOLD.
 * Split out from `scoreConsistency` so this logic has fast, deterministic
 * unit-test coverage without depending on real ONNX inference for every
 * test case.
 */
export function flagInconsistentShots(
  shots: { clip: string; embedding: Float32Array }[],
  threshold: number = CONSISTENCY_SIMILARITY_THRESHOLD
): ConsistencyResult {
  const byCharacter = new Map<string, { clip: string; embedding: Float32Array }[]>();
  for (const shot of shots) {
    const character = parseCharacterName(shot.clip);
    if (!character) continue;
    const bucket = byCharacter.get(character) ?? [];
    bucket.push(shot);
    byCharacter.set(character, bucket);
  }

  const flaggedShots: ConsistencyFlag[] = [];
  for (const [character, bucket] of byCharacter) {
    if (bucket.length < 2) continue;
    const reference = bucket[0] as { clip: string; embedding: Float32Array };
    for (let i = 1; i < bucket.length; i++) {
      const candidate = bucket[i] as { clip: string; embedding: Float32Array };
      const similarity = cosineSimilarity(reference.embedding, candidate.embedding);
      if (similarity < threshold) {
        flaggedShots.push({
          clip: candidate.clip,
          character,
          referenceClip: reference.clip,
          similarityScore: Number(similarity.toFixed(4)),
          reason: buildConsistencyReason(similarity),
        });
      }
    }
  }

  return {
    charactersTracked: byCharacter.size,
    flaggedShots,
  };
}

/** End-to-end CG02 entry point: computes embeddings for every shot (via the
 * real ONNX model) and flags cross-shot consistency breaks. */
export async function scoreConsistency(
  shots: ShotInput[],
  options: { session?: ort.InferenceSession; threshold?: number } = {}
): Promise<ConsistencyResult> {
  const session = options.session ?? (await getEmbeddingSession());
  const embedded: { clip: string; embedding: Float32Array }[] = [];
  for (const shot of shots) {
    const embedding = await embedShot(shot.framePaths, session);
    embedded.push({ clip: shot.clip, embedding });
  }
  return flagInconsistentShots(embedded, options.threshold);
}
