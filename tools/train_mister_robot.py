"""
train_mister_robot.py — End-to-end microWakeWord training for "Mister Robot".

Phases:
  1. Install deps into the isolated venv (tools/microwakeword-train/.venv)
  2. Generate TTS positive samples via piper-sample-generator
  3. Copy real recordings as additional positive samples
  4. Download MIT RIR + AudioSet + FMA-XS background audio
  5. Download pre-generated negative spectrogram features from HuggingFace
  6. Generate augmented spectrogram features from positives
  7. Train the model (RTX 5060 Ti ~20-30 min)
  8. Write tflite + ESPHome JSON manifest to tools/wake_word_output/

Run from the repo root:
    python tools/train_mister_robot.py
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).parent.parent
TOOLS        = REPO_ROOT / "tools"
TRAIN_DIR    = TOOLS / "microwakeword-train"
VENV         = TRAIN_DIR / ".venv"
VENV_PY      = VENV / "Scripts" / "python.exe"
WORK         = TRAIN_DIR / "workdir"
RECORDINGS   = TOOLS / "recordings" / "mister_robot"
OUTPUT_DIR   = TOOLS / "wake_word_output"

WAKE_WORD         = "Mister Robot"
WAKE_WORD_SLUG    = "mister_robot"
PHONETIC          = "mister robot"   # piper phonetic hint
TTS_SAMPLE_COUNT  = 1000

# ── helpers ───────────────────────────────────────────────────────────────────
def run(cmd, cwd=None, env=None, check=True):
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(
        [str(c) for c in cmd],
        cwd=str(cwd or WORK),
        env=env,
        check=check,
    )
    return result

def pip(*packages):
    run([VENV_PY, "-m", "pip", "install", "--quiet", "--upgrade", *packages],
        cwd=TRAIN_DIR)

def python_run(script_args, cwd=None, extra_env=None):
    env = os.environ.copy()
    if extra_env:
        env.update(extra_env)
    run([VENV_PY, *script_args], cwd=cwd or WORK, env=env)

# ── phase 1: install deps ─────────────────────────────────────────────────────
def phase1_install():
    print("\n" + "="*60)
    print("PHASE 1 — Installing dependencies")
    print("="*60)
    pip("pip", "setuptools", "wheel")
    # TF 2.16+ required; use CPU build for compatibility, GPU will auto-use CUDA
    pip("tensorflow==2.17.0")
    pip("ai-edge-litert")
    # Install microwakeword package itself
    run([VENV_PY, "-m", "pip", "install", "--quiet", "-e", "."], cwd=TRAIN_DIR)
    # Extra deps for piper-sample-generator
    pip("soundfile", "librosa", "scipy", "pandas", "pyarrow")
    # torch + torchcodec required by datasets.Audio() used inside microwakeword Clips class
    pip("torch", "--index-url", "https://download.pytorch.org/whl/cu121")
    pip("torchcodec")

# ── phase 2: TTS positive samples ────────────────────────────────────────────
def phase2_tts_samples():
    print("\n" + "="*60)
    print("PHASE 2 — Generating TTS positive samples")
    print("="*60)
    piper_dir = WORK / "piper-sample-generator"
    if not piper_dir.exists():
        run(["git", "clone", "https://github.com/rhasspy/piper-sample-generator",
             str(piper_dir)], cwd=WORK)

    model_path = piper_dir / "models" / "en_US-libritts_r-medium.pt"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    if not model_path.exists():
        run(["curl", "-L", "-o", str(model_path),
             "https://github.com/rhasspy/piper-sample-generator/releases/download/v2.0.0/en_US-libritts_r-medium.pt"],
            cwd=WORK)

    out = WORK / "positive_samples"
    out.mkdir(parents=True, exist_ok=True)

    python_run(
        [str(piper_dir / "generate_samples.py"), PHONETIC,
         "--max-samples", str(TTS_SAMPLE_COUNT),
         "--batch-size", "100",
         "--output-dir", str(out)],
        cwd=piper_dir,
    )
    return out

# ── phase 3: copy real recordings into positive dir ───────────────────────────
def phase3_copy_recordings(positive_dir: Path):
    print("\n" + "="*60)
    print("PHASE 3 — Adding real family recordings")
    print("="*60)
    real_dir = positive_dir / "real_recordings"
    real_dir.mkdir(parents=True, exist_ok=True)
    copied = 0
    for wav in RECORDINGS.rglob("*.wav"):
        shutil.copy(wav, real_dir / f"real_{copied:04d}.wav")
        copied += 1
    print(f"  Copied {copied} real recordings to {real_dir}")

# ── phase 4: download background audio ───────────────────────────────────────
def phase4_background():
    print("\n" + "="*60)
    print("PHASE 4 — Downloading background audio (MIT RIRs + AudioSet + FMA)")
    print("="*60)
    # Download script lives as a separate file to avoid string-embedding issues
    import shutil as _shutil
    bg_script_src = TOOLS / "microwakeword_download_bg.py"
    bg_script_dst = WORK / "_download_bg.py"
    _shutil.copy(bg_script_src, bg_script_dst)
    python_run([str(bg_script_dst)], cwd=WORK)

# ── phase 5: download pre-generated negative features ────────────────────────
def phase5_negatives():
    print("\n" + "="*60)
    print("PHASE 5 — Downloading pre-generated negative features")
    print("="*60)
    neg_dir = WORK / "negative_datasets"
    neg_dir.mkdir(parents=True, exist_ok=True)
    # Use huggingface_hub (handles LFS automatically — curl gets pointer files)
    script = WORK / "_dl_negatives.py"
    script.write_text(
        "import zipfile, shutil\n"
        "from pathlib import Path\n"
        "from huggingface_hub import hf_hub_download\n"
        "neg_dir = Path('negative_datasets')\n"
        "neg_dir.mkdir(exist_ok=True)\n"
        "for fname in ['dinner_party.zip','dinner_party_eval.zip','no_speech.zip','speech.zip']:\n"
        "    marker = neg_dir / fname.replace('.zip','')\n"
        "    if marker.exists(): print(f'Already have {fname}'); continue\n"
        "    print(f'Downloading {fname}...')\n"
        "    local = hf_hub_download(repo_id='kahrendt/microwakeword', repo_type='dataset', filename=fname)\n"
        "    with zipfile.ZipFile(local) as z: z.extractall(str(neg_dir))\n"
        "    print(f'  extracted to {neg_dir}')\n"
        "print('Negatives ready.')\n"
    )
    python_run([str(script)], cwd=WORK)

# ── phase 6: generate positive spectrogram features ──────────────────────────
def phase6_features(positive_dir: Path):
    print("\n" + "="*60)
    print("PHASE 6 — Generating augmented spectrogram features from positives")
    print("="*60)
    script = WORK / "_gen_features.py"
    script.write_text(f"""
