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

> Vendor-verified against the official schematic (`files.waveshare.com/wiki/ESP32-S3-DualEye-LCD-1.28/ESP32-S3-DualEye-LCD-1.28-Schematic.pdf`, dated 2025-08-28) and the vendor docs at <https://docs.waveshare.com/ESP32-S3-DualEye-LCD-1.28>. Re-audit triggers: vendor schematic revision change, new SH1.0 cable variant.

### SH1.0 14-pin pinout — LCD1-Board side (P1 in schematic)

The DualEye has **two** SH1.0 14-pin connectors (one on each LCD sub-board, refdes `P1` and `P2`). Use **LCD1-Board (`P1`)** for tethered peripherals — the LCD2-Board (`P2`) header carries different signals (display SPI lines for LCD2).

| Pin | Signal (vendor verbatim) | What it does | Notes |
|---|---|---|---|
| 1 | `USB_5V` | 5V power | **Bidirectional**: output ~4.55-4.70 V when USB-C is plugged into the DualEye (VBUS minus D1 Schottky Vf). Also accepts external 5V input to power the whole board when USB-C is unplugged. ≤ 2 A through D1 (MBR230LSFT1G); minus board self-draw, ~1.5 A available to peripherals worst case. |
| 2 | `GND` | Common ground | |
| 3 | `D_N` | USB D− (negative) | Mirrored from USB-C — for tethered USB peripherals, not used by our cam tether |
| 4 | `D_P` | USB D+ (positive) | Same as Pin 3 |
| 5 | `3V3` | 3.3V power | OUTPUT from MP1605GTF-Z buck converter. 3.314 V, ≤ 2 A capability (board uses some), always-on when board is powered. **Use this if the cam's onboard AMS1117 is dead** — feed straight to cam's 3V3 pin to bypass the regulator. |
| 6 | `GND` | Common ground | |
| 7 | `SDA` | I2C SDA (bus 1) | Same I2C bus as ES8311 + ES7210 + QMI8658 |
| 8 | `SCL` | I2C SCL (bus 1) | |
| 9 | `UART_RXD` | ESP32-S3 UART RX | Connects to peripheral's TX (cam's U0T) |
| 10 | `UART_TXD` | ESP32-S3 UART TX | Connects to peripheral's RX (cam's U0R) |
| 11 | `TP2_SDA` | Touch-panel I2C (unused on non-touch variant) | |
| 12 | `TP2_SCL` | Touch-panel I2C | |
| 13 | `GPIO0` | ESP32-S3 GPIO0 | Boot strap — leave floating after flash |
| 14 | `RESET` | ESP32-S3 RESET | Used by USB-C autoreset circuit |

### Power tree (from schematic page 1)

```
USB-C J1 VBUS ─► D1 MBR230LSFT1G ─► net "USB_5V" ─┬─► P1.1 (SH1.0 Pin 1, LCD1-Board)
                (Schottky, 2A,                    ├─► P2.1 (SH1.0 Pin 1, LCD2-Board)
                 ~0.45V Vf)                       ├─► U1 ETA6098 (charger/power-path IC)
                                                  └─► U2 MP1605GTF-Z buck ─► net "3V3" ─► P1.5, P2.5
```

### ESP32-CAM cam-side wiring (4-wire tether)

| DualEye SH1.0 (LCD1-Board) | ESP32-CAM AI-Thinker header | Purpose |
|---|---|---|
| Pin 1 `USB_5V` | `5V` pin (left column, top, red label on the AI-Thinker pinout) | Power |
| Pin 2 `GND` | Any `GND` pin | Common ground |
| Pin 9 `UART_RXD` | `U0T` (UART TX out of cam) | Head ← cam |
| Pin 10 `UART_TXD` | `U0R` (UART RX into cam) | Head → cam |

⚠ **Do NOT wire to the cam's `3.3V/5V` (yellow) pin** — that's `P_OUT` (regulator output), not an input.

⚠ **SH1.0 FPC cable orientation matters.** Pin 14 ↔ Pin 1 reversal is the #1 wiring mistake — would drive 5V into the RESET line. Use the polarity key on the connector to verify both ends match.

### Diagnostic order if the cam doesn't boot from the tether

1. Both DualEye LCDs (eyes) currently rendering? If no → USB-C cable doesn't pass VBUS (try a known charging cable).
2. Measure DC Pin 1 → Pin 2 at the DualEye SH1.0 socket. Expect ~4.55–4.70 V. If 0 V → D1 Schottky failed open.
3. With FPC plugged into both ends, measure same Pins 1→2 at the cam end of the cable. If 0 V here but 4.6 V at step 2 → FPC reversed or broken.
4. Bench supply 5V directly to cam's 5V/GND pins (skip the SH1.0). If cam boots → SH1.0 path is broken. If not → cam's 5V pad solder joint is open.

Flashing the cam after deployment: OTA only. The UART pins (Pin 9/10) also allow serial recovery from the head unit if OTA ever breaks.

---

## ESP32-CAM Programmer (Dead — Reference Only)
