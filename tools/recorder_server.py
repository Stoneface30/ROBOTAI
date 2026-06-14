"""
recorder_server.py — LAN web server for collecting wake-word training clips.

Family members open http://<YOUR-PC-IP>:8765 on any phone/tablet/browser
on the same WiFi network, pick their name, and tap the button to record.
All clips save automatically to:
  tools/recordings/mister_robot/<speaker>/<NNNN>.wav

USAGE
-----
  pip install fastapi uvicorn python-multipart
  python tools/recorder_server.py

Then on any device on your LAN:
  http://192.168.0.10:8765          ← replace with your PC's LAN IP
  (shown in the console when the server starts)

WAKE WORD / SPEAKERS
--------------------
Edit WAKE_WORD and SPEAKERS below, then restart the server.
"""

import io
import os
import socket
import struct
import wave
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

# ── config ────────────────────────────────────────────────────────────────────
WAKE_WORD   = "Mister Robot"
TARGET      = 500          # clips per speaker
SAMPLE_RATE = 16000        # Hz — must match microWakeWord expectation
PORT        = 8765
OUT_BASE    = Path(__file__).parent / "recordings"

SPEAKERS = [
    "Dad",
    "Mum",
    "Kid1",
    "Kid2",
    # add more as needed
]
# ─────────────────────────────────────────────────────────────────────────────

app = FastAPI()


def slug(text: str) -> str:
    import re
    return re.sub(r"[^a-z0-9_]", "_", text.lower()).strip("_")


def clip_dir(speaker: str) -> Path:
    return OUT_BASE / slug(WAKE_WORD) / slug(speaker)


def next_clip_number(speaker: str) -> int:
    d = clip_dir(speaker)
    if not d.exists():
        return 1
    existing = list(d.glob("*.wav"))
    return len(existing) + 1


def get_lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


