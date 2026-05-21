# Wyoming Voice Services (HA Container path)

If you run **Home Assistant OS** or **HA Supervised**, you don't need this — install the add-ons (Faster Whisper, Piper, openWakeWord) from the HA Add-on Store instead.

This folder is for **HA Container / HA Core** installs (no Supervisor → no add-on store). It runs the same three services as standalone Docker containers on your host, and HA connects to them via the Wyoming Protocol integration.

## Quick start (Windows / Docker Desktop)

```powershell
cd F:\ROBOTAI\infra\wyoming
docker compose up -d
docker compose ps     # all three should be "running"
```

First run will pull ~2 GB of images (Whisper model is the biggest).

## Configuration in Home Assistant

After containers are up, in HA:

**Settings → Devices & Services → Add Integration → "Wyoming Protocol"** — add it THREE TIMES:

| Service | Host | Port |
|---|---|---|
| Whisper STT | `host.docker.internal` (or your Windows LAN IP) | `10300` |
| Piper TTS | same host | `10200` |
| openWakeWord | same host | `10400` |

Each instance auto-detects which service it is.

> ℹ️ **`host.docker.internal` rule:** works if HA is also running in Docker Desktop on Windows. If HA is on a different machine (RPi, NUC, etc.), use the Windows host's LAN IP instead (e.g. `192.168.0.x`). Find your Windows IP with `ipconfig`.

Then create an Assist pipeline:

**Settings → Voice Assistants → Add Assistant**
- Name: `Robot`
- Conversation agent: **Home Assistant** (built-in intents)
  - Set **Ollama** (added separately, see below) as fallback agent
- Speech-to-text: **Wyoming Whisper**
- Text-to-speech: **Wyoming Piper**
- Wake word: **Wyoming openWakeWord** → pick "Hey Jarvis"

## Ollama integration

Separate from Wyoming. **Settings → Devices & Services → Add Integration → "Ollama"**:
- URL: `http://host.docker.internal:11434` (Ollama running on Windows host)
- Pick model: **gemma3:4b**
- "Control Home Assistant": **leave OFF** — we want Ollama as LLM fallback, not the primary intent handler.

## Customizing voices and models

### Whisper model size
Bigger = more accurate, slower. Edit `command:` in `docker-compose.yml`:
- `tiny-int8` — fastest, lower accuracy. ~75 MB.
- `small-int8` — current default. ~500 MB. Good balance.
- `medium-int8` — slower but more accurate. ~1.5 GB. Use if you have GPU.

### Piper voice
[Browse voices](https://rhasspy.github.io/piper-samples/) → swap `--voice` value. Examples:
- `en_GB-alan-medium` — British male, clear
- `en_US-amy-medium` — US female (current)
- `en_US-ryan-high` — US male, higher quality (larger model)

### Wake word
openWakeWord ships with several: `hey_jarvis`, `alexa`, `hey_mycroft`, `ok_nabu`. Change `--preload-model` to swap.

For a **custom wake word** (e.g. your robot's name), train one at <https://microwakeword.com> and run it **on-device** via ESPHome's `micro_wake_word` component instead of openWakeWord — better latency and works offline.

## Troubleshooting

**Wyoming integration can't find the service:**
- `docker compose ps` — service running?
- `docker compose logs faster-whisper` — startup errors?
- Windows Firewall blocking ports 10200/10300/10400? Add inbound rule or test with HA on the same host.

**HA says "host.docker.internal not resolvable":**
- HA is not in Docker Desktop on Windows. Use the Windows LAN IP instead.

**Whisper transcription is gibberish:**
- Wrong language. Edit `--language en` to your language code in docker-compose.yml and restart.

**Piper sounds robotic / glitchy:**
- Sample rate mismatch between Piper output and ESPHome speaker config. Verify ESPHome `speaker.sample_rate: 22050` (Piper's default).
