#!/usr/bin/env python
"""
Train an openWakeWord classifier for the 'Mister Robot' wake word.

Uses the isolated oww_venv at tools/oww_venv to avoid dep conflicts.
Expects recordings at tools/recordings/mister_robot/{speaker}/*.wav

Output: tools/wake_word_output/mister_robot_oww.onnx
        (place this in /share/openwakeword/ on Home Assistant)

Run with:
    F:/ROBOTAI/tools/oww_venv/Scripts/python F:/ROBOTAI/tools/train_oww.py
"""
import io
import logging
import sys
import urllib.request
from pathlib import Path

# Windows console defaults to cp1252; torch.onnx prints emoji that break it.
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
TOOLS_DIR = Path(__file__).parent
RECORDINGS_DIR = TOOLS_DIR / "recordings" / "mister_robot"
OUTPUT_DIR = TOOLS_DIR / "wake_word_output"
FEATURES_DIR = TOOLS_DIR / "oww_features"
FEATURES_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

POSITIVE_FEATURES_NPY = FEATURES_DIR / "mister_robot_positive.npy"
NEGATIVE_TRAIN_NPY    = FEATURES_DIR / "negative_train.npy"
NEGATIVE_VAL_NPY      = FEATURES_DIR / "negative_val.npy"
MODEL_ONNX            = OUTPUT_DIR / "mister_robot_oww.onnx"

# Pre-computed real-speech negative embeddings from davidscripka/openwakeword_features.
# The 17 GB training file is skipped — we use the 180 MB validation set as negatives.
# This gives real speech negatives with a smaller download.
HF_BASE = "https://huggingface.co/datasets/davidscripka/openwakeword_features/resolve/main"
REAL_SPEECH_URL = f"{HF_BASE}/validation_set_features.npy"   # 180 MB — real speech

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_wav_16k(path: Path) -> np.ndarray:
    """Load WAV -> 16 kHz mono int16 PCM (required by AudioFeatures.embed_clips)."""
    import librosa
    audio, _ = librosa.load(str(path), sr=16000, mono=True)
    return (audio * 32767).clip(-32768, 32767).astype(np.int16)


def pad_or_trim(audio: np.ndarray, n_samples: int = 48000) -> np.ndarray:
    """
    Pad to n_samples (3 s at 16 kHz) with silence BEFORE the clip.
    Putting the wake word at the END mirrors how the 16-frame sliding window
    sees a wake word during real inference (context builds up, word finishes).
    """
    audio = audio.astype(np.int16)
    if len(audio) >= n_samples:
        return audio[:n_samples]
    return np.pad(audio, (n_samples - len(audio), 0))


def download_if_missing(url: str, dest: Path) -> bool:
    """Return True if file is available (already exists or downloaded OK)."""
    if dest.exists():
        log.info("Cached: %s", dest.name)
        return True
    log.info("Downloading %s ...", url)
    try:
        urllib.request.urlretrieve(url, dest)
        log.info("  saved %.1f MB", dest.stat().st_size / 1e6)
        return True
    except Exception as exc:
        log.warning("  download failed: %s", exc)
        if dest.exists():
            dest.unlink()
        return False


def make_synthetic_negatives(n_clips: int, n_samples: int = 48000) -> np.ndarray:
    """
    Fallback negative generator using noise.
    Yields weaker training than real speech negatives — expect more FP on speech.
    """
    log.warning("Using synthetic noise negatives — consider downloading HF negatives for better quality.")
    rng = np.random.default_rng(42)
    clips = np.zeros((n_clips, n_samples), dtype=np.int16)
    for i in range(n_clips):
        t = i % 3
        if t == 0:
            clips[i] = (rng.standard_normal(n_samples) * 1638).astype(np.int16)   # ~5% of 32768
        elif t == 1:
            w = rng.standard_normal(n_samples)
            cs = np.cumsum(w)
            scaled = cs / (np.abs(cs).max() + 1e-9) * 1638
            clips[i] = scaled.astype(np.int16)
    return clips


