# ROBOTAI — Home Robot Head Unit + Vision + Voice AI

> **Two-board robot brain:** Waveshare ESP32-S3-DualEye (head + voice) + ESP32-CAM (vision) → Home Assistant on Windows 11 → Local LLM via Ollama → Fully local, OTA-managed.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│            Windows 11 host (Home Assistant + Ollama)        │
│   HA Assist pipeline · qwen2.5 · gemma3 · Frigate (planned) │
└──────────┬──────────────────────────┬───────────────────────┘
           │ ESPHome native API       │ Wyoming protocol or
           │ (MJPEG camera stream)    │ custom audio stream
           │                          │   (see VOICE_AI.md)
┌──────────▼──────────┐  ┌────────────▼──────────────────────┐
│   ESP32-CAM         │  │  Waveshare ESP32-S3-DualEye-1.28  │
│   (Vision module)   │  │  (Head unit / Brain)              │
│                     │  │                                   │
│  OV2640 camera      │  │  2× 240×240 round LCD "eyes"      │
│  MJPEG → HA         │  │  ES8311 codec + 8Ω speaker        │
│  ESPHome firmware   │  │  ES7210 4-mic array               │
│  OTA via WiFi       │  │  Wake-word + STT/TTS via LAN      │
│                     │  │  GC9A01A panels @ 80 MHz SPI      │
│  Connects to head   │  │  WiFi 2.4GHz + BLE 5.0            │
│  unit via SH1.0     │  │  USB-C native + CH343P UART       │
│  expansion header   │  │                                   │
│  (5V + UART)        │  │  xiaozhi-esp32 firmware (current) │
└─────────────────────┘  │  Voice-AI stack: see VOICE_AI.md  │
                         └───────────────────────────────────┘
```

## What This Is

A home robot with two ESP32-class boards:

1. **Head unit** — Waveshare ESP32-S3-DualEye-LCD-1.28 (WS-32267)
   - Two round 1.28" GC9A01A displays = animated robot eyes
   - ES8311 + ES7210 audio chain (8Ω speaker out, 4-mic array in)
   - QMI8658 IMU on I2C bus 1
   - 16MB flash, 8MB PSRAM, BLE 5.0, WiFi 2.4GHz
   - Currently runs a customised `xiaozhi-esp32` fork. Voice-AI stack pending — see `VOICE_AI.md` once research completes

2. **Vision module** — AI-Thinker ESP32-CAM
   - OV2640 sensor, ESPHome firmware, MJPEG → HA
   - Powered + tethered to head unit via SH1.0 expansion header (5V + serial)

Both run fully on the LAN. Server side: Home Assistant + Ollama on Windows 11.

This repo documents the complete journey: rescuing a dead programmer board, the ESP32-CAM brought up via UART, the DualEye debugged from "black screens" caused by hallucinated MOSI/MISO pin assignments, and the voice AI stack chosen via research (see `VOICE_AI.md`).

---

## Key Accomplishments

### ESP32-CAM (vision)
- **Dead MB board bypass** — The CH340C USB chip on the diymore ESP32-CAM-MB programmer board was dead on arrival. Pivoted to a DollaTek CP2104 6-pin UART adapter as a direct programmer — 5V, GND, TX→RX, RX→TX, IO0→GND for bootloader mode.

- **esptool environment surgery** — PlatformIO's `tool-esptoolpy` package installed as a broken editable pip install pointing at an empty directory (MinGW/Git Bash blocked `idf_tools.py`). Fix: uninstall the editable install, reinstall `esptool==5.2.0` from PyPI into PlatformIO's `penv`.

- **Camera init fixed** — Root cause of `ESP_ERR_NOT_SUPPORTED`: `reset_pin: GPIO15` was driving a strapping pin; `power_down_pin: GPIO32` was missing (needed to wake OV2640). Fixed via OTA.

- **Full OTA from first boot** — Live in HA as `camera.robot_cam_robot_eye` (0.1fps idle → 10fps on demand).

### DualEye head unit
- **Black-screen debug** — Both displays dark despite "panel create success" log messages. Root cause: pin assignments in our board file (commit 55bc2ba) were guessed, not pulled from Waveshare's reference. **MOSI was on GPIO40, MISO on GPIO42 — they need to be swapped.** SPI commands were being sent out the panel's input pin the whole time; the GC9A01 driver reports init success regardless of physical wiring. Also wrong: audio DIN/DOUT swapped, `AUDIO_CODEC_PA_PIN` set to `NC` instead of `GPIO9`, `DISPLAY_SWAP_XY` wrong, LCD2 mirror flags missing. Fix: copy the canonical config from `waveshareteam/ESP32-S3-DualEye-Touch-LCD-1.28` GitHub repo verbatim.
- **Permanent rule extracted** — `Vault/rules/rule-vendor-reference-first.md`: never guess pin assignments for vendor boards; fetch the canonical reference first. Driver "init success" messages prove nothing about wiring.
- **Live state** — both displays render, WiFi connects, audio codec (ES8311+ES7210) initializes, MCP tools registered. Speaker hardware connected. Right-eye mirroring of left-eye content pending (currently shows GRAM static — LCD2 is initialized but no content is being drawn to it).

---

## Hardware

| Component | Part | Notes |
|-----------|------|-------|
| Main board | AI-Thinker ESP32-CAM (ESP32-S, OV2640) | FCC ID: 2BCLP-ESP-32S |
| Camera | OV2640 via HDF3m-811-V1T ribbon | 24-pin FPC, pre-attached |
| Programmer | DollaTek CP2104 USB-UART 6-pin | 5V power + serial via single USB |
| (Dead) | diymore ESP32-CAM-MB | CH340C USB chip DOA — used as donor for reference only |

**Power in robot:** 5V via BEC/UBEC rail → board's VCC pin. AMS1117 onboard regulator steps down to 3.3V for the ESP32. OV2640 camera runs from same 5V input.

---

## Pinout (AI-Thinker ESP32-CAM — fixed, do not change)

```
Camera XCLK  : GPIO0   (also IO0 boot strap — leave floating after flash)
Camera SDA   : GPIO26
Camera SCL   : GPIO27
Camera Data  : GPIO5, GPIO18, GPIO19, GPIO21, GPIO36, GPIO39, GPIO34, GPIO35
VSYNC        : GPIO25
HREF         : GPIO23
PCLK         : GPIO22
PWDN         : GPIO32  (drive LOW to wake OV2640 — must be explicit in ESPHome)
Flash LED    : GPIO4   (onboard, active HIGH, very bright — PWM at low duty only)
```

---

## Flashing (First Time — UART via CP2104)

The MB board's CH340C was dead. This method works with any CP2104/CP2102/CH340 UART adapter.

```
CP2104       ESP32-CAM 16-pin header
------       -----------------------
5V    ──────→ 5V  (right col, pin 1 from top)
GND   ──────→ GND (right col, pin 4)
TXD   ──────→ UDT (right col, pin 8) ← TX of ESP = RX of adapter
RXD   ←────── UDR (right col, pin 7) ← RX of ESP = TX of adapter
              IO0 ←── GND bridge (right col, pin 3 → any GND)
