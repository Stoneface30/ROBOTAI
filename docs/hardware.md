# Hardware Reference

> Two boards in this robot. Section 1 = head unit (Waveshare DualEye). Section 2 = vision module (ESP32-CAM). They share power and a UART link via the DualEye's SH1.0 expansion header.

---

## Head Unit — Waveshare ESP32-S3-DualEye-LCD-1.28 (WS-32267)

Brain of the robot. Animated eyes + voice AI front-end + sensor hub.

| Spec | Value |
|------|-------|
| SoC | ESP32-S3R8 (Xtensa LX7 dual-core 240 MHz) |
| Flash | 16 MB onboard |
| PSRAM | 8 MB stacked octal (3V, generation 3) |
| WiFi / BLE | 2.4 GHz 802.11 b/g/n / BLE 5.0 |
| Displays | 2× 240×240 round IPS LCD, GC9A01A driver, SPI |
| Audio codec | ES8311 (mono DAC + ADC, I2S) |
| Audio ADC | ES7210 (4-mic TDM ADC, I2S) |
| Speaker | 8Ω 2W via JST connector |
| IMU | QMI8658 6-axis on I2C bus 1 |
| USB | Type-C, CH343P USB-UART bridge |
| Expansion | SH1.0 14-pin (extra GPIO + 5V power out for tethered modules) |

### Pinout — verified against [waveshareteam/ESP32-S3-DualEye-Touch-LCD-1.28](https://github.com/waveshareteam/ESP32-S3-DualEye-Touch-LCD-1.28) official config

| Signal | GPIO | Notes |
|---|---|---|
| **SPI bus (shared by both LCDs)** | | |
| MOSI | GPIO42 | ⚠ Critical: **not** GPIO40. See `Vault/rules/rule-vendor-reference-first.md` |
| MISO | GPIO40 | GC9A01 is write-only; line wired but unused |
| SCLK | GPIO41 | 80 MHz pclk |
| **LCD1 (left eye, primary)** | | |
| CS | GPIO47 | |
| DC | GPIO45 | Shared with LCD2 |
| RST | GPIO48 | |
| BL | GPIO46 | Active HIGH, direct GPIO (no PWM) |
| **LCD2 (right eye)** | | |
| CS | GPIO38 | |
| DC | GPIO45 | Shared with LCD1 |
| RST | GPIO8 | |
| BL | GPIO39 | Active HIGH |
| **I2C bus 1 — ES8311 + ES7210 + QMI8658** | | |
| SDA | GPIO11 | |
| SCL | GPIO10 | |
| **I2S audio** | | |
| MCLK | GPIO12 | |
| BCLK | GPIO13 | |
| WS | GPIO14 | |
| DIN (mic in via ES7210) | GPIO15 | ⚠ Not GPIO16 — see rule |
| DOUT (speaker out via ES8311) | GPIO16 | |
| PA enable | GPIO9 | Drives speaker amp; without this, no audio output |
| **Button + UART** | | |
| Boot button | GPIO0 | Long press → WiFi config; short → toggle chat |
| Console UART | GPIO43/44 | Via CH343P → USB-C |

### Backlight convention

Active **HIGH** on both BL pins. `DISPLAY_BACKLIGHT_OUTPUT_INVERT = false`.

### Black-screen lessons (do not repeat)

- The GC9A01 driver returns "LCD panel create success" even when MOSI is wired to a disconnected pin or to the panel's MISO line. The log message proves driver state, not physical wiring.
- Pin assignments must come from the vendor's official reference firmware. Guessing from a datasheet or "common patterns" cost ~5 hours of debug time on first bring-up.
- Audio codec init success is the same trap: ES8311 will say "Work in Slave mode" regardless of whether DIN/DOUT are correctly wired. Verify by playing a tone, not by reading logs.

---

## Vision Module — AI-Thinker ESP32-CAM

| Spec | Value |
|------|-------|
| SoC | ESP32-D0WD-V3 (dual-core 240MHz, rev3.1) |
| Flash | 4MB |
| PSRAM | 8MB (QSPI quad mode) |
| Camera | OV2640 via 24-pin FPC ribbon (HDF3m-811-V1T) |
| FCC ID | 2BCLP-ESP-32S |
| Flash LED | GPIO4 (onboard white LED — very bright at full duty) |
| Boot strap | GPIO0 = LOW → download mode; floating → normal boot |
| PWDN | GPIO32 → OV2640 power-down (active HIGH; drive LOW to wake) |

## Power

- **Input**: 5V via VCC pin (right column pin 5)
- **Onboard regulator**: AMS1117 3.3V — powers ESP32 and OV2640
- **Current draw**: ~200mA at idle WiFi + camera ready; spikes to ~300mA during camera active
- **CP2104 5V output**: adequate for flashing and testing; dedicate a separate 5V source for robot deployment

## Serial / Programming

| Signal | ESP32-CAM pin | Notes |
|--------|--------------|-------|
| TX (UDT) | Right col, pin 7 | → UART RX of adapter |
| RX (UDR) | Right col, pin 6 | ← UART TX of adapter |
| IO0 | Right col, pin 3 | → GND to enter bootloader |
| 5V | Right col, pin 5 | Power from adapter |
| GND | Right col, pin 4 | Common ground |

**Disconnect UART adapter before robot deployment** — TX/RX pins are also used by the robot MCU bridge in Phase 2.

## Planned Robot GPIO Allocation (Phase 2+)

| GPIO | Role | Notes |
|------|------|-------|
| GPIO1 | UART TX → robot MCU RX | Disconnect CP2104 before use |
| GPIO3 | UART RX ← robot MCU TX | Disconnect CP2104 before use |
| GPIO15 | I2C SDA (sensor bus) | 4.7kΩ pull-up to 3V3 required |
| GPIO14 | I2C SCL (sensor bus) | 4.7kΩ pull-up to 3V3 required |
| GPIO12 | Motor A PWM | |
| GPIO16 | Motor A direction | |
| GPIO13 | Motor B PWM | |
| GPIO2 | Motor B direction | |

## DualEye ↔ ESP32-CAM Tether (SH1.0 14-pin Header)

The ESP32-CAM is mounted on the robot and powered + linked via the DualEye's SH1.0 expansion header — no separate USB cable in the field.

| SH1.0 Pin | DualEye signal | ESP32-CAM wire | Purpose |
|---|---|---|---|
| 1 | USB_5V (5V passthrough from USB-C) | 5V (right col pin 5) | Power |
| GND pin | GND | GND (right col pin 4) | Common ground |
| GPIO43 (UART TX) | UART TX | UDR (right col pin 6, RX) | Head → cam control |
| GPIO44 (UART RX) | UART RX | UDT (right col pin 7, TX) | Cam → head telemetry |

⚠ Use SH1.0 **Pin 1 (USB_5V)**, not Pin 5 (3V3 rail). The ESP32-CAM has its own AMS1117 onboard 3V3 regulator and needs 5V input. Wiring it to 3V3 will brown out the OV2640 every time WiFi spikes current.

Flashing the ESP32-CAM after deployment: OTA only. The DualEye also exposes the UART to the cam, so a future enhancement is a serial passthrough for emergency rescue if OTA breaks.

---

## ESP32-CAM Programmer (Dead — Reference Only)
