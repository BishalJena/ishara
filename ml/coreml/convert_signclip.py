"""Convert the frozen SignCLIP video encoder to a Core ML ML Program.

The wrapper reproduces MMFusionSeparate.forward_video (as called by
spikes/recognition/signclip.embed) with the padded-input contract in contract.py:
video MLP -> [CLS] video [SEP] embeddings -> 12 BERT layers -> masked mean pool
over video frames plus the video [SEP] (CLS excluded), exactly as upstream.

Run with ml/coreml/.venv/bin/python after spikes/recognition/setup_signclip.py.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

import contract

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / "artifacts"
sys.path.insert(0, str(HERE.parents[1] / "spikes" / "recognition"))
import signclip  # noqa: E402  (spikes/recognition is not a package)

PRECISIONS = {"fp16": "SignCLIPEncoder.mlpackage", "fp32": "SignCLIPEncoder-fp32.mlpackage"}
# Additive key mask. transformers uses float32 min, which overflows to -inf in FP16
# and turns (1 - mask) * min into NaN for real frames; -1e4 still underflows exp() to 0.
MASK_PENALTY = -1e4


class SignCLIPEncoder(torch.nn.Module):
    def __init__(self, video_encoder: torch.nn.Module, caps: torch.Tensor):
        super().__init__()
        if video_encoder.videoconv is not None or video_encoder.perceiver is not None:
            raise ValueError("Checkpoint uses a video front end this wrapper does not reproduce")
        self.mlp = video_encoder.videomlp
        self.embeddings = video_encoder.bert.embeddings
        self.layers = video_encoder.bert.encoder
        self.register_buffer("caps", caps[:, :2].clone())

    def forward(self, features: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        ones = torch.ones_like(mask[:, :1])
        keys = torch.cat([ones, mask, ones], 1)  # [CLS] video [SEP]
        hidden = self.embeddings(self.caps, self.mlp(features),
                                 token_type_ids=torch.zeros_like(keys, dtype=torch.long))
        hidden = self.layers(hidden, attention_mask=(1.0 - keys)[:, None, None, :] * MASK_PENALTY)[0]
        weights = torch.cat([torch.zeros_like(ones), mask, ones], 1)
        weights = weights / weights.sum(1, keepdim=True)
        return torch.bmm(hidden.transpose(2, 1), weights.unsqueeze(2)).squeeze(-1)


def load_wrapper() -> tuple[SignCLIPEncoder, object]:
    model = signclip.load_model()
    return SignCLIPEncoder(model.video_encoder, model.caps).eval(), model


@torch.inference_mode()
def torch_embed(wrapper: SignCLIPEncoder, features: np.ndarray, mask: np.ndarray) -> np.ndarray:
    return wrapper(torch.from_numpy(features), torch.from_numpy(mask))[0].numpy()


def check_wrapper(wrapper: SignCLIPEncoder, model: object) -> float:
    """Fail fast unless the wrapper matches signclip.embed on synthetic frames."""
    worst = 1.0
    for frames in (4, 63, 256):
        raw = np.random.default_rng(frames).normal(scale=0.5, size=(frames, 609)).astype(np.float32)
        worst = min(worst, contract.cosine(signclip.embed(model, raw), torch_embed(wrapper, *contract.pad(raw))))
    if worst < 0.999999:
        raise RuntimeError(f"Wrapper diverges from signclip.embed (cosine {worst:.7f})")
    return worst


def convert(wrapper: SignCLIPEncoder, precision: str) -> Path:
    import coremltools as ct

    example = contract.pad(np.zeros((contract.MIN_FRAMES, contract.FEATURE_DIM), np.float32))
    with torch.inference_mode():
        traced = torch.jit.trace(wrapper, tuple(torch.from_numpy(x) for x in example))
    mlmodel = ct.convert(
        traced,
        inputs=[ct.TensorType("features", shape=example[0].shape, dtype=np.float32),
                ct.TensorType("mask", shape=example[1].shape, dtype=np.float32)],
        outputs=[ct.TensorType("embedding", dtype=np.float32)],
        convert_to="mlprogram",
        minimum_deployment_target=ct.target.iOS17,
        compute_precision=ct.precision.FLOAT16 if precision == "fp16" else ct.precision.FLOAT32,
    )
    mlmodel.short_description = ("Frozen multilingual SignCLIP pose encoder. Raw embedding; "
                                 "L2-normalize before cosine matching.")
    mlmodel.input_description["features"] = "SignCLIP-normalized pose frames [1,256,609], zero-padded at the end"
    mlmodel.input_description["mask"] = "1 for real frames, 0 for padding [1,256]"
    mlmodel.output_description["embedding"] = "Raw 768-d video embedding"
    mlmodel.user_defined_metadata.update({
        "signclip_source": signclip.REVISION, "checkpoint_sha256": signclip.CHECKPOINT_SHA,
        "input_contract": signclip.CONTRACT, "precision": precision,
        "max_frames": str(contract.MAX_FRAMES), "min_frames": str(contract.MIN_FRAMES)})
    destination = ARTIFACTS / PRECISIONS[precision]
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    mlmodel.save(str(destination))
    return destination


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--precision", choices=sorted(PRECISIONS), nargs="+", default=["fp16"])
    args = parser.parse_args()
    torch.set_num_threads(4)
    wrapper, model = load_wrapper()
    print(f"Wrapper vs signclip.embed worst cosine: {check_wrapper(wrapper, model):.7f}")
    for precision in args.precision:
        print(f"Saved {convert(wrapper, precision).relative_to(HERE)}")


if __name__ == "__main__":
    main()
