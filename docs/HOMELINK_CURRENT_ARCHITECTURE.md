# HomeLink — current architecture (HL-00 baseline)

Captured 2026-09-24 from the build that is actually running, not from memory.
Every claim below was read out of source or measured against the live system; where
something could not be answered from source it is marked UNKNOWN rather than guessed.

## Real working project path

| | |
|---|---|
| **Working build** | `C:\Homelink` |
| Stale copy (do not use) | `F:\Homelink` — July-era files, no camera-roll fix, junk files in `backend/` |
| How this was proven | SHA-256 of a file served by the live port 8080 matched **only** `C:\Homelink`'s copy |

`F:\Homelink` uniquely held `homelinksession.md`; that document also exists on GitHub and the
GitHub copy is newer, so the GitHub copy is authoritative.

## Startup flow

```
start_homelink_app.bat
  └─ python serve_app.py                    → app on :8080, serves dist/
backend\start_guard.bat
  └─ python camera_server.py                → camera guard on :7171 (per machine)
backend\main.py                             → chat proxy (see "Chat", below)
```

The app server must be started with an **absolute** script path. `serve_app.py` derives its
root from `os.path.dirname(os.path.abspath(__file__))`, so launching it as a bare relative
`serve_app.py` from the wrong working directory silently serves the *other* HomeLink folder.
This was observed on 2026-09-24.

## Ports

| Port | Service | Host |
|---|---|---|
| 8080 | HomeLink app (`serve_app.py`, serves `dist/`) | AlienWare |
| 7171 | Camera guard (`camera_server.py`) | every guard node |
| 6969 | Currently **Lana TV** (`F:\Lana TV\lana_server.py`), not HomeLink's proxy | AlienWare |
| 7070 | Lana OS Link (`C:\LANA\lana_os_link.py`) | AlienWare |
| 7060 | LANA control agent (remote shell/input) | LenovoMonitor, RedKryptonite |

## Node map

| Node | Tailscale | Cameras |
|---|---|---|
| AlienWare | `100.107.136.88` | 3 (C920, DroidCam, desktop mirror `screen:0` as cam 10) |
| LenovoMonitor | `100.115.8.121` | 2 (Logi C270, Integrated) |
| RedKryptonite | `100.110.73.8` | 2 (C525, HP TrueVision) |

LenovoMonitor answers on Tailscale but **not** on its LAN address — its firewall has a rule for
`HomeLink App 8080` and none for 7171. The app uses the Tailscale URLs, so this is not
currently user-visible.

## Camera implementation — IMPLEMENTED

**Video transport is MJPEG over plain HTTP.** There is no WebSocket, no WebRTC and no
frame-by-frame polling loop; a browser `<img>` element holds one long-lived multipart response.

- `services/cameraService.ts` — `guardMediaUrl()` builds `/stream`, `/snapshot` and `/events`
  URLs. The API key travels in the **query string** because, as the source comment states,
  `<img>` tags cannot send headers.
- `components/CameraView.tsx` — each tile renders
  `<img src={guardMediaUrl(node.url, '/stream', key, { cam, cacheBust })}>`.

Guard endpoints in use: `/` (status), `/stream`, `/snapshot`, `/events`, `/discover`,
`/rescan`, `/wake`, `/audio`.

## Frame refresh and reconnect — IMPLEMENTED

| Mechanism | Where | Interval |
|---|---|---|
| Whole-grid stream reconnect (self-heal a stalled MJPEG) | `CameraView.tsx` `STREAM_REFRESH_MS` | **120 s** |
| Per-tile retry on image error | `onError` → `scheduleRetry` → `retryTick` | on failure |
| Guard status poll | `refreshStatus` | 10 s |
| Motion events poll | `refreshEvents` | 30 s |
| Node discovery | `runDiscovery` | **60 s** (`DISCOVERY_INTERVAL_MS`) |
| Clock tick (drives the overlay) | `setClock` | 1 s |

Reconnection is forced by changing the `<img>` React `key` and the `cacheBust` query
parameter, which makes the browser drop the old connection and open a new one.

A manual **RECONNECT** control calls `wakeGuardCameras()`, which POSTs `/rescan` (rebuilds the
camera set, recovering a webcam moved to a different USB port) and falls back to `/wake` on
older guards that return 405.

## Date/time overlay — IMPLEMENTED

Client-side, driven by the 1 s `clock` state in `CameraView.tsx`:

- long form `YYYY-MM-DD HH:MM:SS` for the tile stamp
- short form `MM/DD HH:MM` for compact contexts
- a `REC` indicator renders only when the system is **armed** and the tile is live

The overlay is drawn by the browser over the video; it is **not** burned into the JPEG by the
guard. Verified live on 2026-09-23 showing `REC 2026-09-23 23:57:03`.

## Camera watchdog — IMPLEMENTED (split client/server)

- **Client:** the 120 s refresh plus per-tile retry above.
- **Server (`camera_server.py`):** black-frame recovery, frozen-frame recovery (deliberately
  skipped for `screen:` sources, since an idle desktop legitimately produces identical frames),
  and `/rescan` to rebuild the camera set live.