```

**Boot into download mode:**
1. IO0→GND bridge in place
2. Power-cycle (remove and replug USB)
3. You'll see `Connecting.....` — chip is ready

```bash
cd /your/esphome/project
esphome run esphome/robot_cam.yaml --device COM4   # Windows CP2104 port
```

After flash: remove IO0→GND bridge, power-cycle → boots normally.

**All future updates: OTA**
```bash
esphome run esphome/robot_cam.yaml   # no --device — auto-discovers via mDNS
```

---

## ESPHome Config Highlights

See [`esphome/robot_cam.yaml`](esphome/robot_cam.yaml) for full config.

Key decisions:
- `board: esp32cam` — AI-Thinker board definition (correct pinout, PSRAM config)
- `framework: arduino` — required for `esp32_camera`; esp-idf does not support it
- `psram: mode: quad / speed: 80MHz` — required or camera component refuses to init
- `power_down_pin: GPIO32` — explicitly wake OV2640; omitting this causes probe failure
- `i2c:` block separate from `esp32_camera:` — `i2c_pins:` is deprecated in ESPHome 2026+
- `reboot_timeout: 0s` — prevent OTA reboot loop if HA API temporarily unreachable
- `idle_framerate: 0.1fps` — conserves power when nothing is watching; spins to 10fps on demand

---

## Home Assistant Integration

ESPHome native API (no MQTT needed). After flashing, add via:
**Settings → Devices & Services → Add Integration → ESPHome → `192.168.0.x`**

Entities created:
| Entity | Type | Notes |
|--------|------|-------|
| `camera.robot_cam_robot_eye` | Camera | MJPEG stream, idle/active modes |
| `light.robot_cam_robot_eye_led` | Light | PWM flash LED — use sparingly |
| `sensor.robot_cam_robotcam_wifi` | Sensor | WiFi signal dBm |
| `sensor.robot_cam_robotcam_temp` | Sensor | Internal chip temperature |
| `button.robot_cam_robotcam_restart` | Button | OTA-safe restart |

---

## Known Issues & Blockers

| Issue | Status | Notes |
|-------|--------|-------|
| PlatformIO + MinGW esptool broken editable install | Fixed | Reinstall esptool from PyPI into penv |
| Camera `ESP_ERR_NOT_SUPPORTED` on first flash | Fixed | Add `power_down_pin: GPIO32`, remove `reset_pin: GPIO15` |
| Serial monitor drops when power-cycling via UART adapter | Workaround | Use separate 5V for board power; keep UART adapter for serial only |
| Chip temp ~65°C at idle with WiFi active | Expected | Normal for ESP32 with active WiFi + camera ready |

---

## Roadmap

- [ ] UART bridge to robot MCU (GPIO1 TX, GPIO3 RX — disconnect before USB flash)
- [ ] I2C sensor bus (GPIO15 SDA, GPIO14 SCL — 4.7kΩ pull-ups to 3V3)
- [ ] Motor PWM: Motor A → GPIO12 (PWM) + GPIO16 (Dir), Motor B → GPIO13 (PWM) + GPIO2 (Dir)
- [ ] Frigate NVR integration (OpenVINO on OptiPlex for object detection)
- [ ] MJPEG web server on dedicated port (add `esp32_camera_web_server` block)

---

## Media

Photos and videos from the build session in [`Media/`](Media/).

| File | Description |
|------|-------------|
| `PXL_*_hardware_*.jpg` | ESP32-CAM module, CP2104 wiring, IO0 bridge |
| `PXL_*_session_*.mp4` | Build session video |

---

## Secrets Template

Copy `esphome/secrets.yaml.template` to `esphome/secrets.yaml` and fill in your values. The `secrets.yaml` file is gitignored — never commit it.

---

## Related Projects

- [roborock-s5-valetudo](https://github.com/Stoneface30/roborock-s5-valetudo) — Same approach: rescue a device from broken tooling, document every blocker
