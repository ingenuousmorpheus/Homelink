# HomeLink Session — Reliability, Low-Latency Camera, and Lana Remote Console Plan

**Created:** 2026-09-23  
**Repository:** ingenuousmorpheus/Homelink  
**Source of truth:** GitHub main  
**HEAD inspected:** dd4cb815dfc65ef9894f43a8ef7659ca89370717  
**Current repository visibility:** public

---

# 0. Mission

HomeLink is already useful as a mobile/remote bridge into the home AI stack.

The next goal is not to turn it into a completely different app. The goal is to make the current concept dependable enough that it can stay open for hours without stale camera frames, connection drift, or uncertainty about whether the picture is actually live.

Target identity:

> **HomeLink = the private remote console for the home AI network: live view, AI chat, system status, and safe device/session monitoring over the user's own network/Tailscale.**

Near-term priority:

~~~text
STABILITY
→ VIDEO FRESHNESS
→ LOWER LATENCY
→ SELF-RECOVERY
→ ONE CLEAN BACKEND
→ BETTER DEVICE/SESSION MONITORING
~~~

Do not start by adding lots of new features.

---

# 1. Important Finding From This GitHub Audit

The current GitHub repository does **not** contain the live camera-view implementation described by the owner.

The repository contains:

- React/Vite mobile-friendly chat frontend
- HomeLink settings and connection diagnostics
- a FastAPI LM Studio proxy
- an older Flask LANA server path
- LM Studio client/config
- one-shot OpenCV vision capture
- vision-to-LM-Studio routing
- connection diagnostic scripts

The current repo's camera code in backend/vision_router_fixed.py captures a **single frame per request**:

~~~text
open VideoCapture(0)
→ wait 0.2 sec
→ read one frame
→ release camera
→ JPEG/base64
→ send to vision model
~~~

That is not a persistent live camera stream.

Therefore the exact production bug:

> "camera sometimes freezes while the date/time overlay continues updating"

cannot be reproduced from the source currently stored in GitHub.

That symptom strongly suggests that the UI/application loop is still alive while the **video frame source or transport has stalled**. The clock should never be used as proof that the video is live.

**HL-00 must first synchronize the actual current working HomeLink code into GitHub before changing the camera path.**

Do not discard the working version on the user's PC merely because this repository is older.

---

# 2. Current Repository Architecture

## Frontend

~~~text
App.tsx
components/
    ChatMessage.tsx
    SettingsModal.tsx
services/
    chatService.ts
~~~

Stack:

- React 19
- TypeScript
- Vite
- mobile-friendly web UI
- streaming chat through fetch/SSE-style response parsing
- settings persisted in browser localStorage

Current purpose:

~~~text
phone/browser
→ HomeLink proxy
→ LM Studio
~~~

## Backend path A — FastAPI proxy

backend/main.py provides:

- root status
- POST /chat
- GET /models
- LM Studio proxy to localhost
- streaming response forwarding
- simple shared-key authentication on protected routes

This is the backend that most closely matches the current React frontend.

## Backend path B — legacy LANA Flask server

backend/lana_server_fixed.py is a different server architecture.

It references files/modules not currently present in this repository, including some combination of:

- intent_engine
- actions
- vision_router
- vision_state
- lana_manifest.json

Treat it as **legacy/incomplete inside this repo** until the actual working local code is synchronized.

Do not maintain two competing HomeLink backends long term.

## Vision

Current GitHub vision path:

~~~text
OpenCV snapshot
→ JPEG/base64
→ LM Studio vision model
→ text response
~~~

Useful for "what do you see?" requests.

It should remain available even after live streaming is added, but **snapshot inference and live video transport must become separate systems**.

The vision model does not need every live frame.

---

# 3. Problems To Fix Before Expansion

## P0 — GitHub is missing the actual live camera build

The first task is to protect and synchronize the code currently running on the owner's machine.

GitHub is the source of truth after that reconciliation.

## P0 — Camera freshness is not represented

