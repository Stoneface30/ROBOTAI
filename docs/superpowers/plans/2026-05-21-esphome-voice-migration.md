# ESPHome Voice Assistant Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the xiaozhi-esp32 firmware on the Waveshare DualEye with an ESPHome-based voice satellite that speaks Wyoming to Home Assistant. Wake word → HA Assist → if matches local intent execute via HA, else fallback to Ollama (`gemma3:4b`).

**Architecture:** ESP32-S3-DualEye runs ESPHome firmware (`voice_assistant` component + `micro_wake_word`). Audio chain on ES8311 (DAC) + ES7210 (4-mic ADC, ESPHome native components, ES8311 master-mode patched via sw3Dan fork). Wyoming protocol carries audio to HA. HA Assist runs faster-whisper (STT) + Piper (TTS) + conversation chain (HA intents first, then Ollama fallback). LVGL eyes (two GC9A01A displays) added to the same ESPHome YAML so the face survives the firmware swap.

**Tech Stack:** ESPHome 2026.x (current latest), ESP-IDF 5.x toolchain, Home Assistant 2026.x add-ons (faster-whisper, piper, openwakeword OR micro_wake_word on-device), Ollama running locally on the Windows 11 host with `gemma3:4b` loaded.

---

## File Structure

| File | Role | Created/Modified |
|------|------|------------------|
| `esphome/dualeye_voice.yaml` | New ESPHome config for DualEye voice satellite | Create |
| `esphome/secrets.yaml` | API key + WiFi creds (gitignored, exists) | Modify |
| `esphome/components/es8311_master/` | Vendored ES8311 master-mode patch (from sw3Dan) | Create |
| `esphome/components/dualeye_face/` | Custom LVGL component for 2× GC9A01A eyes | Create |
| `docs/VOICE_AI.md` | Decision doc (already written) | Reference |
| `homeassistant/configuration.yaml` | Notes on HA Assist pipeline + Ollama agent | Reference (HA side, not in repo) |

---

## Task 1: HA-Side Setup (User Steps + Verification)

This block runs on the Windows 11 host. User does the clicks; we verify via the HA REST API.

**Files:**
- Modify: nothing in repo
- Verify: HA add-ons installed + Assist pipeline configured

- [ ] **Step 1.1: User starts Wyoming Docker services**

  HA install is HA Container — no Supervisor, no add-on store. Run the three Wyoming services as standalone Docker containers via `F:\ROBOTAI\infra\wyoming\docker-compose.yml`:

  ```powershell
  cd F:\ROBOTAI\infra\wyoming
  docker compose up -d
  docker compose ps    # whisper(10300), piper(10200), openwakeword(10400) all running
  ```

  Then in HA: Settings → Devices & Services → Add Integration → **Wyoming Protocol**, add three instances (one per port) pointing at `host.docker.internal` (or Windows LAN IP if HA is on a different machine).

  See `infra/wyoming/README.md` for full details + model customization.

- [ ] **Step 1.2: User installs Ollama integration in HA**

  In HA: Settings → Devices & Services → Add Integration → Ollama. URL: `http://<windows-host-ip>:11434`. Pick model: `gemma3:4b`.

- [ ] **Step 1.3: User creates Assist pipeline**

  Settings → Voice Assistants → Add Assistant.
  - STT: Faster Whisper
  - Wake word: openWakeWord (or micro_wake_word later)
  - Conversation agent: **Home Assistant** (primary — handles intents)
  - Set "Prefer handling commands locally"
  - Add Ollama (gemma3:4b) as the **fallback** conversation agent
  - TTS: Piper, voice: en_GB-alan-medium (or user pick)

- [ ] **Step 1.4: Verify pipeline via REST API**

  ```bash
  curl -H "Authorization: Bearer $HA_TOKEN" http://<ha-ip>:8123/api/conversation/agent/info
  ```
  Expected: response includes Ollama agent ID + HA Assist agent ID.

  ```bash
  curl -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text":"turn on the kitchen lights","agent_id":"conversation.home_assistant"}' \
    http://<ha-ip>:8123/api/conversation/process
  ```
  Expected: HA Assist responds with intent match or "no match".

  ```bash
  curl -X POST -H "Authorization: Bearer $HA_TOKEN" -H "Content-Type: application/json" \
    -d '{"text":"what is the capital of Mongolia","agent_id":"conversation.ollama"}' \
    http://<ha-ip>:8123/api/conversation/process
  ```
  Expected: Ollama returns "Ulaanbaatar" (proves model is loaded + responding).

- [ ] **Step 1.5: Commit notes (no code; just observed values)**

  No commit in this task — just record the HA add-on versions, Ollama model SHA, and pipeline IDs in `Vault/projects/ROBOTAI/voice-ha-setup.md` for reproducibility.