# ── HTML page ─────────────────────────────────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1">
<title>Mister Robot — Wake Word Recorder</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #0a0a0f;
    color: #e8e8f0;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 24px 16px;
    gap: 20px;
  }
  h1 { font-size: 1.5rem; color: #7eb8ff; letter-spacing: 0.05em; }
  .sub { font-size: 0.85rem; color: #666; }
  .phrase {
    font-size: 2rem; font-weight: 700;
    color: #fff;
    background: #1a1a2e;
    border: 2px solid #7eb8ff44;
    border-radius: 16px;
    padding: 16px 32px;
    text-align: center;
    letter-spacing: 0.04em;
  }
  .speaker-grid {
    display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;
    max-width: 400px;
  }
  .sp-btn {
    padding: 10px 20px; border-radius: 24px; border: 2px solid #333;
    background: #1a1a2e; color: #aaa; font-size: 1rem; cursor: pointer;
    transition: all 0.15s;
  }
  .sp-btn.active {
    border-color: #7eb8ff; color: #fff; background: #1a2a4a;
  }
  .progress-wrap { width: 100%; max-width: 360px; }
  .progress-bar-bg {
    height: 10px; background: #1a1a2e; border-radius: 8px; overflow: hidden;
  }
  .progress-bar { height: 100%; background: #7eb8ff; border-radius: 8px;
    transition: width 0.3s; }
  .progress-label { font-size: 0.85rem; color: #888; text-align: center;
    margin-top: 6px; }
  #rec-btn {
    width: 140px; height: 140px; border-radius: 50%;
    border: none; font-size: 3rem; cursor: pointer;
    background: #1a2a4a; color: #7eb8ff;
    box-shadow: 0 0 0 4px #7eb8ff44;
    transition: all 0.15s;
    display: flex; align-items: center; justify-content: center;
  }
  #rec-btn:disabled { opacity: 0.35; cursor: not-allowed; }
  #rec-btn.recording {
    background: #2a1a1a; color: #ff6b6b;
    box-shadow: 0 0 0 4px #ff6b6b88, 0 0 30px #ff6b6b44;
    animation: pulse 0.8s ease-in-out infinite;
  }
  @keyframes pulse {
    0%,100% { box-shadow: 0 0 0 4px #ff6b6b88, 0 0 20px #ff6b6b33; }
    50%      { box-shadow: 0 0 0 8px #ff6b6b55, 0 0 40px #ff6b6b66; }
  }
  #status {
    font-size: 0.9rem; color: #888; min-height: 1.2em; text-align: center;
  }
  #status.ok  { color: #6ddc8b; }
  #status.err { color: #ff6b6b; }
  #status.rec { color: #ff6b6b; }
  .tips {
    max-width: 360px; background: #111120; border-radius: 12px;
    padding: 14px 18px; font-size: 0.8rem; color: #666; line-height: 1.7;
  }
  .tips b { color: #aaa; }
  .done-banner {
    display: none; background: #0d2a1a; border: 2px solid #6ddc8b;
    border-radius: 16px; padding: 20px 28px; text-align: center;
    max-width: 360px;
  }
  .done-banner h2 { color: #6ddc8b; margin-bottom: 8px; }
  .done-banner p  { font-size: 0.85rem; color: #aaa; line-height: 1.6; }
</style>
</head>
<body>
  <h1>🤖 Wake Word Recorder</h1>
  <p class="sub">Recording for: <strong>__WAKE_WORD__</strong></p>

  <div class="phrase">"__WAKE_WORD__"</div>

  <div class="speaker-grid" id="speaker-grid">
    __SPEAKER_BUTTONS__
  </div>

  <div class="progress-wrap">
    <div class="progress-bar-bg">
      <div class="progress-bar" id="pbar" style="width:0%"></div>
    </div>
    <div class="progress-label" id="plabel">Select your name above</div>
  </div>

  <button id="rec-btn" disabled title="Tap to record">🎙️</button>
  <div id="status">Select your name to start</div>

  <div class="done-banner" id="done-banner">
    <h2>✅ All done!</h2>
    <p>You've recorded all __TARGET__ clips.<br>
       Let another family member take a turn!</p>
  </div>

  <div class="tips">
    <b>Tips for great recordings:</b><br>
    • Say the phrase at normal volume<br>
    • Vary your speed slightly each time<br>
    • Move around — try from 0.5m and 2m away<br>
    • It's fine if there's background noise some of the time<br>
    • Tap REDO below the button if you fluffed a clip
  </div>

  <script>
  const WAKE_WORD = "__WAKE_WORD__";
  const TARGET    = __TARGET__;
  let speaker  = null;
  let count    = 0;
  let mediaRec = null;
  let chunks   = [];
  let stream   = null;
  let canRedo  = false;

  const recBtn   = document.getElementById("rec-btn");
  const status   = document.getElementById("status");
  const pbar     = document.getElementById("pbar");
  const plabel   = document.getElementById("plabel");
  const doneBanner = document.getElementById("done-banner");

  // ── speaker selection ────────────────────────────────────────────────────
  document.querySelectorAll(".sp-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      document.querySelectorAll(".sp-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      speaker = btn.dataset.speaker;
      const res = await fetch(`/count?speaker=${encodeURIComponent(speaker)}`);
      const data = await res.json();
      count = data.count;
      updateProgress();
      if (count >= TARGET) {
        showDone();
      } else {
        recBtn.disabled = false;
        status.textContent = "Tap the mic and say the phrase";
        status.className = "";
      }
    });
  });

  // ── progress ─────────────────────────────────────────────────────────────
  function updateProgress() {
    const pct = Math.min(100, (count / TARGET) * 100);
    pbar.style.width = pct + "%";
    plabel.textContent = `${count} / ${TARGET} clips`;
  }

  function showDone() {
    recBtn.disabled = true;
    doneBanner.style.display = "block";
    status.textContent = "All done! 🎉";
    status.className = "ok";
  }

  // ── recording ─────────────────────────────────────────────────────────────
  recBtn.addEventListener("click", async () => {
    if (!speaker) return;
    if (mediaRec && mediaRec.state === "recording") return;

    // request mic
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: {
        sampleRate: 16000, channelCount: 1, echoCancellation: false,
        noiseSuppression: false, autoGainControl: false
      }});
    } catch (e) {
      status.textContent = "Mic access denied — check browser permissions";
      status.className = "err";
      return;
    }

    chunks = [];
    mediaRec = new MediaRecorder(stream, { mimeType: "audio/webm" });
    mediaRec.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };

    mediaRec.onstop = async () => {
      stream.getTracks().forEach(t => t.stop());
      recBtn.textContent = "🎙️";
      recBtn.classList.remove("recording");
      status.textContent = "Saving…";
      status.className = "";

      const blob = new Blob(chunks, { type: "audio/webm" });
      const form = new FormData();
      form.append("audio", blob, "clip.webm");
      form.append("speaker", speaker);

      try {
        const res  = await fetch("/upload", { method: "POST", body: form });
        const data = await res.json();
        if (data.ok) {
          count = data.count;
          updateProgress();
          canRedo = true;
          status.textContent = `✓ Clip ${count} saved`;
          status.className = "ok";
          if (count >= TARGET) { showDone(); }
        } else {
          status.textContent = "Error: " + data.error;
          status.className = "err";
        }
      } catch (e) {
        status.textContent = "Upload failed — are you on the right network?";
        status.className = "err";
      }

      recBtn.disabled = false;
    };

    // record for 1.8s then stop
    recBtn.textContent = "⏹";
    recBtn.classList.add("recording");
    recBtn.disabled = true;
    status.textContent = `🔴 Say "${WAKE_WORD}"…`;
    status.className = "rec";

    mediaRec.start();
    setTimeout(() => { if (mediaRec.state === "recording") mediaRec.stop(); }, 1800);
  });
  </script>
