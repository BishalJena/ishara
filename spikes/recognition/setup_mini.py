"""Fetch pinned public artifacts. No training, inference, or private uploads.

    .venv/bin/python setup_mini.py
"""
from __future__ import annotations

import hashlib
import subprocess
import urllib.request

from huggingface_hub import snapshot_download

import slgcn
from sentence import LLM_DIR, LLM_ID, LLM_REVISION


def main():
    slgcn.ARTIFACTS.mkdir(parents=True, exist_ok=True)
    if not slgcn.SOURCE.exists():
        subprocess.run(["git", "clone", "--quiet", "https://github.com/AI4Bharat/OpenHands.git",
                        str(slgcn.SOURCE)], check=True)
        subprocess.run(["git", "-C", str(slgcn.SOURCE), "checkout", "--quiet", slgcn.SOURCE_REVISION],
                       check=True)
    revision = subprocess.check_output(
        ["git", "-C", str(slgcn.SOURCE), "rev-parse", "HEAD"], text=True).strip()
    if revision != slgcn.SOURCE_REVISION:
        raise RuntimeError("Existing OpenHands clone has a different revision; preserve it and inspect before changing")
    for filename, sha in [("include_slgcn.zip", slgcn.ARCHIVE_SHA),
                          ("include_metadata.zip", slgcn.METADATA_SHA)]:
        path = slgcn.ARTIFACTS / filename
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == sha:
            print(f"Verified {filename}")
            continue
        temporary = path.with_suffix(".download")
        urllib.request.urlretrieve(
            f"https://github.com/AI4Bharat/OpenHands/releases/download/checkpoints_v1/{filename}",
            temporary)
        if hashlib.sha256(temporary.read_bytes()).hexdigest() != sha:
            temporary.unlink()
            raise RuntimeError(f"Checksum mismatch for {filename}")
        temporary.replace(path)
        print(f"Downloaded and verified {filename}")
    snapshot_download(LLM_ID, revision=LLM_REVISION, local_dir=LLM_DIR,
                      allow_patterns=["*.json", "*.safetensors", "merges.txt", "LICENSE", "README.md"],
                      token=False)
    print("Assets ready. Dataset clips can be fetched separately with fetch_clips.py.")


if __name__ == "__main__":
    main()
