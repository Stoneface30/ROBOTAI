"""
Download and convert background audio for microWakeWord training.
Run from the training workdir:  python microwakeword_download_bg.py

MIT RIRs are skipped (impulse_paths=[] in the augmenter config is fine).
AudioSet + FMA are downloaded directly and converted with soundfile/librosa.
"""
import subprocess
import tarfile
import zipfile
from pathlib import Path

import librosa
import numpy as np
import scipy.io.wavfile
import soundfile as sf
from tqdm import tqdm


def to_16k_mono_wav(src: Path, dst: Path):
    data, sr = sf.read(str(src), always_2d=False)
    if data.ndim > 1:
        data = data.mean(axis=1)
    data = data.astype(np.float32)
    if sr != 16000:
        data = librosa.resample(data, orig_sr=sr, target_sr=16000)
    scipy.io.wavfile.write(
        str(dst), 16000, (data * 32767).clip(-32768, 32767).astype(np.int16)
    )


# ── AudioSet balanced training part 9 (~1 GB) ─────────────────────────────────
aset_dir = Path("audioset")
aset_dir.mkdir(exist_ok=True)
aset_16k = Path("audioset_16k")
aset_16k.mkdir(exist_ok=True)

if not any(aset_16k.glob("*.wav")):
    tar_path = aset_dir / "bal_train09.tar"
    if not tar_path.exists():
        print("Downloading AudioSet part 9 (~1 GB)...")
        subprocess.run(
            ["curl", "-L", "--progress-bar", "-o", str(tar_path),
             "https://huggingface.co/datasets/agkphysics/AudioSet/resolve/main/"
             "data/bal_train09.tar"],
            check=True,
        )
    print("Extracting AudioSet...")
    with tarfile.open(tar_path) as tf:
        tf.extractall(str(aset_dir))
    print("Converting AudioSet FLAC -> 16 kHz WAV...")
    flacs = list(Path("audioset/audio").glob("**/*.flac"))
    for flac in tqdm(flacs):
        try:
            to_16k_mono_wav(flac, aset_16k / (flac.stem + ".wav"))
        except Exception as exc:
            print(f"  skip {flac.name}: {exc}")
    print(f"AudioSet 16k: {len(list(aset_16k.glob('*.wav')))} files")
else:
    print(f"AudioSet 16k already present: {len(list(aset_16k.glob('*.wav')))} files")

# ── FMA XS (extra-small, CC-licensed music) ───────────────────────────────────
fma_dir  = Path("fma")
fma_dir.mkdir(exist_ok=True)
fma_16k  = Path("fma_16k")
fma_16k.mkdir(exist_ok=True)

if not any(fma_16k.glob("*.wav")):
    zip_path = fma_dir / "fma_xs.zip"
    if not zip_path.exists():
        print("Downloading FMA XS...")
        subprocess.run(
            ["curl", "-L", "--progress-bar", "-o", str(zip_path),
             "https://huggingface.co/datasets/mchl914/fma_xsmall/resolve/main/"
             "fma_xs.zip"],
            check=True,
        )
    print("Extracting FMA XS...")
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(str(fma_dir))
    print("Converting FMA MP3 -> 16 kHz WAV...")
    mp3s = list(Path("fma/fma_small").glob("**/*.mp3"))
    for mp3 in tqdm(mp3s):
        try:
            to_16k_mono_wav(mp3, fma_16k / (mp3.stem + ".wav"))
        except Exception as exc:
            print(f"  skip {mp3.name}: {exc}")
    print(f"FMA 16k: {len(list(fma_16k.glob('*.wav')))} files")
else:
    print(f"FMA 16k already present: {len(list(fma_16k.glob('*.wav')))} files")

print("Background audio ready.")
