# ROBOTAI — ESP32-CAM Robot Vision with Home Assistant

> **ESP32-CAM (AI-Thinker OV2640) → ESPHome → Home Assistant → OTA-only deployment**  
> Dead flashing board? No problem. Full journey documented — UART rescue, esptool surgery, OTA freedom.

---

## What This Is

An AI-Thinker ESP32-CAM module (OV2640 camera, 4MB Flash, 8MB PSRAM) running ESPHome firmware as the vision system for a home robot. Streams MJPEG video to Home Assistant. Fully OTA-managed — once flashed, zero physical access needed.

This repo documents the complete journey: hardware research, a dead programmer board, a UART rescue flash, two firmware bugs fixed, and a working camera live in Home Assistant.

---

## Key Accomplishments

- **Dead MB board bypass** — The CH340C USB chip on the diymore ESP32-CAM-MB programmer board was dead on arrival. Pivoted to a DollaTek CP2104 6-pin UART adapter as a direct programmer — 5V, GND, TX→RX, RX→TX, IO0→GND for bootloader mode.

- **esptool environment surgery** — PlatformIO's `tool-esptoolpy` package installed as a broken editable pip install pointing at an empty directory (MinGW/Git Bash blocked `idf_tools.py`). Fix: uninstall the editable install, reinstall `esptool==5.2.0` from PyPI into PlatformIO's `penv` — build succeeds, binary generated.

- **Camera init fixed via power_down_pin** — First flash showed `ESP_ERR_NOT_SUPPORTED` from camera probe despite correct pinout and seated ribbon. Root cause: `reset_pin: GPIO15` was incorrectly driving a strapping pin; `power_down_pin: GPIO32` was missing (needed to wake OV2640). Second OTA flash fixed both.

- **Full OTA from first WiFi boot** — Board connected to WiFi on first boot. All subsequent firmware updates pushed wirelessly — no physical access to the robot ever needed again.

- **Live in Home Assistant** — `camera.robot_cam_robot_eye` entity active. Idle at 0.1fps, streams at 10fps on demand.

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