A UI clock can keep updating while the last decoded camera frame remains frozen.

The UI needs separate indicators for:

~~~text
APP TIME
VIDEO CAPTURE TIME
LAST FRAME RECEIVED
FRAME SEQUENCE
FRAME AGE
TRANSPORT STATE
~~~

A frame older than the configured threshold must visibly show STALE VIDEO instead of appearing live.

## P0 — Backend duplication / configuration drift

The repo currently has multiple contradictory paths:

- FastAPI proxy
- Flask LANA server
- docs referring to different ports
- hard-coded addresses in several files

This makes failures harder to diagnose and can create latency/reconnect confusion.

Long term HomeLink should expose one gateway service.

## P0 — Public-repo security cleanup

The current public repo contains a fixed shared HomeLink authentication secret in source and several machine/network addresses.

Also, vite.config.ts currently defines a Gemini API environment value into frontend build-time JavaScript.

Even if it is unused, **private API credentials must never be compiled into the browser bundle**.

Target rule:

~~~text
PUBLIC CODE
≠
PUBLIC CREDENTIALS
~~~

HomeLink can remain open source while all identity, tokens, device addresses, camera data, and private configuration stay local.

---

# 4. Target Architecture

~~~text
                 PHONE / TABLET / LAPTOP
                          │
                    HomeLink PWA
                          │
          ┌───────────────┼────────────────┐
          │               │                │
       WebRTC          WebSocket        HTTPS/REST
       video           telemetry          commands
          │               │                │
          └───────────────▼────────────────┘
                    HOMELINK GATEWAY
                          │
          ┌───────────────┼────────────────────┐
          │               │                    │
    Camera Worker     Lana OS Link        Device Monitor
          │               │                    │
    hardware capture   chat/tools          service health
          │
    Frame Health / Watchdog
~~~

HomeLink should be the presentation/control layer.

Lana OS Link remains the AI operating system.

HomeLink should not duplicate Lana's internal reasoning or tool architecture.

---

# 5. Camera Architecture V2

## Separate live video from AI vision

These are different workloads.

Live viewing needs:

- low latency
- continuous frames
- adaptive bitrate
- reconnection
- stale-frame detection

AI vision needs:

- selected snapshots
- occasional sampled frames
- full-resolution image when useful

Target:

~~~text
CAMERA
   │
   ├── Live Video Track ──→ WebRTC ──→ HomeLink
   │
   └── Snapshot Tap ──────→ Vision Model
~~~

Do not send every live camera frame through the LLM.

---

# 6. Recommended Live Transport

## Primary: WebRTC

Use WebRTC as the preferred live-camera transport.

Why:

- designed for low-latency media
- old frames can be dropped instead of building delay
- built-in jitter handling
- bitrate adaptation
- connection-state events
- browser-native client support

Possible Python-side implementation:

~~~text
FastAPI
+
aiortc
+
persistent camera worker
~~~

Do not commit to aiortc until HL-00 confirms how the current working camera build captures video.

If the working build already uses another good WebRTC implementation, preserve it.

## Fallback

Maintain a low-complexity snapshot/MJPEG or JPEG-over-WebSocket mode for troubleshooting and weak devices.

The fallback is not the primary high-quality mode.

---

# 7. Persistent Camera Worker

Do not repeatedly open and close the camera for every live frame.

Target:

~~~text
camera process starts once
→ owns device handle
→ continuously reads latest frame
→ stores only newest frame
→ consumers read latest frame
~~~

Important rule:

> **Never allow a slow consumer to create an ever-growing frame queue.**

For live monitoring, old frames are useless.

Use a latest-frame buffer:

~~~text
frame N
frame N+1
frame N+2

slow viewer asks
→ return N+2
→ discard stale queued frames
~~~

This prevents latency from increasing over time.

---

# 8. Frame Freshness Contract

Every captured frame should have metadata equivalent to:

~~~json
{
  "camera_id": "alienware-front",
  "sequence": 193842,
  "captured_at_monotonic": 123456.789,
  "captured_at_wall": "ISO timestamp",
  "width": 1280,
  "height": 720
}
~~~

