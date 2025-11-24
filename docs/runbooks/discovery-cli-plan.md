# Discovery CLI Integration Plan

## Goals
- Surface network discovery in `kitty-cli shell` so operators can trigger scans, view devices, and approve/reject them.
- Add light-weight fingerprints for ESP32/Raspberry Pi candidates and expose confidence/type hints in CLI output.
- Keep automation optional and auditable (no surprise Wi-Fi provisioning by default).

## Phases
1) **CLI wiring (current)**
   - Commands: `discover scan`, `discover status <id>`, `discover list [filters/search]`, `discover approve <id> [--notes]`, `discover reject <id>`.
   - Target API: discovery service (`DISCOVERY_BASE`, default `http://localhost:8500` or gateway proxy).
   - Output: tables with type, IP, hostname, vendor/model, services, last_seen, confidence, approved.
2) **Fingerprinting**
   - Enrich discovery service classification: MAC OUI (Espressif/Raspberry Pi), mDNS names, service banners (`_ssh._tcp`, `_esphomelib._tcp`, `_workstation._tcp`), port hints (22/80/443).
   - Add `candidate_kind` + confidence to API and display in CLI.
3) **Onboarding helpers (optional/guarded)**
   - Offer manual steps or guarded helpers for ESP32/RPi onboarding (SSID/AP mode, Wi-Fi credential push where supported).
   - Require explicit `--unsafe-auto` (default off); log all actions.

## Non-goals (for now)
- Fully automated Wi-Fi provisioning for arbitrary firmware (too brittle).
- Managing device credentials inside CLI (keep to ops runbooks).

## Risks / Mitigations
- **Long scans/timeouts:** keep CLI timeouts generous; poll status instead of blocking.
- **False positives:** present `candidate_kind` as a hint with confidence; keep approval manual.
- **Security:** no automatic network joins; audit approve/reject actions.