import os, sys
sys.path.insert(0, r'{TRAIN_DIR}')
from mmap_ninja.ragged import RaggedMmap
from microwakeword.audio.augmentation import Augmentation
from microwakeword.audio.clips import Clips
from microwakeword.audio.spectrograms import SpectrogramGeneration

clips = Clips(
    input_directory=r'{positive_dir}',
    file_pattern='**/*.wav',
    max_clip_duration_s=None,
    remove_silence=False,
    random_split_seed=42,
    split_count=0.1,
)

augmenter = Augmentation(
    augmentation_duration_s=3.2,
    augmentation_probabilities={{
        "SevenBandParametricEQ": 0.2,
        "TanhDistortion":        0.1,
        "PitchShift":            0.3,
        "BandStopFilter":        0.15,
        "AddColorNoise":         0.5,
        "AddBackgroundNoise":    0.0,
        "Gain":                  1.0,
        "RIR":                   0.0,
    }},
    impulse_paths=[],
    background_paths=[],         # no external background audio; use AddColorNoise only
    background_min_snr_db=-5,
    background_max_snr_db=10,
    min_jitter_s=0.195,
    max_jitter_s=0.205,
)

out_dir = 'generated_augmented_features'
os.makedirs(out_dir, exist_ok=True)

for split, split_name, rep, slide in [
    ('training',   'train',      2, 10),
    ('validation', 'validation', 1, 10),
    ('testing',    'test',       1,  1),
]:
    out = os.path.join(out_dir, split)
    os.makedirs(out, exist_ok=True)
    spec = SpectrogramGeneration(clips=clips, augmenter=augmenter,
                                  slide_frames=slide, step_ms=10)
    RaggedMmap.from_generator(
        out_dir=os.path.join(out, 'wakeword_mmap'),
        sample_generator=spec.spectrogram_generator(split=split_name, repeat=rep),
        batch_size=100, verbose=True,
    )