Client tracks:

- last sequence received
- last frame receive time
- frame age
- FPS
- connection state

UI examples:

~~~text
LIVE · 24 FPS · 86 ms
LIVE · 12 FPS · 310 ms
STALE · last frame 4.8 s ago
RECONNECTING
CAMERA OFFLINE
~~~

The wall-clock date/time overlay remains independent.

---

# 9. Camera Freeze Watchdog

This directly addresses the owner's reported failure.

If:

~~~text
clock moves
but
frame sequence does not move
~~~

then HomeLink has a frozen stream.

Recovery state machine:

~~~text
FRAME HEALTHY
    ↓ no new frame for threshold
SUSPECT
    ↓
request keyframe / refresh track
    ↓
RECONNECTING
    ↓ still stalled
restart camera worker
    ↓ still stalled
CAMERA OFFLINE + visible error
~~~

Suggested initial thresholds for testing, not final tuning:

- warn after approximately 1.5–2 seconds with no new frame
- reconnect transport after approximately 3 seconds
- restart capture device after repeated reconnect failure

Use measured results to tune these.

Never silently leave a frozen frame labeled LIVE.

---

# 10. Latency Measurement

Before optimizing, instrument the full path.

Measure:

~~~text
capture timestamp
→ encode start/end
→ send
→ receive
→ decode
→ paint
~~~

Record:

- capture FPS
- delivered FPS
- encode time
- bitrate
- dropped frames
- frame age
- RTT
- WebRTC packet loss/jitter where available
- reconnect count
- camera restarts

Do not use "it feels faster" as the acceptance test.

Primary user metric:

> **How old is the picture currently shown on screen?**

---

# 11. Performance Strategy

Support quality modes:

~~~text
AUTO
HIGH       720p/1080p where stable
BALANCED   ~720p with adaptive FPS
LOW DATA   360p/480p
SNAPSHOT   manual refresh / AI vision only
~~~

AUTO should react to:

- RTT
- packet loss
- decoder performance
- current frame age

Prefer dropping quality/FPS over allowing latency to grow.

Later, where available, evaluate hardware H.264 encoding instead of expensive CPU JPEG loops.

---

# 12. HomeLink Gateway

Long term there should be one HomeLink backend process.

Recommended responsibilities:

~~~text
HomeLink Gateway
├── /health
├── /api/chat
├── /api/devices
├── /api/cameras
├── /api/sessions
├── /api/snapshot
├── /ws/events
└── /webrtc/*
~~~

The gateway talks locally to:

- Lana OS Link
- camera service
- LM Studio only when needed
- host/service monitor

Do not expose LM Studio directly to the phone.

---

# 13. Lana OS Link Integration

HomeLink should become a **remote window into Lana OS Link**, not a second Lana.

Target:

~~~text
HomeLink
→ Lana OS Link API
→ Lana reasoning / memory / tools
~~~

HomeLink provides:

- remote chat
- Lana online/offline state
- current activity
- optional avatar/status snapshot
- safe session monitoring
- selected camera view
- notifications

Action permissions remain governed by Lana OS Link.

HomeLink should not bypass Lana's permissions.

---

# 14. Session / Agent Monitor

A useful future HomeLink screen:

~~~text
HOME AI STATUS

LANA OS LINK        ONLINE
LM STUDIO           ONLINE
Avatar              ONLINE
Codex session       ACTIVE
Claude session      IDLE
Second PC           ONLINE
Camera 1            LIVE 82 ms
Camera 2            OFFLINE
~~~

This is read-only first.

Remote execution/control should be a separate later permission layer.

---

# 15. Multi-Device / Multi-Camera Direction

Eventually each machine can expose a lightweight HomeLink node.

~~~text
Alienware
 ├── camera
 ├── screen/status
 └── Lana services

Second PC
 ├── camera
 ├── screen/status
 └── compute services

Laptop
 └── camera
~~~

Each node advertises:

- stable device ID
- friendly name
- capabilities
- health
- camera list

HomeLink can then show a grid without hard-coding IP addresses.

Tailscale/MagicDNS names should be preferred over fixed addresses where practical.

---

# 16. Networking

HomeLink already assumes a trusted home/Tailscale environment.

Improve that model instead of asking browsers to permanently allow insecure mixed content.

Preferred direction:

~~~text
HTTPS HomeLink origin
+
Tailscale private network
+
same-origin API/WebSocket/WebRTC signaling
~~~

Evaluate Tailscale Serve or another local HTTPS reverse-proxy arrangement during the networking phase.

Do not expose camera or control ports directly to the public internet.

---

# 17. Security Rules

Before further feature growth:

1. remove hard-coded shared secrets from source
2. rotate any credential that has been used while committed publicly
3. remove API-key injection from the frontend bundle
4. keep local device/network config outside Git
5. restrict CORS instead of permanent wildcard where possible
6. bind sensitive upstream services to localhost/private interfaces
7. require authentication on control/snapshot/video signaling routes
8. log security events without logging secrets
9. never include camera images in Git or ordinary application logs

HomeLink may remain public/open-source.

Personal data stays local.

---

# 18. Reliability State Machine

Every remote subsystem should expose explicit state.

Camera:

~~~text
UNKNOWN
CONNECTING
LIVE
DEGRADED
STALE
RECONNECTING
OFFLINE
ERROR
~~~

Lana:

~~~text
UNKNOWN
ONLINE
BUSY
DEGRADED
OFFLINE
~~~

Do not reduce everything to one green/red dot.

---

# 19. Logging / Diagnostics

Add a small rotating local diagnostic log.

Camera events:

~~~text
camera_open
first_frame
frame_stale
transport_disconnect
transport_reconnect
camera_restart
camera_recovered
camera_failed
~~~

Network events:

~~~text
gateway_connect
gateway_disconnect
RTT change
authentication failure
upstream Lana unavailable
~~~

Never log:

- raw auth tokens
- full private prompts by default
- camera frames
- voice recordings
- secrets

Add a **Copy Diagnostic Report** button that includes only safe technical state.

---

# 20. Phased Build Plan

## HL-00 — Protect Current Working Build + Baseline Audit

This is mandatory because GitHub does not currently contain the camera implementation the owner is using.

Tasks:

- inspect local HomeLink working directory
- compare it with GitHub main
- protect all uncommitted/local-only working files
- identify the actual camera implementation
- run current app before changing anything
- document frontend/backend/service topology
- establish GitHub as source of truth only after reconciliation
- record baseline latency and camera-freeze behavior

Create:

docs/HOMELINK_CURRENT_ARCHITECTURE.md

Gate:

> The exact version the owner currently uses is recoverable from GitHub and its current behavior is documented.

## HL-01 — Security + Configuration Cleanup

Tasks:

- eliminate fixed shared secret from source
- rotate credentials that were committed and actually used
- remove frontend Gemini/API-key injection
- create local config / environment template
- centralize server URL and ports
- eliminate conflicting 8000/6969 docs/settings
- narrow CORS
- keep Tailscale/private networking

Gate:

> A public clone contains no usable private credential or personal network identity.

## HL-02 — One Gateway

Tasks:

- select the current working server as the migration base
- consolidate duplicate FastAPI/Flask roles
- expose one health model
- connect HomeLink to Lana OS Link through a clean adapter
- preserve working chat streaming

Gate:

> The mobile client talks to one HomeLink gateway and there is one documented startup path.

## HL-03 — Camera Instrumentation

Before replacing transport, add:

- sequence number
- capture timestamp
- client receive timestamp
- frame age
- delivered FPS
- stale state
- camera status

Gate:

> When video freezes, HomeLink can prove exactly where and when it became stale.

## HL-04 — Persistent Camera Worker

Tasks:

- keep camera open
- latest-frame buffer
- no unbounded frame queues
- clean open/close lifecycle
- device-loss detection
- camera restart function

Gate:

> Camera can run locally for at least 60 minutes without capture deadlock or growing latency.

## HL-05 — WebRTC Live Video

Tasks:

- WebRTC signaling through HomeLink gateway
- low-latency video track
- adaptive bitrate/FPS
- connection state telemetry
- reconnect support
- fallback snapshot mode

Gate:

> On the home network/Tailscale, the displayed frame remains near-live and does not accumulate multi-second delay during normal use.

## HL-06 — Freeze Watchdog + Self-Healing

Tasks:

- stale-frame detector
- reconnect state machine
- camera-worker restart
- visible STALE/OFFLINE state
- recovery counters
- test simulated camera disconnects

Gate:

> A stalled camera either recovers automatically or clearly reports failure. It never shows an old image as live.

## HL-07 — Mobile/PWA Polish

Tasks:

- installable PWA
- responsive camera grid
- orientation handling
- efficient foreground/background reconnect
- avoid duplicate streams after app resume
- clear camera quality selector
- battery/data-aware mode

Gate:

> Repeated phone lock/unlock and browser background/resume cycles do not create duplicate sessions or stale video.

## HL-08 — Home AI Status Center

Tasks:

- Lana OS Link health
- LM Studio health
- model loaded state
- avatar runtime state
- second-PC state
- agent/session status
- camera status
- CPU/GPU/VRAM where useful

Gate:

> HomeLink shows whether the home AI system is healthy without opening each PC separately.

## HL-09 — Multi-Camera / Device Registry

Tasks:

- stable device IDs
- capability discovery
- no hard-coded IPs in UI
- multi-camera grid
- single-camera focus view
- per-camera health/latency

Gate:

> Adding a second machine/camera does not require editing HomeLink source code.

## HL-10 — Reliability Soak + Packaging

Tasks:

- 8-hour soak test
- repeated network disconnect/reconnect test
- camera unplug/replug test
- gateway restart test
- Lana restart test
- bounded logs
- one-click Windows startup / service or tray launcher
- version display

Gate:

> HomeLink can be left running as infrastructure rather than treated as a demo.

---

# 21. Acceptance Metrics

These are engineering targets, not permanent promises.

## Camera

- no silently frozen frame
- frame age shown internally and available to UI
- 60-minute camera test passes before HL-06
- 8-hour soak passes before HL-10
- automatic recovery from transport interruption where possible
- old frames are dropped instead of queued

## Chat

- streaming remains responsive
- disconnect is detected
- reconnect does not duplicate assistant output
- backend/Lana errors are distinguished

## Mobile

- app resume reconnects cleanly
- no duplicate camera sessions
- clear offline/degraded/stale indicators

---

# 22. Tests To Add

Suggested backend tests:

~~~text
tests/
    test_gateway_health.py
    test_auth.py
    test_camera_frame_sequence.py
    test_camera_stale_detector.py
    test_camera_latest_frame_buffer.py
    test_camera_restart.py
    test_lana_adapter.py
    test_config.py
~~~

Frontend coverage:

- connection state transitions
- stale video badge
- resume/reconnect behavior
- settings migration
- camera selector

Integration coverage:

~~~text
camera → gateway → client
Lana → gateway → chat stream
network loss → reconnect
camera loss → recovery
~~~

---

# 23. What Not To Do

Do not:

- rewrite HomeLink from scratch
- send every camera frame to an LLM
- queue live frames indefinitely
- label a frozen frame as LIVE
- expose LM Studio directly to the internet
- compile private API keys into frontend JavaScript
- depend on one hard-coded PC IP
- maintain two competing HomeLink servers forever
- turn remote monitoring into unrestricted remote execution without a permission design
- change Lana OS Link architecture merely to fix HomeLink video

---

# 24. First Practical Milestone

The first milestone is not a new feature.

~~~text
OPEN HOMELINK
     ↓
CAMERA CONNECTS
     ↓
FRAME AGE STAYS LOW
     ↓
PHONE CAN LOCK / RESUME
     ↓
NETWORK CAN DROP / RETURN
     ↓
CAMERA SELF-RECOVERS
     ↓
LANA CHAT STILL WORKS
     ↓
NO FROZEN FRAME PRETENDING TO BE LIVE
~~~

When that is reliable, expand HomeLink into the broader home-AI status center.

---

# 25. Immediate Next Engineering Task

Begin with **HL-00 only**.

Instructions for the next coding agent:

1. Inspect local HomeLink and run git status.
2. Do not reset, clean, delete, or overwrite local changes.
3. Fetch GitHub.
4. Compare the live working app to GitHub main.
5. Find the actual camera implementation used today.
6. Preserve/reconcile it into version control safely.
7. Run current frontend/backend.
8. Reproduce the reported stale-camera symptom if possible.
9. Measure camera FPS, frame update cadence, transport type, latency/frame age if available, and behavior when camera freezes.
10. Create docs/HOMELINK_CURRENT_ARCHITECTURE.md.
11. Update this session file with the HL-00 findings.
12. Test.
13. Review diff.
14. Commit and push normally.
15. Verify remote/local SHA.

Do not implement the WebRTC redesign until HL-00 establishes what is actually running now.

---

# 26. Source-of-Truth Rule

GitHub main is the authoritative HomeLink repository **after HL-00 reconciles the current live local build**.

Future HomeLink work begins:

~~~text
FETCH/PULL SAFELY
→ READ homelinksession.md
→ INSPECT ACTUAL CODE
→ RUN BASELINE
→ WORK
~~~

Future HomeLink work ends:

~~~text
TEST
→ UPDATE homelinksession.md
→ REVIEW DIFF
→ COMMIT
→ PUSH
→ VERIFY
~~~

Never destroy local work merely because GitHub differs.

---

# 27. Long-Term Product Identity

HomeLink should become the dependable remote face of the home AI environment:

~~~text
CAMERAS
+
LANA OS LINK
+
HOME COMPUTERS
+
AGENT / SESSION STATUS
+
PRIVATE TAILSCALE NETWORK
        ↓
     HOMELINK
        ↓
PHONE / TABLET / LAPTOP
~~~

The differentiator is not just remote access.

It is:

> **A self-healing, low-latency window into the user's local AI home network.**


---

# HL-00 CHECKPOINT — Executed 2026-09-24

**Executed:** 2026-09-24 00:20 America/New_York
**Working folder found:** `C:\Homelink`
**Starting GitHub HEAD:** `da411e82e2e2bede62b5013dba275aff1fe03d50` ("Add HomeLink reliability and low-latency roadmap")

### Goal

Execute HL-00 as specified in section 20: make GitHub contain the HomeLink build actually
running on this PC, without redesigning anything. Secondary, and unplanned: the owner reported
HomeLink down and the E drive unreadable, which had to be repaired before the baseline could be
captured at all.

This entry required real synthesis rather than routine execution — the "E drive" fault and the
"cameras dead" fault looked like one problem and were two unrelated ones, and the camera fault
had to be traced across three machines before any of it could be trusted.

### Starting State

- GitHub `main` held **23 tracked files** and no camera implementation, exactly as section 1 predicted.
- Two candidate folders existed: `C:\Homelink` and `F:\Homelink`. Neither was a git repository;
  no local clone existed anywhere.
- HomeLink's camera grid was not working. The owner reported the E drive as "accessible but
  HomeLink cannot read it."

### Changed

**Repairs (made before the baseline was captured, and part of it):**

- `F:\Lana TV\lana_emulator_catalog.py` — 9 occurrences of the dead `\\192.168.1.145\E` prefix
  repointed to `\\LENOVOMONITOR\Lana TV`.
- `F:\Lana TV\lana_roots.py` — added `\\LENOVOMONITOR\Lana TV` and `\\192.168.1.145\Lana TV`
  ahead of the dead `E` / `E$` candidates in `_DEFAULT_ROOT_SPECS`.
- `C:\HomeLink\backend\camera_server.py` **on LenovoMonitor and on RedKryptonite** — replaced the
  pre-2026-08-31 build with the current one (52372 bytes, contains `CAMERA_ROLL_PROBE_TIMEOUT`).
  Backups left beside each as `camera_server.py.bak-<stamp>`. Both guards restarted.
- `C:\Homelink\serve_app.py` — refuses to serve filenames matching `token|secret|password|
  credential|.env` out of `/guard-update/`, and refuses directory listings. Opt back in for an
  install with `HOMELINK_ALLOW_TOKEN_FETCH=1`.

**Reconciliation into GitHub:** 30 files staged. 21 previously absent (including
`components/CameraView.tsx`, `services/cameraService.ts`, `services/liveAudio.ts`,
`backend/camera_server.py`, `serve_app.py`, `start_homelink_app.bat`, all of
`redkryptonite-setup/`). `.gitignore` hardened; `.env.example` added; new
`docs/HOMELINK_CURRENT_ARCHITECTURE.md`.

**Preserved from GitHub, not overwritten:** `homelinksession.md` (this file), `README.md`,
`backend/HOMELINK_SETUP.md`.

### Verification

- **Working-build identification:** SHA-256 of `camera_server.py` fetched from the live port 8080
  matched `C:\Homelink`'s copy (`7D724DD7…`) and not `F:\Homelink`'s (`96B1206F…`).
- **E drive:** `net use \\192.168.1.145\E` returned **System error 59**; `net share` on
  LenovoMonitor showed no share named `E` — only `E$` (admin) and `Lana TV` → `E:\`.
  After the fix: media library **388 videos**, root state `ok`; game catalogue **10 games across
  6 consoles**, all reachable.
- **Guard wedge:** on both remote nodes, `Invoke-WebRequest http://127.0.0.1:7171/` failed **on the
  node's own localhost** while `netstat` showed the port LISTENING. Their `camera_server.py` was
  dated 2026-08-14 (Lenovo) and 2026-08-30 (RK) with `CAMERA_ROLL_PROBE_TIMEOUT` absent.
  `Test-Path '\\REDKRYPTONITE\PixServer\Camera Roll'` from the Lenovo took **6465 ms** to fail.
- **After repair:** all three guards HTTP 200, **7/7 cameras** `camera_ok=true`; real JPEG frames
  pulled from AlienWare (29192 bytes) and LenovoMonitor (56296 bytes); RedKryptonite held HTTP 200
  across 5 samples over 2 minutes.
- **UI:** Sentinel grid rendered with two LenovoMonitor tiles at **1280×720** actual pixels and the
  overlay reading `REC 2026-09-23 23:57:03`.
- **Commit safety:** staged set asserted to contain zero matches for `token`, `guard_events`,
  `node_modules`, `.env.local`, `.zip`, `.jpg`, `dist/`.

### Result

**PARTIAL.** The HL-00 gate is met: the owner's exact working version is now recoverable from
GitHub and its behavior is documented. Two items in the phase's task list are *not* satisfied —
see Gate/Blocker.

### Findings

1. **Section 1's prediction is CONFIRMED with evidence.** GitHub's camera code
   (`vision_router_fixed.py`, single frame per request) is not what runs. The working build streams
   **MJPEG** from `/stream` into an `<img>` tag.
2. **The "camera freezes while the date/time overlay keeps updating" symptom now has a measured
   root cause, and section 1 was right about the mechanism.** The overlay is client-side, driven by
   a 1 s `setClock` tick in `CameraView.tsx` — it is wholly independent of the video, so it keeps
   running when frames stop. What stops the frames is the **guard process wedging**: a pre-fix
   `camera_server.py` touches the camera roll on every `/status` with no timeout, and an unreachable
   SMB roll *blocks* rather than erroring. The port stays open, so the client sees a hung connection
   rather than a refusal, and the 120 s blind reconnect is the only thing that would ever clear it.
   Section 1's instruction — "the clock should never be used as proof that the video is live" — is
   exactly correct and should stay in the design.
3. **Two independent faults presented as one outage.** The dead `E` share (Lana TV media + game
   catalogue) and the wedged guards (HomeLink cameras) shared no cause. Fixing either alone would
   have left the system looking broken.
4. **`serve_app.py` resolves its root from `__file__`.** Launched as a bare relative `serve_app.py`
   from the wrong working directory it silently serves the *other* HomeLink folder. Observed live:
   port 8080 served `F:\Homelink`'s files for several minutes. Always launch with an absolute path.
5. **Security — an exposed remote-control credential.** `redkryptonite-setup/redkryptonite_lana_token.txt`
   was downloadable at `http://<alienware>:8080/guard-update/redkryptonite_lana_token.txt`
   (HTTP 200, hash-confirmed identical to the local file). That token grants shell and input control
   over RedKryptonite to anyone on the LAN or tailnet. `install_lana_arm.ps1` fetches it by design.
   Now blocked; **the file is excluded from git**. **Rotation is recommended** — it was readable for
   an unknown period.
6. **Shared API key is hardcoded and already in git history** — `App.tsx`, `backend/main.py`,
   `backend/camera_server.py`, `services/chatService.ts`, `redkryptonite-setup/update_guard.ps1`.
   Left as-is deliberately: moving it to env loading touches the live camera auth path in five
   places and is HL-01 work, not HL-00 ("do not redesign").
7. **LenovoMonitor's camera roll is `X:\Camera Roll`, a mapped drive.** Mapped drives are per-user,
   so the guard process cannot see it (`camera_roll_ready=false`). It needs the UNC path.
8. **LenovoMonitor has no firewall rule for 7171** — only `HomeLink App 8080`. It is reachable over
   Tailscale, which is what the app uses, so this is currently invisible.

### Latency / freeze behavior (baseline, as required by the phase)

- Transport: MJPEG over plain HTTP, one long-lived multipart response per tile.
- Blind whole-grid reconnect every **120 s** (`STREAM_REFRESH_MS`); per-tile retry on `onError`.
- Status poll 10 s, events 30 s, discovery 60 s, clock 1 s.
- Consequence: a stalled stream can display a frozen frame for **up to 2 minutes** before the client
  self-heals, and nothing in the client distinguishes "stream stalled" from "guard wedged."
- No numeric end-to-end latency figure was captured — there is no instrumentation to read one from.
  That is HL-03's job.

### Gate/Blocker

The HL-00 gate **passes**. Two task-list items remain unmet:

1. **"record baseline latency"** — not possible without instrumentation; deferred to HL-03.
2. **RedKryptonite stability is unproven beyond 2 minutes.** It wedged once during this session and
   was restarted. It also runs a HomeLink *client* (PID 22408) holding streams to all three guards,
   which is a plausible contributor. Not investigated further, per the instruction not to chase the
   intermittent freeze during HL-00.

### Do Not Redo

- **Do not re-investigate which folder is live.** It is `C:\Homelink`, proven by hash against the
  live server. `F:\Homelink` is a July-era copy; its only unique file was `homelinksession.md`, and
  GitHub's copy is newer.
- **Do not look for a share named `E` on LenovoMonitor.** There is none. Use `\\LENOVOMONITOR\Lana TV`
  (`E$` is admin-only and unusable by a non-elevated process).
- **Do not re-diagnose "guard listening but not answering."** It is the camera-roll hang. Check the
  build for `CAMERA_ROLL_PROBE_TIMEOUT` first.
- **Do not assume the overlay proves the video is live.** It is a separate 1 s client timer.
- **Do not search for WebSocket or WebRTC code** in the current build — there is none. WebRTC is
  HL-05, unstarted.

### Next Action

Begin **HL-01 (Security + Configuration Cleanup)**, starting with rotating the RedKryptonite agent
token, then moving the shared API key out of source into env/config.