## Camera roll (still capture) — PARTIAL

Motion snapshots and manual captures write to a configured roll path. Current state:

| Node | Roll | Ready |
|---|---|---|
| AlienWare | `\\REDKRYPTONITE\PixServer\Camera Roll` | intermittent |
| LenovoMonitor | `X:\Camera Roll` | **false** — `X:` is a *mapped drive*, and mapped drives are per-user, so a service/task cannot see it. Use the UNC path instead. |
| RedKryptonite | `\\REDKRYPTONITE\PixServer\Camera Roll` | true |

An unreachable roll used to hang the entire guard. Since 2026-08-31 the roll probe runs under
`CAMERA_ROLL_PROBE_TIMEOUT` (3 s) with the answer cached for `CAMERA_ROLL_CACHE_SEC`, so losing
the roll now only pauses still-saving. **Both remote nodes were still running the pre-fix build
until 2026-09-24** and had wedged because of it.

## Chat / Lana integration — PARTIAL

`services/chatService.ts` `streamChat()` POSTs to `${serverUrl}/chat` and reads a streamed
response body incrementally.

The configured `serverUrl` is `http://100.107.136.88:6969`. **Port 6969 is currently served by
Lana TV (`lana_server.py`), not by HomeLink's `backend/main.py`.** Lana TV does expose a `/chat`
route, so the tab is not dead, but the HomeLink proxy in `backend/main.py` is not the process
answering. The app's NEURAL tab was showing `ALIENWARE UPLINK SEVERED` on 2026-09-23.

Known defect, unchanged by this checkpoint: in `chatService.ts` a server-sent `parsed.error` is
thrown inside the same `try` that swallows partial-JSON chunks, so a real backend error can be
silently discarded and present as an empty assistant reply.

## LM Studio integration — LEGACY / UNVERIFIED

`backend/lm_studio_client.py`, `backend/lana_server_fixed.py` and `backend/vision_router_fixed.py`
are committed but are **not** the code path serving any live port. LM Studio historically listens
loopback-only on `127.0.0.1:1234`. Not exercised during this checkpoint.

## Mobile / phone view — PARTIAL

No dedicated mobile code path exists: there is no `matchMedia`, viewport-width branch or
phone-specific component in `App.tsx` or `CameraView.tsx`. Layout adapts through CSS/utility
classes only. Phones reach the app over Tailscale and must allow insecure content, because the
app is served over plain HTTP.

## Configuration locations

| What | Where |
|---|---|
| App settings (server URL, API key, camera URLs) | browser `localStorage` key `homelink_settings` |
| Guard camera overrides / extra sources | `backend/guard_cameras.json` |
| Gemini key | `.env.local` (gitignored; **not** committed) |
| Per-machine remote-control token | `redkryptonite-setup/redkryptonite_lana_token.txt` (**not** committed) |

## Known issues

1. **Guard wedge (root cause found, fixed 2026-09-24).** A pre-2026-08-31 `camera_server.py`
   touches the camera roll on every `/status` with no timeout. With a dead roll the guard keeps
   the port open but stops answering — including on its own localhost. Both remote nodes were
   in this state. Fixed by installing the current build on each.
2. **Latency / freeze:** MJPEG over HTTP with a 120 s blind reconnect means a stalled stream can
   show a frozen frame for up to two minutes before the client self-heals. Not addressed here.
3. **Shared API key is hardcoded** in `App.tsx`, `backend/main.py`, `backend/camera_server.py`,
   `services/chatService.ts` and `redkryptonite-setup/update_guard.ps1`, and is already present
   in git history. Rotation recommended; see the HL-00 entry in `homelinksession.md`.
4. **`serve_app.py` served the wrong folder** when launched with a relative path (see Startup).
5. **LenovoMonitor has no firewall rule for 7171** — Tailscale only.
6. Chat error swallowing in `chatService.ts` (above).

## Component status summary

| Component | Status |
|---|---|
| Live camera display (MJPEG `<img>`) | IMPLEMENTED |
| Stream refresh / reconnect | IMPLEMENTED |
| Date/time overlay + REC light | IMPLEMENTED |
| Camera watchdog (client + server) | IMPLEMENTED |
| Node auto-discovery | IMPLEMENTED |
| Per-camera live audio (`services/liveAudio.ts`, Web Audio) | IMPLEMENTED |
| Camera roll / still capture | PARTIAL (Lenovo roll unreachable) |
| Chat / Lana uplink | PARTIAL (port 6969 owned by Lana TV) |
| Mobile-specific view | PARTIAL (CSS-responsive only) |
| LM Studio backends (`*_fixed.py`, `lm_studio_client.py`) | LEGACY / UNVERIFIED |
| WebSocket transport | UNUSED (absent) |
| WebRTC transport | UNUSED (absent) |
| Node grid minimum slots (`MIN_SLOTS = 4`) | IMPLEMENTED |