# ---------------------------------------------------------------------------
# Step 1: compute positive embeddings
# ---------------------------------------------------------------------------

def compute_positive_features() -> np.ndarray:
    if POSITIVE_FEATURES_NPY.exists():
        feats = np.load(POSITIVE_FEATURES_NPY)
        log.info("Loaded positive features: %s", feats.shape)
        return feats

    from openwakeword.utils import AudioFeatures
    F = AudioFeatures(device="cpu")

    pos_files = sorted(RECORDINGS_DIR.glob("**/*.wav"))
    if not pos_files:
        raise FileNotFoundError(f"No WAV files found under {RECORDINGS_DIR}")

    log.info("Embedding %d positive recordings ...", len(pos_files))
    clips = np.stack([pad_or_trim(load_wav_16k(p)) for p in pos_files])  # (N, 24000)
    feats = F.embed_clips(clips, batch_size=32)                           # (N, frames, 96)
    np.save(POSITIVE_FEATURES_NPY, feats)
    log.info("Saved positive features: shape %s", feats.shape)
    return feats


# ---------------------------------------------------------------------------
# Step 2: load or compute negative embeddings
# ---------------------------------------------------------------------------

def get_negative_features() -> tuple:
    """Returns (neg_train_feats, neg_val_feats, is_real_speech) each (N, frames, 96).

    Downloads the 180 MB openWakeWord validation set (real speech) and splits it 80/20.
    Falls back to synthetic noise if download fails.
    """
    real_npy = FEATURES_DIR / "real_speech_validation.npy"
    ok = download_if_missing(REAL_SPEECH_URL, real_npy)

    if ok:
        arr = np.load(real_npy, mmap_mode='r')   # shape: (N, 96) — individual embedding frames
        log.info("Real-speech embedding frames loaded: %s", arr.shape)

        # Create (window=16, 96) windows by sampling random starting positions.
        # Target 15,000 negative windows for training; 3,000 for validation.
        window = 16
        n_frames = len(arr)
        max_start = n_frames - window
        rng = np.random.default_rng(42)
        indices_tr = rng.integers(0, int(max_start * 0.8), size=15000)
        indices_va = rng.integers(int(max_start * 0.8), max_start, size=3000)

        neg_train = np.stack([arr[i:i+window] for i in indices_tr]).astype(np.float32)
        neg_val   = np.stack([arr[i:i+window] for i in indices_va]).astype(np.float32)
        log.info("Sampled negative windows — train: %s  val: %s", neg_train.shape, neg_val.shape)
        return neg_train, neg_val, True

    log.warning("Real-speech negatives unavailable — using synthetic noise.")
    log.warning("Model will have elevated false-positive rate on real speech.")

    from openwakeword.utils import AudioFeatures
    F = AudioFeatures(device="cpu")
    noise_tr = make_synthetic_negatives(2000)
    noise_va = make_synthetic_negatives(400)
    return F.embed_clips(noise_tr, batch_size=64), F.embed_clips(noise_va, batch_size=64), False


# ---------------------------------------------------------------------------
# Step 3: build sliding-window DataLoaders
# ---------------------------------------------------------------------------

def features_to_windows(feats: np.ndarray, window: int = 16) -> np.ndarray:
    """
    Slide a window of `window` frames over each clip's embedding sequence.
    Input:  (N, total_frames, 96)
    Output: (M, window, 96)
    """
    N, T, D = feats.shape
    if T < window:
        pad = np.zeros((N, window - T, D), dtype=feats.dtype)
        feats = np.concatenate([feats, pad], axis=1)
        T = window
    parts = [feats[:, s:s + window, :] for s in range(T - window + 1)]
    return np.concatenate(parts, axis=0)


