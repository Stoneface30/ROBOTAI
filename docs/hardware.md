# Hardware Reference

## Main Board — AI-Thinker ESP32-CAM

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

## Programmer Board (Dead — Reference Only)

The diymore ESP32-CAM-MB kit came with a CH340C-based USB programmer board. The CH340C USB chip was DOA — confirmed dead after testing two cables and two USB ports with WCH and generic CDC drivers. The board has been retired; CP2104 UART adapter is used for all programming.
