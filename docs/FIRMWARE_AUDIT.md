# Firmware Sovereignty Audit — xiaozhi-esp32 Fork

> **Date:** 2026-05-21
> **Auditor:** Static source review of `F:\ROBOTAI\xiaozhi-esp32` (our fork of github.com/78/xiaozhi-esp32)
> **Verdict:** Safe to run on the LAN; one defensive patch applied to prevent regression on clean rebuild.

## TL;DR

The firmware has **exactly one outbound dependency at boot**: an HTTP(S) POST to a bootstrap "OTA" URL. The OTA response is what tells the device which MQTT broker, WebSocket server, and time source to use — everything else downstream is **NVS-driven and user-controlled**.

The Kconfig default for that bootstrap URL was the upstream Chinese cloud (`https://api.tenclass.net/xiaozhi/ota/`). Our build was already overriding it via `sdkconfig` to a LAN address, but a clean rebuild would have reset it to the upstream default. **Patch applied 2026-05-21** to make the default unreachable (`http://0.0.0.0:0/`), forcing an explicit override.

No telemetry, no analytics, no hard-coded brokers, no TLS pinning. The MCP server in the firmware is the device's *internal tool registry* served over the existing WebSocket — not an outbound MCP client.

## Findings

| File:Line | URL / Hostname | Risk | Notes |
|---|---|---|---|
| `main/Kconfig.projbuild:5` | ~~`https://api.tenclass.net/xiaozhi/ota/`~~ → `http://0.0.0.0:0/` | **PATCHED** | Default OTA bootstrap. Replaced with unreachable address so clean rebuild can't phone home. Real value must come from `sdkconfig` or NVS. |
| `sdkconfig:600` | `http://192.168.0.10:8003/xiaozhi/ota/` | INFO | User's LAN OTA server. Plain HTTP — fine on trusted LAN, not over WAN. |
| `main/ota.cc:50` | `CONFIG_OTA_URL` (runtime) | INFO | Reads NVS `wifi.ota_url` first, falls back to Kconfig. WiFi config portal can override at runtime. |
| `main/ota.cc:146-186` | (MQTT + WebSocket from OTA JSON) | INFO | All MQTT/WS server config arrives from the OTA response and is persisted to NVS. Whoever runs the OTA server controls everything downstream. |
| `main/protocols/websocket_protocol.cc:84-95` | NVS `websocket.url` | INFO | No hard-coded WS URL anywhere. Pulled from NVS only. |
| `main/protocols/mqtt_protocol.cc:66` | NVS `mqtt.endpoint` | INFO | No hard-coded broker. |
| `main/Kconfig.projbuild:865` | `192.168.2.100:8000` | LOW | UDP audio debug server. Only used if `USE_AUDIO_DEBUGGER` is enabled (not enabled in `sdkconfig.dualeye`). |
| `main/display/emote_display.cc:149` | `"xiaozhi.me"` (substring) | LOW | String *check* only (UI heuristic for system messages). No network call. |
| `main/ota.cc:75`, `audio/wake_words/custom_wake_word.cc:114` | `*.feishu.cn` doc links | INFO | Comment / log string only — never fetched. |
| Other-board configs | `dl.espressif.com/AE/...bin` | LOW | Asset bundle download URL for *other* boards (not dualeye). Used at flash-time on dev PC, not on device. |
| SNTP | (no overrides) | INFO | `sdkconfig` uses ESP-IDF default or DHCP-provided NTP. `ota.cc:188-211` also accepts a `server_time` field from the OTA JSON — your LAN server can set the clock directly. |
| CA bundle / TLS pinning | (none) | INFO | No `esp_crt_bundle`, `cert_pem`, or hard-coded issuer. Standard ESP-IDF TLS verification chain. |
| API keys / tokens | (none in source) | INFO | All auth tokens come from NVS at runtime (`Authorization: Bearer` header in `websocket_protocol.cc:106`). |

## What's already OK

- **WiFi config portal** overrides OTA URL at runtime via NVS key `wifi.ota_url` (`ota.cc:48`).
- **WebSocket / MQTT URLs** are never hard-coded — only loaded from NVS, populated by the OTA JSON response. Your LAN OTA server is the single source of truth.
- **No telemetry**, no crash reporters (Sentry / Bugly / Umeng), no analytics SDKs.
- **No hard-coded IPs** other than the documented debug UDP (gated behind `USE_AUDIO_DEBUGGER` — disabled in our build).
- **MCP server is on-device only** (`main/mcp_server.cc`) — it's the device's tool registry served over the existing WebSocket, not an outbound MCP client.
- `sdkconfig.dualeye` is a 3-line override (board + emote + lang); does not reintroduce any endpoints.

## Defensive patch applied (2026-05-21)

`main/Kconfig.projbuild:5` — changed `OTA_URL` default from `https://api.tenclass.net/xiaozhi/ota/` to `http://0.0.0.0:0/`. This makes the default unreachable so a `idf.py fullclean` followed by a build cannot accidentally phone home. The real OTA URL must now come from one of:

1. `sdkconfig` (current behaviour — line 600 overrides it to LAN)
2. NVS `wifi.ota_url` at runtime (WiFi config portal)
3. Explicit `idf.py menuconfig` setting

## What this means for the ESPHome migration

The current xiaozhi-esp32 firmware is fine to keep running while we build the ESPHome replacement. We're not at risk of data leaks. The ESPHome migration is happening for architectural reasons (cleaner HA integration, less surface area, microWakeWord, ditching the xiaozhi protocol stack), not because the firmware is hostile.

## Re-audit triggers

Re-run this audit if:
- Upstream `github.com/78/xiaozhi-esp32` merges new code into our fork
- We pull new ESP-IDF managed components (`managed_components/`)
- We add any new MCP tools that take external dependencies
- We swap any audio/wake-word components for upstream Espressif modules

## Audit command (for re-runs)

```bash
cd F:\ROBOTAI\xiaozhi-esp32
git grep -nE 'https?://|wss?://' main/ components/ | grep -v -E 'build|managed_components|\.md:|//.*http|@.*http'
git grep -nE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b' main/ | grep -v -E '0\.0\.0\.0|127\.0\.0\.1|255\.255\.255\.255|192\.168\.[0-9]+\.[0-9]+ # ok|/255'
```
