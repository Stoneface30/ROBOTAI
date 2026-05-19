# Flashing Guide — ESP32-CAM via CP2104 UART

This guide covers first-time flashing when the MB programmer board is unavailable (dead or missing).

## What You Need

- AI-Thinker ESP32-CAM module
- Any CP2104 / CP2102 / CH340 USB-UART adapter with 5V output (DollaTek CP2104 6-pin confirmed working)
- DuPont female-to-female jumper wires
- ESPHome installed (`pip install esphome`)

## Why Not the MB Board

The diymore ESP32-CAM-MB kit includes a CH340C-based USB programmer. The CH340C chip can be DOA (dead on arrival) — Windows won't enumerate it as a COM port even with drivers installed and multiple cables tested. The CP2104 UART adapter is a reliable substitute.

## Wiring

```
CP2104 adapter    ESP32-CAM 16-pin header
──────────────    ───────────────────────
5V        ──────→ 5V   (right column, pin 1 from top)
GND       ──────→ GND  (right column, pin 4)
TXD       ──────→ UDT  (right column, pin 8)  ← adapter TX = board RX
RXD       ←────── UDR  (right column, pin 7)  ← adapter RX = board TX
                  IO0 ←─── GND bridge          (right column, pin 3)
```

The IO0→GND bridge puts the ESP32 into download mode on power-up. A single DuPont wire from IO0 (pin 3) to any GND pin works. Remove it after flashing.

## ESP32-CAM 16-pin Header Layout (right column, top to bottom)

```
Right side (top → bottom):
  Pin 1: 3V3
  Pin 2: IO16
  Pin 3: IO0   ← bootloader strap
  Pin 4: GND   ← bridge target
  Pin 5: VCC (5V)
  Pin 6: UDR (RX)
  Pin 7: UDT (TX)
  Pin 8: GND
```

## Flash Steps

```bash
# 1. IO0→GND bridge in place
# 2. Plug in CP2104 USB — board powers up in download mode
# 3. Verify COM port (Windows Device Manager → Ports)

cd /your/project
esphome run esphome/robot_cam.yaml --device COM4   # adjust COMx

# ESPHome compiles, then shows:
# Connecting.....
# Connected to ESP32 on COM4:
# Uploading...
# OTA successful
```

If `Connecting.....` hangs: power-cycle the board while IO0 is still grounded.

## After First Flash

1. Remove IO0→GND bridge
2. Power-cycle
3. Board boots ESPHome, connects to WiFi, appears in Home Assistant
4. All future updates: `esphome run esphome/robot_cam.yaml` (no `--device`) — OTA over WiFi

## Common Errors

### `ModuleNotFoundError: No module named 'esptool'`

PlatformIO installs `tool-esptoolpy` as a broken editable pip install when running from MinGW/Git Bash. Fix:

```bash
# Uninstall broken editable install
"C:/Users/<YOU>/.platformio/penv/Scripts/pip.exe" uninstall esptool -y

# Reinstall from PyPI into penv
"C:/Users/<YOU>/.platformio/penv/Scripts/pip.exe" install esptool==5.2.0

# Verify
"C:/Users/<YOU>/.platformio/penv/Scripts/python.exe" -c "import esptool; print(esptool.__version__)"
# → 5.2.0
```

### `Failed to connect to ESP32: No serial data received`

- IO0→GND bridge not in place before power-up
- Power-cycle the board (don't just reset) while IO0 is grounded
- Verify TX/RX not swapped: adapter TXD → board UDT (not UDR)

### `ESP_ERR_NOT_SUPPORTED` (camera probe fails)

- Missing `power_down_pin: GPIO32` in YAML — the OV2640 needs GPIO32 driven LOW
- Do NOT use `reset_pin: GPIO15` — GPIO15 is a strapping pin unrelated to camera RESETB
- See [`robot_cam.yaml`](../esphome/robot_cam.yaml) for correct config