**Verification:** Both `curl` calls return non-empty responses; pipeline visible in HA UI.

---

## Task 2: Vendor the ES8311 Master-Mode Patch

ESPHome's stock ES8311 component is hardcoded I2S slave. ES7210 also wants slave. One must be master. The sw3Dan fork has a working patch — we vendor it into our repo rather than depend on their fork.

**Files:**
- Create: `esphome/components/es8311_master/__init__.py`
- Create: `esphome/components/es8311_master/audio_dac.py`
- Create: `esphome/components/es8311_master/es8311.cpp`
- Create: `esphome/components/es8311_master/es8311.h`

- [ ] **Step 2.1: Fetch the sw3Dan patch**

  ```bash
  gh repo clone sw3Dan/waveshare-s2-audio_esphome_voice /tmp/sw3dan
  ```
  Identify the ES8311 component files: should be under `components/es8311/` or similar.

- [ ] **Step 2.2: Copy patched component into our repo as `es8311_master`**

  Name it `es8311_master` so it doesn't shadow ESPHome's stock component.
  ```bash
  mkdir -p esphome/components/es8311_master
  cp /tmp/sw3dan/components/es8311/* esphome/components/es8311_master/
  ```
  Rewrite the C++ class name and Python registration to `es8311_master` to avoid namespace collision.

- [ ] **Step 2.3: Diff against ESPHome stock to understand the patch**

  ```bash
  gh repo clone esphome/esphome /tmp/esphome-upstream
  diff /tmp/esphome-upstream/esphome/components/es8311/ esphome/components/es8311_master/
  ```
  Expected diff: ~100 lines, the master-mode register writes + MCLK config.

- [ ] **Step 2.4: Add LICENSE/ATTRIBUTION**

  Add `esphome/components/es8311_master/ATTRIBUTION.md`:
  > Patched from sw3Dan/waveshare-s2-audio_esphome_voice, which is in turn derived
  > from ESPHome's stock es8311 component. Adds I2S master mode for boards that
  > share MCLK with a separate slave ADC (ES7210 in our case).

- [ ] **Step 2.5: Commit**

  ```bash
  git add esphome/components/es8311_master/
  git commit -m "feat(esphome): vendor ES8311 master-mode component patch from sw3Dan fork"
  ```

**Verification:** `git log` shows the new commit; `find esphome/components/es8311_master -type f | wc -l` ≥ 4 files present.

---

## Task 3: Build the DualEye ESPHome YAML (Audio Path First, No Eyes Yet)

Audio path first — eyes come in Task 4. This isolates risk: if audio works, the codec patch is good; we know any later display issues are display-specific.

**Files:**
- Create: `esphome/dualeye_voice.yaml`
- Modify: `esphome/secrets.yaml` (WiFi creds + API key already present from ESP32-CAM project)

- [ ] **Step 3.1: Write minimal YAML — boots + connects to WiFi + speaks Wyoming**

  Base config:
  ```yaml
  esphome:
    name: dualeye
    friendly_name: Robot Head
  esp32:
    board: esp32-s3-devkitc-1
    flash_size: 16MB
    framework:
      type: esp-idf
      sdkconfig_options:
        CONFIG_ESP32S3_DEFAULT_CPU_FREQ_240: y
        CONFIG_ESP32S3_DATA_CACHE_64KB: y
        CONFIG_SPIRAM_MODE_OCT: y
        CONFIG_SPIRAM_SPEED_80M: y
  psram:
    mode: octal
    speed: 80MHz
  wifi:
    ssid: !secret wifi_ssid
    password: !secret wifi_password
  api:
    encryption:
      key: !secret api_key
  ota:
    - platform: esphome
      password: !secret ota_password
  logger:
    level: INFO
  ```

- [ ] **Step 3.2: Add the audio chain**

  ```yaml
  external_components:
    - source:
        type: local
        path: components

  i2c:
    sda: 11
    scl: 10
    frequency: 400kHz

  i2s_audio:
    i2s_lrclk_pin: 14   # WS
    i2s_bclk_pin: 13
    i2s_mclk_pin: 12

  audio_dac:
    - platform: es8311_master
      id: dac
      address: 0x18

  audio_adc:
    - platform: es7210
      id: adc
      address: 0x40
      sample_rate: 16000
      bits_per_sample: 16
      mic_gain: 30dB
      tdm_mode: true

  microphone:
    - platform: i2s_audio
      id: mic
      adc: adc
      channel: 0
      sample_rate: 16000

  speaker:
    - platform: i2s_audio
      id: spk
      dac: dac
      i2s_dout_pin: 16
      sample_rate: 16000
      mode: mono
      enable_pin: 9   # PA enable
  ```

