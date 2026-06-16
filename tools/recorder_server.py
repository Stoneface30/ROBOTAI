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
TARGET      = 100          # clips per speaker
SAMPLE_RATE = 16000        # Hz — must match microWakeWord expectation
PORT        = 8766
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

  <button id="rec-btn" disabled>&#127908;</button>

  <div style="display:flex;gap:12px;align-items:center;margin-top:-4px">
    <button id="auto-btn" disabled
      style="padding:8px 20px;border-radius:20px;border:2px solid #444;
             background:#111;color:#888;font-size:0.9rem;cursor:pointer;
             transition:all 0.15s">
      AUTO OFF
    </button>
    <button id="stop-btn" disabled
      style="padding:8px 20px;border-radius:20px;border:2px solid #ff6b6b44;
             background:#2a1a1a;color:#ff6b6b88;font-size:0.9rem;cursor:pointer;
             transition:all 0.15s">
      STOP
    </button>
  </div>

  <div id="status">Select your name to start</div>
  <div id="countdown" style="font-size:2.5rem;font-weight:700;color:#7eb8ff;
       min-height:3rem;text-align:center;line-height:3rem"></div>

  <div class="done-banner" id="done-banner">
    <h2>All done!</h2>
    <p>You recorded all __TARGET__ clips.<br>
       Let another family member take a turn!</p>
  </div>

  <div class="tips">
    <b>How to use AUTO mode:</b><br>
    1. Select your name &nbsp;2. Tap AUTO ON &nbsp;3. Tap the mic once<br>
    It records 1.8 s, saves, counts down 2 s, then records again automatically.<br>
    Just keep saying <b>"__WAKE_WORD__"</b> every 4 seconds. Tap STOP when done.<br><br>
    <b>Tips:</b> vary your distance (close / across the room) &bull;
    vary your speed slightly &bull; background noise ~20% of clips is fine
  </div>

  <script>
  const WAKE_WORD   = "__WAKE_WORD__";
  const TARGET      = __TARGET__;
  const GAP_MS      = 2000;   // pause between auto clips (ms)
  const REC_MS      = 1800;   // recording window (ms)

  let speaker   = null;
  let count     = 0;
  let autoMode  = false;
  let running   = false;      // true while auto loop is active
  let stopFlag  = false;

  const recBtn   = document.getElementById("rec-btn");
  const autoBtn  = document.getElementById("auto-btn");
  const stopBtn  = document.getElementById("stop-btn");
  const status   = document.getElementById("status");
  const pbar     = document.getElementById("pbar");
  const plabel   = document.getElementById("plabel");
  const countdown= document.getElementById("countdown");
  const doneBanner = document.getElementById("done-banner");

  // ── speaker selection ─────────────────────────────────────────────────────
  document.querySelectorAll(".sp-btn").forEach(btn => {
    btn.addEventListener("click", async () => {
      if (running) return;
      document.querySelectorAll(".sp-btn").forEach(b => b.classList.remove("active"));
      btn.classList.add("active");
      speaker = btn.dataset.speaker;
      const res  = await fetch(`/count?speaker=${encodeURIComponent(speaker)}`);
      const data = await res.json();
      count = data.count;
      updateProgress();
      if (count >= TARGET) { showDone(); return; }
      recBtn.disabled = false;
      autoBtn.disabled = false;
      status.textContent = "Ready — tap the mic, or turn AUTO ON first";
      status.className = "";
    });
  });

  // ── auto toggle ───────────────────────────────────────────────────────────
  autoBtn.addEventListener("click", () => {
    if (running) return;
    autoMode = !autoMode;
    autoBtn.textContent  = autoMode ? "AUTO ON"  : "AUTO OFF";
    autoBtn.style.borderColor = autoMode ? "#7eb8ff" : "#444";
    autoBtn.style.color       = autoMode ? "#7eb8ff" : "#888";
    status.textContent = autoMode
      ? "AUTO ON — tap the mic to start, it will loop automatically"
      : "AUTO OFF — tap the mic for one clip at a time";
    status.className = "";
  });

  // ── stop button ───────────────────────────────────────────────────────────
  stopBtn.addEventListener("click", () => { stopFlag = true; });

  // ── progress ──────────────────────────────────────────────────────────────
  function updateProgress() {
    const pct = Math.min(100, (count / TARGET) * 100);
    pbar.style.width = pct + "%";
    plabel.textContent = `${count} / ${TARGET} clips`;
  }

  function showDone() {
    running = false;
    recBtn.disabled = true;
    autoBtn.disabled = true;
    stopBtn.disabled = true;
    doneBanner.style.display = "block";
    countdown.textContent = "";
    status.textContent = "All done!";
    status.className = "ok";
  }

  function setUIBusy(busy) {
    recBtn.disabled  = busy && !autoMode;   // in auto mode rec-btn stays for "stop"
    autoBtn.disabled = busy;
    stopBtn.disabled = !busy;
    document.querySelectorAll(".sp-btn").forEach(b => b.disabled = busy);
  }

  // ── record one clip, returns true if saved OK ─────────────────────────────
  async function recordOne() {
    let stream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: {
        sampleRate: 16000, channelCount: 1,
        echoCancellation: false, noiseSuppression: false, autoGainControl: false
      }});
    } catch {
      status.textContent = "Mic access denied — check browser permissions";
      status.className = "err";
      return false;
    }

    return new Promise(resolve => {
      const chunks = [];
      const rec = new MediaRecorder(stream, { mimeType: "audio/webm" });
      rec.ondataavailable = e => { if (e.data.size > 0) chunks.push(e.data); };

      rec.onstop = async () => {
        stream.getTracks().forEach(t => t.stop());
        recBtn.classList.remove("recording");
        status.textContent = "Saving…";
        status.className = "";
        countdown.textContent = "";

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
            status.textContent = "Saved " + count + " / " + TARGET;
            status.className = "ok";
            resolve(true);
          } else {
            status.textContent = "Error: " + data.error;
            status.className = "err";
            resolve(false);
          }
        } catch {
          status.textContent = "Upload failed — check WiFi";
          status.className = "err";
          resolve(false);
        }
      };

      recBtn.classList.add("recording");
      status.textContent = 'Say "' + WAKE_WORD + '"';
      status.className = "rec";
      countdown.textContent = "";
      rec.start();
      setTimeout(() => { if (rec.state === "recording") rec.stop(); }, REC_MS);
    });
  }

  // ── countdown helper ──────────────────────────────────────────────────────
  function sleep(ms) { return new Promise(r => setTimeout(r, ms)); }

  async function countdownTo(ms) {
    const steps = Math.round(ms / 1000);
    for (let i = steps; i >= 1; i--) {
      if (stopFlag) return;
      countdown.textContent = i;
      await sleep(1000);
    }
    countdown.textContent = "";
  }

  // ── main record button ────────────────────────────────────────────────────
  recBtn.addEventListener("click", async () => {
    if (!speaker || running) return;
    running = true;
    stopFlag = false;
    setUIBusy(true);

    if (autoMode) {
      // AUTO LOOP
      while (!stopFlag && count < TARGET) {
        const ok = await recordOne();
        if (!ok || stopFlag || count >= TARGET) break;
        await countdownTo(GAP_MS);
      }
      running = false;
      stopFlag = false;
      setUIBusy(false);
      if (count >= TARGET) { showDone(); return; }
      status.textContent = "Stopped — tap mic to continue";
      status.className = "";
      countdown.textContent = "";
    } else {
      // SINGLE CLIP
      await recordOne();
      running = false;
      setUIBusy(false);
      if (count >= TARGET) showDone();
    }
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

    # TLS cert paths — generated once by: python tools/gen_cert.py
    cert = Path(__file__).parent / "cert.pem"
    key  = Path(__file__).parent / "key.pem"
    use_https = cert.exists() and key.exists()
    scheme = "https" if use_https else "http"

    print(f"\n  [ROBOT] Wake Word Recorder")
    print(f"  Wake word : \"{WAKE_WORD}\"")
    print(f"  Speakers  : {', '.join(SPEAKERS)}")
    print(f"  Target    : {TARGET} clips each")
    print()
    print(f"  Open on any phone/tablet on your WiFi:")
    print(f"  >>  {scheme}://{lan_ip}:{PORT}")
    if not use_https:
        print("  [WARN] No cert.pem found — serving HTTP. Phone mic will be blocked by Chrome.")
        print("         Run: python tools/gen_cert.py  then restart.")
    else:
        print("  [HTTPS] Self-signed cert active.")
        print(f"  On first visit: tap 'Advanced' -> 'Proceed to {lan_ip}' to accept the cert.")
    print()
    print("  Ctrl+C to stop\n")

    kwargs = dict(host="0.0.0.0", port=PORT, log_level="warning")
    if use_https:
        kwargs["ssl_certfile"] = str(cert)
        kwargs["ssl_keyfile"]  = str(key)
    uvicorn.run(app, **kwargs)
