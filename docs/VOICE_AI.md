# Voice AI Stack — Decision & Migration Plan

> **Recommendation (chosen after research, 2026-05-21):** ESPHome `voice_assistant` component → Wyoming protocol → Home Assistant Assist → Whisper STT + Piper TTS + Ollama as LLM fallback. The DualEye becomes an HA Voice Satellite. xiaozhi-esp32 is retained on OTA slot B as a fallback only.

## Why this stack, not the others

The DualEye's audio chain (ES8311 codec + ES7210 4-mic TDM ADC, I2S on GPIO12/13/14/15/16, PA enable on GPIO9) is **identical** to the Waveshare ESP32-S3-Audio-Board, for which a community ESPHome reference exists with proven wake-word + mic + speaker working simultaneously:

- Working reference: <https://github.com/sw3Dan/waveshare-s2-audio_esphome_voice>
- HA community thread: <https://community.home-assistant.io/t/waveshare-s3-audio-board-esphome-voiceassistant/932316>

This collapses two of the four candidates (HA Wyoming Satellite firmware and ESPHome `voice_assistant`) into one path — they're the same firmware. The remaining two candidates were rejected:

- **Willow** — only supports ESP32-S3-BOX hardware (ES7210 alone, no ES8311). No board profile for our codec combo. <https://heywillow.io/hardware/>
- **xiaozhi-stripped** — would require re-implementing on-device Opus encoding, custom WebSocket protocol, server-side STT/TTS/LLM glue, and HA bridge. Reinvents what HA Assist gives for free. xiaozhi's Opus-over-WS protocol also requires a firmware recompile to change the server URL — not pluggable. <https://github.com/78/xiaozhi-esp32/blob/main/docs/websocket.md>

## Comparison table

| Criteria | (1) HA Wyoming Satellite | (2) Willow | (3) ESPHome voice_assistant | (4) xiaozhi-stripped |
|---|---|---|---|---|
| Setup effort (hrs) | 4–6 | N/A | **3–5** | 15–25 |
| HA integration | 5 (native intents) | 4 (REST) | **5 (native)** | 2 (DIY bridge) |
| LLM fallback | 5 (Assist → Ollama) | 3 (manual) | **5** | 5 (total control) |
| Wake word | 5 (microWakeWord + custom) | 4 (Espressif fixed) | **5** | 4 |
| TTS quality | 5 (Piper, swappable to XTTS) | 3 (Piper locked) | **5** | 5 (you choose) |
| End-to-end latency | 4 (~1.2–2 s) | 4 | **4** | 3 |
| DualEye HW compat (ES8311+ES7210) | 3 (needs sw3Dan patch) | **1** (no support) | **3** (same patch) | 5 (already boots) |
| LVGL eyes coexistence | 3 (RAM tight) | 1 | 3 | **4** (already works) |
| Project momentum | 5 (Nabu Casa core) | 2 (slow) | **5** | 4 (active CN community) |

## Architecture

```
            Wake word            Wyoming protocol             HA Assist
   user ──> mic ──> ESP32-S3 ───────────────────> Home Assistant ──┐
                    (ESPHome,                                       │
                    DualEye)                                        ▼
                                                              ┌──────────┐
                                                              │ STT      │ faster-whisper add-on
                                                              │          │
                                                              ▼          │
                                                          ┌───────┐      │
                                                          │ HA    │ try local intent first
                                                          │ Assist│ (lights, sensors, scripts)
                                                          └───┬───┘      │
                                                              │          │
                                                       intent │  no match│
                                                              │  ▼       │
                                                              │ ┌──────┐ │
                                                              │ │Ollama│ │ qwen2.5:7b (sweet spot)
                                                              │ │ LLM  │ │
                                                              │ └──┬───┘ │
                                                              │    │     │
                                                              ▼    ▼     │
                                                          ┌───────────┐  │
                                                          │   Piper   │  │  TTS
                                                          └─────┬─────┘  │
                                                                │        │
                                                                ▼        │
                          audio ◄── ESP32-S3 ◄── Wyoming ◄──────┘        │
                                    speaker
```

The intent-routing the user asked for ("if it's HA execute it, if it's a question answer it") is **built into HA Assist** — no custom code needed. Set the conversation agent chain to: HA Assist (handles light/sensor/script intents) → Ollama fallback (handles general Q&A).

## Hardware compatibility — the ES8311+ES7210 gotcha

Vanilla ESPHome ships both components:
- <https://esphome.io/components/audio_dac/es8311/>
- <https://esphome.io/components/audio_adc/es7210/>