- [ ] **Step 3.3: Add wake word + voice_assistant component**

  ```yaml
  micro_wake_word:
    id: mww
    models:
      - model: hey_jarvis   # placeholder; user trains custom later
        probability_cutoff: 0.97
    microphone: mic

  voice_assistant:
    id: va
    microphone: mic
    speaker: spk
    micro_wake_word: mww
    noise_suppression_level: 1
    auto_gain: 31dBFS
  ```

- [ ] **Step 3.4: Flash + verify audio-only**

  ```bash
  cd esphome
  esphome run dualeye_voice.yaml --device COM5
  ```
  Connect to HA → device shows up as ESPHome integration. Trigger `voice_assistant.start` from HA dev tools. Expected: mic captures, audio plays back via speaker.

- [ ] **Step 3.5: Commit (audio path proven)**

  ```bash
  git add esphome/dualeye_voice.yaml
  git commit -m "feat(esphome): DualEye voice satellite YAML — audio path"
  ```

**Verification:** ESPHome device appears in HA, mic stream visible in HA `voice_assistant.debug`, speaker plays test TTS through Piper.

---

## Task 4: Add LVGL Eye Animation Component

Two GC9A01A round displays on the shared SPI bus. ESPHome has a `gc9a01a` display platform — we use it twice with different CS pins.

**Files:**
- Modify: `esphome/dualeye_voice.yaml`
- Create: `esphome/components/dualeye_face/__init__.py` (custom LVGL anim driver, optional — start with static)
- Create: `esphome/eye_animations/` (PNG frame assets, optional)

- [ ] **Step 4.1: Add SPI bus + two displays to YAML**

  ```yaml
  spi:
    clk_pin: 41
    mosi_pin: 42
    interface: hardware

  display:
    - platform: gc9a01a
      id: left_eye
      cs_pin: 47
      dc_pin: 45
      reset_pin: 48
      invert_colors: true
      update_interval: never
      lambda: |-
        it.fill(Color(0,0,0));
        it.filled_circle(120, 120, 80, Color(255,255,255));
        it.filled_circle(120, 120, 40, Color(0,0,0));
    - platform: gc9a01a
      id: right_eye
      cs_pin: 38
      dc_pin: 45
      reset_pin: 8
      invert_colors: true
      mirror_x: true
      mirror_y: true
      update_interval: never
      lambda: |-
        it.fill(Color(0,0,0));
        it.filled_circle(120, 120, 80, Color(255,255,255));
        it.filled_circle(120, 120, 40, Color(0,0,0));

  output:
    - platform: gpio
      pin: 46
      id: bl_left
    - platform: gpio
      pin: 39
      id: bl_right

  # Light wrappers so we can dim from HA
  light:
    - platform: binary
      output: bl_left
      name: "Left Eye Backlight"
      restore_mode: ALWAYS_ON
    - platform: binary
      output: bl_right
      name: "Right Eye Backlight"
      restore_mode: ALWAYS_ON
  ```

- [ ] **Step 4.2: Flash + verify static eye renders on both displays**

  ```bash
  esphome run dualeye_voice.yaml
  ```
  Expected: both displays show a static white circle on black with a black pupil. Backlights on, displays sync to the same frame.

- [ ] **Step 4.3: Add idle blink animation (script + timer)**

  ```yaml
  interval:
    - interval: 5s
      then:
        - lambda: |-
            // Blink: pupil temporarily large to cover whole eye
            // Trigger redraw of both eyes via id().update()
            id(left_eye).update();
            id(right_eye).update();
  ```
  Refine the lambda to render closed/open frames based on a global state variable. Keep simple — full LVGL animations are a later polish task.

- [ ] **Step 4.4: Add voice_assistant state -> eye expression mapping**

  ```yaml
  voice_assistant:
    on_listening:
      - lambda: 'id(eye_state) = LISTENING;'
      - script.execute: redraw_eyes
    on_stt_end:
      - lambda: 'id(eye_state) = THINKING;'
      - script.execute: redraw_eyes
    on_tts_start:
      - lambda: 'id(eye_state) = SPEAKING;'
      - script.execute: redraw_eyes
    on_end:
      - lambda: 'id(eye_state) = IDLE;'
      - script.execute: redraw_eyes
  ```
  States change pupil size / position to give a "robot is listening" / "thinking" cue.

- [ ] **Step 4.5: Commit (eyes + voice integration)**

  ```bash
  git add esphome/dualeye_voice.yaml
  git commit -m "feat(esphome): add dual GC9A01A eyes with voice_assistant state sync"
  ```

