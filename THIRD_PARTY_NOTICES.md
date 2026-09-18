# Third-party notices

OpenTryOn's original application code is MIT licensed. Model code, weights and sample media are **not** relicensed under MIT.

| Component | Upstream | License / notes |
| --- | --- | --- |
| FASHN VTON 1.5 inference | https://github.com/fashn-AI/fashn-vton-1.5 | Apache-2.0, pinned to `7c0f10af3f91ad4048fe9729c470a13ef905d25a` |
| FASHN VTON weights | https://huggingface.co/fashn-ai/fashn-vton-1.5 | Model card declares Apache-2.0; downloaded separately |
| DWPose | https://github.com/IDEA-Research/DWPose | Apache-2.0; weights sourced from `fashn-ai/DWPose` |
| YOLOX | https://github.com/Megvii-BaseDetection/YOLOX | Apache-2.0 |
| FASHN human parser | https://github.com/fashn-AI/fashn-human-parser/blob/main/LICENSE | Separate NVIDIA Source Code License for SegFormer; not covered by the VTON Apache license |
| SegFormer | https://github.com/NVlabs/SegFormer/blob/master/LICENSE | Review the underlying NVIDIA terms, including non-commercial restrictions |
| Public-demo validation fixtures | `examples/data/model.webp` and `examples/data/garment.webp` in the pinned FASHN VTON repository | Stored in `tests/fixtures/` under the upstream repository's Apache-2.0 license, copied without modification; no generated output is bundled |
| Web person and garment references | User-provided reference images | Included at the user's request. The repository publisher is responsible for confirming redistribution, watermark and likeness rights before making the repository public |

The upstream Apache license is included at `licenses/FASHN-APACHE-2.0.txt`.

The default FASHN pipeline calls its human parser even in segmentation-free mode. Disabling OpenTryOn's preservation option does **not** remove this dependency. Consequently this project does not claim the complete default inference stack is unrestricted for commercial deployment. Confirm component and model terms for your use, or implement a provider with suitable licenses. This is a dependency-specific limitation, not a restriction added by OpenTryOn's MIT license.
