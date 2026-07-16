# ESP32-CAM Bring-Up — Camera Phase (prepared 2026-07-16)

Everything below is pre-staged: firmware compiled (with the new MJPEG server for
Frigate), Frigate stack written, HA automation skeleton ready. The only missing
ingredient is **powering the board**.

## Power options (user choice — both prepared)

### Option A — Tethered behind the eyes (SH1.0 cable)
The DualEye's SH1.0 expansion header supplies **5V + GND + UART** (see
`docs/hardware.md`). Wire cam 5V/GND to the SH1.0 5V/GND, and (optional) cam
U0T → SH1.0 Pin 9: the DualEye firmware already mirrors the cam's boot log
into its own logger as `CAM_LOG:` lines — free diagnostics.
- Pro: one enclosure, one supply, cam log visible via `esphome logs dualeye.yaml`.
- Con: shares the robot's 5V budget — use a supply good for ≥1.5 A total
  (eyes + audio + cam bursts).

### Option B — Standalone
Any 5V USB adapter → cam 5V/GND pins. Fully independent.

## Bring-up steps (after power)
1. The board joins WiFi with its last-flashed firmware (static `192.168.0.104`).
   Check: `ping 192.168.0.104`.
2. OTA the camera-phase firmware (adds MJPEG server):
   `cd F:\ROBOTAI\esphome && esphome run robot_cam.yaml`
   (If the old firmware predates OTA or won't answer, first flash over the
   CP2104 UART per `docs/flashing-guide.md` — IO0→GND, `--device COM<x>`.)
3. Verify stream: `http://192.168.0.104:8080/stream` (MJPEG) and
   `http://192.168.0.104:8081/still` (snapshot). HA entity
   `camera.robot_cam_robot_eye` comes back automatically.
4. Start Frigate: `docker compose -f F:\ROBOTAI\infra\frigate\docker-compose.yml up -d`
   → UI at `http://192.168.0.10:5000`, confirm `robot_eye` camera shows frames
   and person detection fires (walk in front of it).
5. In HA: install/enable the Frigate integration (HACS) pointing at
   `http://192.168.0.10:5000` → creates `binary_sensor.robot_eye_person_occupancy`.
6. Enable the prepared automation `automation.robot_person_wake` (created
   disabled) — eyes wake to "watching" when a person appears (#33).

## What each top-50 vision item needs after bring-up
| # | Item | Needs |
|---|---|---|
| 33 | Person-triggered wake | steps 4–6 above only |
| 34 | Face-recognition greetings | + Double-Take + CompreFace containers (next session) |
| 35 | Doorbell face memory | reuses #34 stack on the Nest snapshots |
| 40 | Waving hello | Frigate motion zones tuning, no new hardware |
| 42 | Narrated timelapse | flip `record: enabled: true` in Frigate config |