ES7210 natively handles the 4-mic TDM array. **The known patch**: stock ES8311 component is hardcoded as I2S slave, which conflicts when ES7210 also wants slave mode on the same bus. The sw3Dan fork patches ES8311 to optionally be I2S master and shares MCLK on GPIO12 — matches our exact pinout. The patch is ~100 lines.

## Migration path

1. **Keep xiaozhi on OTA slot B as fallback** — don't wipe what works. Switch slots via `idf.py erase-otadata` if the ESPHome build fails.
2. **Fork `sw3Dan/waveshare-s2-audio_esphome_voice`** to our account; rename YAML for `esp32-s3-dualeye`. Verify I2S/I2C pin map — they match.
3. **Add two `gc9a01a` displays + LVGL** to the YAML so the eyes survive the firmware swap. Budget PSRAM: voice pipeline ≈ 2 MB, eyes ≈ 1 MB, plenty of room in 8 MB.
4. **Install HA add-ons**:
   - `faster-whisper` (medium-int8 — fast enough on CPU)
   - `piper` (or wire Wyoming to XTTS-v2 / Kokoro on the GPU later)
   - `openWakeWord` server-side, OR `micro_wake_word` on-device (lower latency, custom training at <https://microwakeword.com>)
5. **HA Assist pipeline config**: STT = faster-whisper, conversation agent = HA Assist (default) **with Ollama as fallback** for the "prefer handling commands locally, fallback to external" toggle. **Ollama model: `gemma3:4b`** (user choice, 2026-05-21) — Gemma 3 4B parameters, fast first-token on most GPUs, good general Q&A quality. Newer `gemma4:e4b` is also loaded locally if we want to compare. 7B-class and larger are too slow for live voice.
6. **Flash via `esphome run` over USB-C**, then OTA after.
7. **Validation tests**:
   - Wake word → "turn on the kitchen lights" → HA executes (no LLM)
   - Wake word → "what's the capital of Mongolia" → Ollama responds via TTS

## Open risks (worth knowing before commit)

- **PSRAM pressure with both eyes + voice pipeline running simultaneously** — untested combo on this exact board. Mitigation: drop eyes to 15 fps during active conversation, or blank one eye and use the other as a VU meter.
- **sw3Dan fork is single-maintainer, 19 commits** — bus factor 1. Mitigation: vendor the ES8311 patch into our own fork rather than relying on theirs.
- **ES7210 4-mic beamforming** — ESPHome's component exposes 4 channels but does **not** do AEC or beamforming. Acceptable in a quiet room, weak in a noisy one. xiaozhi has onboard AEC; ESPHome does not. If noise becomes a problem, consider porting xiaozhi's AEC as a custom component.
- **Ollama latency** — `qwen2.5:7b` first-token is ~400 ms on a decent GPU, ~2 s on CPU. Benchmark before committing.
- **WiFi 2.4 GHz only** — DualEye has no 5 GHz radio. If the 2.4 band is congested, Wyoming audio will drop. Non-negotiable.

## What stays from xiaozhi-esp32

Nothing in the long run. The xiaozhi build is kept on OTA slot B purely as a "known good" fallback while the ESPHome path is brought up. Once ESPHome + HA Assist + Ollama is verified end-to-end, the xiaozhi slot can be wiped.

## Sources

- [ESPHome voice_assistant component](https://esphome.io/components/voice_assistant/)
- [ESPHome ES8311 audio_dac](https://esphome.io/components/audio_dac/es8311/)
- [ESPHome ES7210 audio_adc](https://esphome.io/components/audio_adc/es7210/)
- [ESPHome i2s_audio microphone](https://esphome.io/components/microphone/i2s_audio/)
- [ESPHome micro_wake_word](https://esphome.io/components/micro_wake_word/)
- [microWakeWord training tool](https://microwakeword.com/)
- [Waveshare ESP32-S3-DualEye-Touch-LCD-1.28 wiki](https://www.waveshare.com/wiki/ESP32-S3-DualEye-Touch-LCD-1.28)
- [HA community: Waveshare S3 audio board ESPHome VoiceAssistant](https://community.home-assistant.io/t/waveshare-s3-audio-board-esphome-voiceassistant/932316)
- [sw3Dan working ESPHome reference](https://github.com/sw3Dan/waveshare-s2-audio_esphome_voice)
- [HA Assist conversation agents docs](https://www.home-assistant.io/voice_control/voice_remote_local_assistant/)
- [Ollama HA integration](https://www.home-assistant.io/integrations/ollama/)
- [xiaozhi-esp32 WebSocket protocol (for context, not chosen)](https://github.com/78/xiaozhi-esp32/blob/main/docs/websocket.md)
- [Willow hardware support (rejected)](https://heywillow.io/hardware/)