print("Features generated.")
""")
    python_run([str(script)], cwd=WORK)

# ── phase 7: train ────────────────────────────────────────────────────────────
def phase7_train():
    print("\n" + "="*60)
    print("PHASE 7 — Training model (RTX 5060 Ti)")
    print("="*60)
    import yaml
    config = {
        "window_step_ms": 10,
        "train_dir": "trained_models/wakeword",
        "features": [
            {"features_dir": "generated_augmented_features",
             "sampling_weight": 2.0, "penalty_weight": 1.0,
             "truth": True, "truncation_strategy": "truncate_start", "type": "mmap"},
            {"features_dir": "negative_datasets/speech",
             "sampling_weight": 10.0, "penalty_weight": 1.0,
             "truth": False, "truncation_strategy": "random", "type": "mmap"},
            {"features_dir": "negative_datasets/dinner_party",
             "sampling_weight": 10.0, "penalty_weight": 1.0,
             "truth": False, "truncation_strategy": "random", "type": "mmap"},
            {"features_dir": "negative_datasets/no_speech",
             "sampling_weight": 5.0, "penalty_weight": 1.0,
             "truth": False, "truncation_strategy": "random", "type": "mmap"},
            {"features_dir": "negative_datasets/dinner_party_eval",
             "sampling_weight": 0.0, "penalty_weight": 1.0,
             "truth": False, "truncation_strategy": "split", "type": "mmap"},
        ],
        "training_steps": [15000],
        "positive_class_weight": [1],
        "negative_class_weight": [20],
        "learning_rates": [0.001],
        "batch_size": 128,
        "time_mask_max_size": [0],
        "time_mask_count": [0],
        "freq_mask_max_size": [0],
        "freq_mask_count": [0],
        "eval_step_interval": 500,
        "clip_duration_ms": 1500,
        "target_minimization": 0.9,
        "minimization_metric": None,
        "maximization_metric": "average_viable_recall",
    }
    cfg_path = WORK / "training_parameters.yaml"
    cfg_path.write_text(yaml.dump(config))

    python_run(
        ["-m", "microwakeword.model_train_eval",
         f"--training_config={cfg_path}",
         "--train", "1",
         "--restore_checkpoint", "1",
         "--test_tf_nonstreaming", "0",
         "--test_tflite_nonstreaming", "0",
         "--test_tflite_nonstreaming_quantized", "0",
         "--test_tflite_streaming", "0",
         "--test_tflite_streaming_quantized", "1",
         "--use_weights", "best_weights",
         "mixednet",
         "--pointwise_filters", "64,64,64,64",
         "--repeat_in_block", "1, 1, 1, 1",
         "--mixconv_kernel_sizes", "[5], [7,11], [9,15], [23]",
         "--residual_connection", "0,0,0,0",
         "--first_conv_filters", "32",
         "--first_conv_kernel_size", "5",
         "--stride", "3"],
        cwd=WORK,
    )

# ── phase 8: package output ───────────────────────────────────────────────────
def phase8_package():
    print("\n" + "="*60)
    print("PHASE 8 — Packaging output")
    print("="*60)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    tflite_src = WORK / "trained_models" / "wakeword" / \
                 "tflite_stream_state_internal_quant" / \
                 "stream_state_internal_quant.tflite"
    tflite_dst = OUTPUT_DIR / f"{WAKE_WORD_SLUG}.tflite"
    shutil.copy(tflite_src, tflite_dst)

    import json
    manifest = {
        "wake_word": WAKE_WORD,
        "author": "Family training — microWakeWord",
        "website": "",
        "model": f"{WAKE_WORD_SLUG}.tflite",
        "opaque_model_data_v2": {
            "tensor_arena_size": 32 * 1024,
            "probability_cutoff": 0.5,
            "sliding_window_average_size": 10,
        },
        "version": 2,
        "micro": {
            "minimum_esphome_version": "2024.2.0",
        },
    }
    manifest_path = OUTPUT_DIR / f"{WAKE_WORD_SLUG}.json"
    manifest_path.write_text(json.dumps(manifest, indent=2))

    print(f"\n  tflite  : {tflite_dst}")
    print(f"  manifest: {manifest_path}")
    print("\n  Next: host these files on GitHub, then update esphome/dualeye.yaml:")
    print(f"    - model: github://YOUR_USER/YOUR_REPO/wake_word_output/{WAKE_WORD_SLUG}.json")


# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    WORK.mkdir(parents=True, exist_ok=True)

    phase1_install()
    # Skip TTS generation (piper-phonemize-cross has no Windows wheel).
    # Our 144 real recordings are used directly as positive samples.
    pos = WORK / "positive_samples"
    pos.mkdir(parents=True, exist_ok=True)
    phase3_copy_recordings(pos)
    # phase4 skipped: HuggingFace LFS blocks direct curl for large tars.
    # Using color/gain augmentation only (no background mixing needed).
    phase5_negatives()
    phase6_features(pos)
    phase7_train()
    phase8_package()

    print("\n" + "="*60)
    print("TRAINING COMPLETE")
    print(f"Output: {OUTPUT_DIR}")
    print("="*60)