def make_dataloader(pos_feats: np.ndarray, neg_feats: np.ndarray,
                    batch_size: int = 256, shuffle: bool = True,
                    neg_already_windowed: bool = False) -> DataLoader:
    """Build a DataLoader.  pos_feats is (N, frames, 96) — always needs windowing.
    neg_feats is either (N, frames, 96) clips or (N, 16, 96) pre-windowed rows."""
    win_pos = features_to_windows(pos_feats)
    win_neg = neg_feats if neg_already_windowed else features_to_windows(neg_feats)
    X = np.concatenate([win_pos, win_neg], axis=0).astype(np.float32)
    y = np.concatenate([np.ones(len(win_pos)), np.zeros(len(win_neg))]).astype(np.float32)
    ds = TensorDataset(torch.tensor(X), torch.tensor(y))
    return DataLoader(ds, batch_size=batch_size, shuffle=shuffle)


# ---------------------------------------------------------------------------
# Step 4: train
# ---------------------------------------------------------------------------

def train_model(pos_feats: np.ndarray,
                neg_train: np.ndarray,
                neg_val:   np.ndarray,
                is_real_speech_negatives: bool = False):
    from openwakeword.train import Model

    log.info("Feature shape per clip: %s", pos_feats.shape[1:])

    model = Model(n_classes=1, input_shape=(16, 96), model_type="dnn",
                  layer_dim=128, n_blocks=1)

    pos_split = max(1, int(len(pos_feats) * 0.8))
    pos_train = pos_feats[:pos_split]
    pos_val   = pos_feats[pos_split:]

    neg_split = int(len(neg_train) * 0.9)
    neg_tr  = neg_train[:neg_split]
    neg_va  = np.concatenate([neg_train[neg_split:], neg_val], axis=0)

    if is_real_speech_negatives:
        # Real speech negatives are already 16×96 windows (pre-computed by openWakeWord).
        # No windowing needed, no inflation — the HF dataset has enough rows.
        max_neg_weight = 200
        log.info("Real-speech negatives: %d train rows, %d val rows", len(neg_tr), len(neg_va))
        train_loader = make_dataloader(pos_train, neg_tr, batch_size=256, shuffle=True,
                                       neg_already_windowed=True)
        val_loader   = make_dataloader(pos_val,   neg_va, batch_size=256, shuffle=False,
                                       neg_already_windowed=True)
        # FP loader: subset of negative val rows
        fp_rows = neg_va[:min(len(neg_va), 5000)]
    else:
        # Synthetic noise: balance 1:1, inflate positives so training has enough batches.
        max_neg = min(len(neg_tr), len(pos_train) * 3)
        neg_tr  = neg_tr[:max_neg]
        neg_va  = neg_va[:max(len(pos_val) * 3, 50)]
        max_neg_weight = 3
        log.info("Synthetic negatives: %d pos, %d neg (3:1 ratio)", len(pos_train), max_neg)

        # Inflate positives to ensure enough training batches.
        win_pos = features_to_windows(pos_train)
        win_neg = features_to_windows(neg_tr)
        target  = max(len(win_neg), 5000)
        rep_pos = max(1, target // max(len(win_pos), 1))
        log.info("Inflating pos x%d (from %d to %d windows)", rep_pos, len(win_pos), len(win_pos)*rep_pos)
        pos_train = np.concatenate([pos_train] * rep_pos, axis=0)

        train_loader = make_dataloader(pos_train, neg_tr, batch_size=256, shuffle=True)
        val_loader   = make_dataloader(pos_val,   neg_va, batch_size=256, shuffle=False)
        fp_rows = features_to_windows(neg_va[:min(len(neg_va), 500)])

    X_fp   = torch.tensor(fp_rows.astype(np.float32))
    y_fp   = torch.zeros(len(X_fp), dtype=torch.float32)
    fp_loader = DataLoader(TensorDataset(X_fp, y_fp), batch_size=256, shuffle=False)

    log.info("Train batches: %d  val batches: %d  fp_val samples: %d",
             len(train_loader), len(val_loader), len(fp_loader.dataset))

    # auto_train() uses enumerate(DataLoader) which stops after one pass.
    # For small datasets we need an epoch-based loop instead.
    nn_model = model.model.to(model.device)
    optimizer = torch.optim.Adam(nn_model.parameters(), lr=1e-3)
    loss_fn   = torch.nn.BCELoss()

    best_recall  = 0.0
    best_weights = None
    n_epochs     = 150
    best_val_loss = float("inf")

    log.info("Training for %d epochs ...", n_epochs)
    for epoch in range(n_epochs):
        nn_model.train(mode=True)
        train_loss = 0.0
        for X_batch, y_batch in train_loader:
            X_batch = X_batch.to(model.device)
            y_batch = y_batch.to(model.device)
            optimizer.zero_grad()
            preds = nn_model(X_batch).squeeze(1)
            # Up-weight positive class by neg:pos ratio
            w = torch.where(y_batch == 1,
                            torch.tensor(max_neg_weight, dtype=torch.float32).to(model.device),
                            torch.tensor(1.0, dtype=torch.float32).to(model.device))
            loss = (loss_fn(preds, y_batch) * w).mean()
            loss.backward()
            optimizer.step()
            train_loss += loss.item()

        # Validation every 5 epochs
        if epoch % 5 == 0 or epoch == n_epochs - 1:
            nn_model.train(mode=False)
            all_preds, all_labels = [], []
            with torch.no_grad():
                for X_v, y_v in val_loader:
                    p = nn_model(X_v.to(model.device)).squeeze(1)
                    all_preds.append(p.cpu())
                    all_labels.append(y_v)
            preds_cat  = torch.cat(all_preds)
            labels_cat = torch.cat(all_labels)
            tp    = ((preds_cat >= 0.5) & (labels_cat == 1)).sum().item()
            fn    = ((preds_cat <  0.5) & (labels_cat == 1)).sum().item()
            recall = tp / max(tp + fn, 1)
            val_loss = loss_fn(preds_cat, labels_cat).item()
            log.info("Epoch %3d: train_loss=%.4f  val_loss=%.4f  recall=%.3f",
                     epoch, train_loss / len(train_loader), val_loss, recall)
            if recall > best_recall or (recall == best_recall and val_loss < best_val_loss):
                best_recall  = recall
                best_val_loss = val_loss
                best_weights = {k: v.clone() for k, v in nn_model.state_dict().items()}

    if best_weights is not None:
        nn_model.load_state_dict(best_weights)
        log.info("Best checkpoint restored: recall=%.3f", best_recall)
    return nn_model


# ---------------------------------------------------------------------------
# Step 5: export ONNX
# ---------------------------------------------------------------------------

def export_onnx(nn_model, output_path: Path) -> None:
    """Export PyTorch model to a single-file ONNX (inline weights, no .data sidecar)."""
    import tempfile, onnx
    nn_model.train(mode=False)
    nn_model = nn_model.to("cpu")
    dummy = torch.zeros(1, 16, 96)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp) / "model.onnx"
        with torch.no_grad():
            torch.onnx.export(
                nn_model,
                dummy,
                str(tmp_path),
                input_names=["input"],
                output_names=["output"],
                dynamic_axes={"input": {0: "batch"}, "output": {0: "batch"}},
                opset_version=12,
            )
        # Load and re-save with all weights inline (no external data sidecar)
        model = onnx.load(str(tmp_path))
        onnx.save_model(model, str(output_path), save_as_external_data=False)

    log.info("Exported single-file ONNX: %s  (%.1f KB)", output_path.name, output_path.stat().st_size / 1024)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== openWakeWord training — Mister Robot ===")

    pos_feats = compute_positive_features()
    neg_train, neg_val, is_real = get_negative_features()

    if MODEL_ONNX.exists():
        log.info("ONNX already exists at %s — delete to retrain.", MODEL_ONNX)
        return

    trained = train_model(pos_feats, neg_train, neg_val, is_real_speech_negatives=is_real)
    export_onnx(trained, MODEL_ONNX)

    log.info("")
    log.info("Next steps:")
    log.info("  1. SSH to HA (or Samba) and copy %s to /share/openwakeword/", MODEL_ONNX.name)
    log.info("  2. HA → Settings → Voice Assistants → pipeline → Wake word → 'mister_robot'")


if __name__ == "__main__":
    main()