</body>
</html>
"""


def build_html() -> str:
    buttons = "\n    ".join(
        f'<button class="sp-btn" data-speaker="{sp}">{sp}</button>'
        for sp in SPEAKERS
    )
    return (HTML
            .replace("__WAKE_WORD__", WAKE_WORD)
            .replace("__SPEAKER_BUTTONS__", buttons)
            .replace("__TARGET__", str(TARGET)))


# ── endpoints ─────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    return build_html()


@app.get("/count")
async def count_clips(speaker: str):
    d = clip_dir(speaker)
    n = len(list(d.glob("*.wav"))) if d.exists() else 0
    return {"count": n}


@app.post("/upload")
async def upload_clip(audio: UploadFile, speaker: str = Form(...)):
    if speaker not in SPEAKERS:
        raise HTTPException(400, "Unknown speaker")

    raw = await audio.read()

    # Convert webm → 16kHz mono PCM WAV via ffmpeg
    import subprocess, tempfile
    with tempfile.NamedTemporaryFile(suffix=".webm", delete=False) as tmp_in:
        tmp_in.write(raw)
        tmp_in_path = tmp_in.name

    d = clip_dir(speaker)
    d.mkdir(parents=True, exist_ok=True)
    n = next_clip_number(speaker)
    out_path = d / f"{n:04d}.wav"

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", tmp_in_path,
                "-ar", str(SAMPLE_RATE), "-ac", "1",
                "-sample_fmt", "s16",
                str(out_path)
            ],
            capture_output=True, timeout=10
        )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.decode())
    except FileNotFoundError:
        # ffmpeg not found — try saving raw webm and warn
        out_path.write_bytes(raw)
        return JSONResponse({
            "ok": True,
            "count": n,
            "warn": "ffmpeg not found — saved raw webm. Install ffmpeg for proper WAV conversion."
        })
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)})
    finally:
        os.unlink(tmp_in_path)

    return JSONResponse({"ok": True, "count": n})


# ── main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    lan_ip = get_lan_ip()
    print(f"\n  🤖  Wake Word Recorder")
    print(f"  Wake word : \"{WAKE_WORD}\"")
    print(f"  Speakers  : {', '.join(SPEAKERS)}")
    print(f"  Target    : {TARGET} clips each")
    print()
    print(f"  Open on any device on your WiFi:")
    print(f"  ➜  http://{lan_ip}:{PORT}")
    print(f"  ➜  http://localhost:{PORT}  (this PC only)")
    print()
    print("  Ctrl+C to stop\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT, log_level="warning")
