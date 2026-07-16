# Bundled model: MobileNetV2 (ONNX)

`mobilenetv2-7.onnx` is the MobileNetV2-1.0 image classifier from the
[ONNX Model Zoo](https://github.com/onnx/models), `validated/vision/classification/mobilenet`,
opset 7. It is trained on ImageNet (ILSVRC2012) and licensed **Apache-2.0**
(see the model directory's own `SPDX-License-Identifier: Apache-2.0` header
in that repo), compatible with ContinuityGuard's own Apache-2.0 license.

## Why this model, and not a face/CLIP embedding model

The execution plan for this project called for a pretrained ONNX embedding
model via `onnxruntime-node` for character-consistency scoring, with CLIP
ViT-B/32 named as an illustrative example elsewhere in this portfolio's
research. `onnxruntime-node` itself works fine on this build's target
platform (see the root README's "onnxruntime-node vs. WASM" note) -- the
substitution here is the *model*, not the runtime.

v0.1 ships MobileNetV2 instead of a dedicated face-recognition or CLIP
embedding model for one practical reason: a specialized face/character
embedding model that is both small enough to bundle directly in an npm
package and unambiguously permissively licensed was not something this
build could source, convert, and license-verify inside this session's
scope. MobileNetV2 is small (14MB), Apache-2.0 licensed with no ambiguity,
and works today.

**What this means in practice, stated honestly:** ContinuityGuard's
character-consistency score is a cosine-similarity comparison of
MobileNetV2's final 1000-way ImageNet-logit vector between two character
crops, used as a generic visual-similarity proxy -- not a specialized
face-identity or CLIP embedding tuned for "is this the same character."
It will respond to overall color, texture, and coarse-shape similarity
between crops, which is a real but weaker signal than a dedicated
face-recognition embedding would give you on photorealistic faces, and an
even weaker, unvalidated signal on stylized/anime-adjacent character
designs (see the main README's "Known limitations" section, which applies
regardless of which embedding model is used underneath).

This is disclosed here, in the CLI output, in the JSON report's `reason`
field, and in the README -- not discovered later by a disappointed user.
A future version can swap in a dedicated face-embedding ONNX model behind
the same `computeEmbedding` interface in `src/score/consistency.ts` without
changing the CLI or report shape.
