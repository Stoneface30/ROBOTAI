"""
record_wake_word.py — Capture 500 wake-word clips per speaker for microWakeWord training.

USAGE
-----
  pip install sounddevice soundfile numpy rich
  python tools/record_wake_word.py --speaker "Dad" --word "Mister Robot"

This creates:
  tools/recordings/mister_robot/Dad/0001.wav
  tools/recordings/mister_robot/Dad/0002.wav
  ...
  tools/recordings/mister_robot/Dad/0500.wav

Run once per family member. All recordings land in the same folder structure
that the microWakeWord training notebook expects.

TRAINING AFTER RECORDING
------------------------
1. Open the microWakeWord training Colab notebook:
   https://github.com/kahrendt/microWakeWord#training

2. Upload the recordings/ folder (zip it first):
   cd tools && zip -r mister_robot_recordings.zip recordings/mister_robot/

3. Follow the notebook — it generates:
     stream_state_internal_quant.tflite   ← the model
     mister_robot.json                    ← ESPHome manifest

4. Host both files on GitHub (create a public repo or use a raw gist):
   The .json must reference the .tflite by relative path or raw URL.

5. In esphome/dualeye.yaml, replace the okay_nabu line with:
     - model: github://YOUR_USER/YOUR_REPO/models/mister_robot.json
       id: mister_robot

6. esphome run esphome/dualeye.yaml

TIPS FOR GOOD RECORDINGS
--------------------------
- Say "Mister Robot" naturally — vary your pace slightly each time
- Move around slightly: sitting, standing, different distances (0.5m–2m)
- Record in the room where the robot lives most of the time
- Don't shout or whisper — normal conversational volume
- It's OK (good, even) to have background TV / music on for ~20% of clips
- Each clip is auto-trimmed to 1.5 s; silence before/after is fine
- If you fluff a recording, press SPACE to redo it immediately
"""

import argparse
import os
import re
import sys
import time
from pathlib import Path

try:
    import numpy as np
    import sounddevice as sd
    import soundfile as sf
    from rich.console import Console
    from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
except ImportError:
    print("Missing dependencies. Run:  pip install sounddevice soundfile numpy rich")
    sys.exit(1)

# ── constants ──────────────────────────────────────────────────────────────────
SAMPLE_RATE   = 16000   # microWakeWord expects 16 kHz mono
CLIP_DURATION = 1.5     # seconds per clip (covers "Mister Robot" with margin)
TARGET_CLIPS  = 500
SILENCE_THRESH = 0.005  # RMS below this → clip is silent, warn and offer redo

console = Console()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", text.lower()).strip("_")


def rms(audio: np.ndarray) -> float:
    return float(np.sqrt(np.mean(audio ** 2)))


def record_clip(duration: float, sr: int) -> np.ndarray:
    """Block until a clip of `duration` seconds is recorded."""
    samples = int(duration * sr)
    audio = sd.rec(samples, samplerate=sr, channels=1, dtype="float32")
    sd.wait()
    return audio.flatten()


def save_clip(audio: np.ndarray, path: Path, sr: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(path), audio, sr, subtype="PCM_16")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record wake-word training clips")
    parser.add_argument("--speaker", required=True, help='Speaker name, e.g. "Dad"')
    parser.add_argument("--word",    default="Mister Robot",
                        help='Wake word phrase (default: "Mister Robot")')
    parser.add_argument("--target",  type=int, default=TARGET_CLIPS,
                        help=f"Number of clips to record (default: {TARGET_CLIPS})")
    parser.add_argument("--out",     default="tools/recordings",
                        help="Output base directory (default: tools/recordings)")
    args = parser.parse_args()

    word_slug    = slugify(args.word)
    speaker_slug = slugify(args.speaker)
    out_dir      = Path(args.out) / word_slug / speaker_slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # find highest existing clip number so we can resume
    existing = sorted(out_dir.glob("*.wav"))
    start_n  = len(existing) + 1

    if start_n > args.target:
        console.print(f"[green]Already have {len(existing)} clips for "
                      f"{args.speaker} — nothing to do![/green]")
        return

    console.rule(f"[bold cyan]Wake Word Recorder[/bold cyan]")
    console.print(f"  Speaker : [bold]{args.speaker}[/bold]")
    console.print(f"  Phrase  : [bold yellow]\"{args.word}\"[/bold yellow]")
    console.print(f"  Target  : [bold]{args.target}[/bold] clips")
    console.print(f"  Done    : [bold]{start_n - 1}[/bold] clips already saved")
    console.print(f"  Saving  : [dim]{out_dir}[/dim]")
    console.print()
    console.print("Press [bold]ENTER[/bold] to start each recording. "
                  "Press [bold]SPACE + ENTER[/bold] to redo the last clip. "
                  "Press [bold]q + ENTER[/bold] to quit and save progress.")
    console.print()

    n = start_n
    redo = False

    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Recording for {args.speaker}",
            total=args.target,
            completed=start_n - 1,
        )

        while n <= args.target:
            clip_path = out_dir / f"{n:04d}.wav"
            label = "[yellow]REDO[/yellow]" if redo else f"Clip [cyan]{n}/{args.target}[/cyan]"

            try:
                key = console.input(f"  {label}  — say [bold yellow]\"{args.word}\"[/bold yellow]  → ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                console.print("\n[dim]Interrupted — progress saved.[/dim]")
                break

            if key == "q":
                console.print("[dim]Quitting — progress saved.[/dim]")
                break

            # countdown
            for i in (3, 2, 1):
                console.print(f"    [bold red]{i}...[/bold red]", end="\r")
                time.sleep(0.35)
            console.print("    [bold green]RECORDING[/bold green]", end="\r")

            audio = record_clip(CLIP_DURATION, SAMPLE_RATE)

            clip_rms = rms(audio)
            if clip_rms < SILENCE_THRESH:
                console.print(f"    [red]⚠ Too quiet (RMS {clip_rms:.4f}) — "
                               "press ENTER to redo[/red]")
                redo = True
                continue

            if key == " ":
                # redo: overwrite the last saved clip
                n_redo = max(1, n - 1)
                redo_path = out_dir / f"{n_redo:04d}.wav"
                save_clip(audio, redo_path, SAMPLE_RATE)
                console.print(f"    [yellow]Replaced clip {n_redo}[/yellow]")
                redo = False
                continue

            save_clip(audio, clip_path, SAMPLE_RATE)
            console.print(f"    [green]✓ saved[/green]  (RMS {clip_rms:.3f})")
            progress.advance(task)
            redo = False
            n += 1

    saved = len(list(out_dir.glob("*.wav")))
    console.rule()
    console.print(f"[bold green]Done — {saved}/{args.target} clips saved "
                  f"for {args.speaker}[/bold green]")
    console.print(f"[dim]Path: {out_dir.resolve()}[/dim]")

    if saved >= args.target:
        console.print()
        console.print("[bold]All clips recorded! Next steps:[/bold]")
        console.print("  1. Run for each other family member:")
        console.print(f'       python tools/record_wake_word.py --speaker "NAME" --word "{args.word}"')
        console.print()
        console.print("  2. Zip the recordings folder:")
        console.print(f"       cd tools && zip -r {word_slug}_recordings.zip recordings/{word_slug}/")
        console.print()
        console.print("  3. Upload to microWakeWord training notebook:")
        console.print("       https://github.com/kahrendt/microWakeWord#training")
        console.print()
        console.print("  4. Update esphome/dualeye.yaml with the trained model URL")


if __name__ == "__main__":
    main()
