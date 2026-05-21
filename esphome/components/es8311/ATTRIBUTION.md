# ES8311 — Patched External Component

This component **overrides** ESPHome's built-in `es8311` audio_dac platform. ESPHome's external_components mechanism gives precedence to local components with the same name, so any YAML using `platform: es8311` resolves to this version.

## Why patched?

ESPHome's stock ES8311 component (as of 2026-05) is hardcoded to I2S **slave** mode. On the Waveshare ESP32-S3-DualEye-LCD-1.28, the ES8311 (DAC) and ES7210 (mic ADC) share the same I2S bus, and the ES7210 ESPHome component is also slave-mode. Two slaves with no master → no clock → no audio.

The patch adds three config options:

| Option | Default | What it does |
|---|---|---|
| `use_mclk` | `true` | Whether MCLK is provided externally (we provide it on GPIO12) |
| `mclk_multiple` | `256` | MCLK to LRCK ratio (sample-rate clock derivation) |
| `force_master` | `false` | Force the ES8311 into I2S master mode (we set this to `true`) |

When `force_master: true`, the patch preserves bit 6 (MSC) of register 0x00 during power-on so the chip drives BCLK and LRCK instead of receiving them. This makes the ES8311 the bus master and the ES7210 a clean slave — both speak the same clock domain, which is what we need for full-duplex audio.

## Provenance

| Layer | Source | Verified |
|---|---|---|
| Original component | [`esphome/components/es8311`](https://github.com/esphome/esphome/tree/dev/esphome/components/es8311) by @kroimon and @kahrendt | upstream, MIT |
| Master-mode + MCLK config patch | [sw3Dan/waveshare-s2-audio_esphome_voice](https://github.com/sw3Dan/waveshare-s2-audio_esphome_voice) `components/es8311/` | working ESPHome reference for the Waveshare S3 Audio Board (same ES8311+ES7210 chain as our DualEye) |
| Vendored to this repo | `F:\ROBOTAI\esphome\components\es8311\` | 2026-05-21 |

`es8311.cpp` is 351 lines (vs 225 upstream) — the +126 line delta is mostly the master-mode register-write path and the new config wiring.

## Why vendored (not pulled from sw3Dan's repo at build time)

The sw3Dan fork is single-maintainer with low commit cadence. Pulling at build time would make our build break if their repo moved, was renamed, or had their HEAD broken. Vendoring snapshots a known-good version. If upstream ESPHome adds master-mode support natively, we delete this folder and remove the component override.

## Re-sync command

When ESPHome upstream changes their es8311 component (sample-rate table, mic-gain enum, etc.), re-sync by:

```bash
# In a temp dir
git clone --depth 1 https://github.com/esphome/esphome
diff esphome/esphome/components/es8311/ F:/ROBOTAI/esphome/components/es8311/
# Apply non-master-mode changes manually; keep our patch on top.
```

## License

This component inherits ESPHome's MIT license. The sw3Dan patch is in the same project under the same license. Our vendoring does not change the licensing.