**Verification:** Trigger a wake word; left+right eyes change shape during listening/speaking phases. Both displays update simultaneously without tearing.

---

## Task 5: End-to-End Voice Test (Wake Word → HA Intent / Ollama Fallback)

The integration test. This proves the user's stated requirement works.

**Files:**
- Modify: `homeassistant/configuration.yaml` notes (not in repo — record in Vault)
- Verify only

- [ ] **Step 5.1: Test "turn on lights" (HA intent path)**

  Say wake word → "turn on the bedroom lights".
  Expected: light entity toggles, HA Assist responds with "Turned on Bedroom Light" via Piper TTS. Eyes go SPEAKING then back to IDLE. **Ollama is NOT called** (verify by tail-ing Ollama logs — no inference request).

- [ ] **Step 5.2: Test "general question" (Ollama fallback path)**

  Say wake word → "what is the boiling point of water in Celsius".
  Expected: HA Assist returns no intent match, conversation chain falls back to Ollama. Ollama returns "100 degrees Celsius" via Piper. Latency target: first audio byte within 3 seconds of end-of-speech.

- [ ] **Step 5.3: Measure latency**

  Use HA Voice Assistant debug page. Record:
  - Wake word detection time
  - STT duration
  - Conversation agent duration (HA Assist + Ollama)
  - TTS duration
  - Total end-to-end

  Compare against target (sub-3s for Ollama path, sub-1.5s for HA intent path).

- [ ] **Step 5.4: Document results**

  Append to `Vault/projects/ROBOTAI/voice-benchmark.md`: dates, model, latency numbers, any failure modes observed.

- [ ] **Step 5.5: Capture lesson if any step required workarounds**

  Per CLAUDE.md L-rule: any correction/workaround → capture-lesson skill.

**Verification:** Both test phrases work end-to-end. Latency within target. Eyes animate during conversation states.

---

## Task 6: Cleanup + Retire xiaozhi-esp32

Once ESPHome path is proven (Task 5 passes), the xiaozhi build on OTA slot B can be retired. Until then, keep the xiaozhi binary as a known-good rollback.

**Files:**
- Modify: `xiaozhi-esp32/sdkconfig.dualeye` (mark deprecated)
- Modify: `docs/VOICE_AI.md` (update "What stays from xiaozhi-esp32" section)
- Modify: README.md (drop xiaozhi-esp32 from the architecture diagram)

- [ ] **Step 6.1: Wait until Task 5 has been stable for 48 hours of normal use**

  No reflashes back to xiaozhi, no manual interventions, no user-reported regressions.

- [ ] **Step 6.2: Erase OTA data so xiaozhi binary is gone from slot B**

  ```powershell
  cd F:\ROBOTAI\xiaozhi-esp32
  cmd /c "C:\Espressif\esp-idf\export.bat && idf.py -p COM5 erase-otadata"
  ```

- [ ] **Step 6.3: Update README + VOICE_AI.md**

  Remove xiaozhi from architecture diagram; mark VOICE_AI.md "What stays from xiaozhi" → "nothing; retired YYYY-MM-DD".

- [ ] **Step 6.4: Final commit**

  ```bash
  git add README.md docs/VOICE_AI.md
  git commit -m "docs: retire xiaozhi-esp32 fork — ESPHome voice satellite is the production firmware"
  ```

**Verification:** OTA slot B reports empty; xiaozhi-esp32 fork is read-only/archived.

---

## Open Risks (carry into execution)

- **PSRAM pressure**: eyes + voice pipeline + Wyoming buffers together. Mitigation: drop eye refresh rate during active conversation.
- **ES7210 4-mic without AEC**: works in quiet rooms; noisy room is untested. Mitigation: port xiaozhi AEC as a future ESPHome component if needed.
- **micro_wake_word custom training**: stock "hey jarvis" works for testing but user will want a personal wake word — `microwakeword.com` is a separate workflow, not blocking.
- **sw3Dan upstream changes**: their fork is single-maintainer. Mitigation: vendoring in Task 2 means we won't suddenly break if their repo disappears.
- **Ollama latency on Windows**: gemma3:4b first-token measured during Task 5. If too slow, fall back to smaller `gemma3:1b` or `qwen2.5:1.5b`.

## Execution Handoff

After completing Task 1 (HA-side setup is on the user), the remaining tasks 2–6 should be executed with `superpowers:subagent-driven-development`:
- Fresh subagent per task
- Each task has clear acceptance criteria
- User intervenes at flash points (USB-C reconnect, observe screen, etc.)

Tasks 1 and 2 can run in parallel — user clicks in HA while subagent vendors the ES8311 patch.
