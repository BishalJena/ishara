"""Fetch the pinned SignCLIP source, official checkpoint and BERT metadata only.

Run with artifacts/signclip/.venv/bin/python after installing requirements-signclip.txt.
"""
import subprocess

import gdown
from huggingface_hub import snapshot_download

import signclip


def main():
    signclip.ASSETS.mkdir(parents=True, exist_ok=True)
    if not signclip.SOURCE.exists():
        subprocess.run(["git", "clone", "--filter=blob:none", "--sparse",
                        "https://github.com/J22Melody/fairseq.git", str(signclip.SOURCE)], check=True)
        subprocess.run(["git", "-C", str(signclip.SOURCE), "sparse-checkout",
                        "set", "examples/MMPT"], check=True)
        subprocess.run(["git", "-C", str(signclip.SOURCE), "checkout", signclip.REVISION], check=True)
    signclip.upstream()
    if not signclip.CHECKPOINT.exists():
        gdown.download(id="1_B_VZMaLqY1nV6z9AokWU_G6LvOQLZFu",
                       output=str(signclip.CHECKPOINT), resume=True, quiet=False)
    digest = signclip.sha256(signclip.CHECKPOINT)
    if signclip.CHECKPOINT_SHA and digest != signclip.CHECKPOINT_SHA:
        raise ValueError("Downloaded SignCLIP checkpoint checksum does not match")
    print("Checkpoint SHA-256:", digest)
    snapshot_download("google-bert/bert-base-cased", revision=signclip.BERT_REVISION,
                      local_dir=signclip.BERT_DIR, token=False,
                      allow_patterns=["config.json", "tokenizer*.json", "vocab.txt"])
    print("Source/checkpoint/metadata ready; no BERT base weights or dataset downloaded.")


if __name__ == "__main__":
    main()
