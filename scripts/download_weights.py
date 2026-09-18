"""Download upstream weights explicitly; no large downloads on web startup."""

import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights-dir", type=Path, default=Path("weights"))
    parser.add_argument("--revision", default="main", help="FASHN model weight revision")
    args = parser.parse_args()
    try:
        from fashn_human_parser import FashnHumanParser
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise SystemExit('Install inference dependencies first: pip install -e ".[inference]"') from exc
    hf_hub_download(
        "fashn-ai/fashn-vton-1.5",
        "model.safetensors",
        revision=args.revision,
        local_dir=str(args.weights_dir),
    )
    for filename in ("yolox_l.onnx", "dw-ll_ucoco_384.onnx"):
        hf_hub_download("fashn-ai/DWPose", filename, local_dir=str(args.weights_dir / "dwpose"))
    FashnHumanParser(device="cpu")
    print(f"Weights are ready in {args.weights_dir.resolve()}")


if __name__ == "__main__":
    main()
