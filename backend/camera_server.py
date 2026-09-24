"""
HomeLink House Guard - Camera Server (multi-camera)
Run this on each laptop or PC that should contribute cameras.

Turns every webcam plugged into the machine into a security camera:
  GET  /                 -> status (per-camera health, armed state, event count)
  GET  /stream?cam=N     -> live MJPEG video stream for camera N
  GET  /snapshot?cam=N   -> single JPEG frame from camera N
  GET  /events           -> list of saved motion-event snapshots (with cam id)
  GET  /events/{name}    -> a saved motion snapshot image
  POST /arm              -> {"armed": true/false} toggle motion detection (all cams)

Cameras are auto-detected at startup (indices 0-9). Plugged in a new
camera? Restart the server (or reboot - it auto-starts).
Set CAMERA_INDEXES=0,1 to skip auto-detection.

Auth: every endpoint requires the shared secret, either as an
`X-API-Key` header or a `?key=` query param (query param is needed
because <img> tags in the app cannot send headers).
"""

import os
import re
import json as jsonlib
import ipaddress
import socket
import subprocess
import time
import threading
import urllib.request
import uuid as uuidlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict

import cv2
import numpy as np
import uvicorn
from fastapi import FastAPI, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, Response, FileResponse, JSONResponse

# Optional: only needed for "screen:N" desktop-mirror sources.
try:
    import mss as _mss
except Exception:                                          # pragma: no cover
    _mss = None

# --- CONFIGURATION ---
API_KEY = os.getenv("HOMELINK_KEY", "home-link-secret")   # same secret as main.py
PORT = int(os.getenv("PORT", "7171"))
CAMERA_INDEXES = os.getenv("CAMERA_INDEXES", "auto")       # "auto" or e.g. "0,1"
MAX_CAMERAS = int(os.getenv("MAX_CAMERAS", "10"))
FRAME_WIDTH = 1280
FRAME_HEIGHT = 720
# Windows device enumeration can hang forever on a half-registered USB device
# (typical after a webcam is moved to another port). Never block the cameras
# on it - these are the give-up deadlines, in seconds.
AUDIO_INIT_TIMEOUT = float(os.getenv("AUDIO_INIT_TIMEOUT", "15"))
DEVICE_ENUM_TIMEOUT = float(os.getenv("DEVICE_ENUM_TIMEOUT", "10"))
# Desktop mirror ("screen:0" sources). Lower than a webcam on purpose - a
# screen is mostly static and every frame is a full-size JPEG.
SCREEN_FPS = float(os.getenv("SCREEN_FPS", "10"))
JPEG_QUALITY = 70
STREAM_MAX_FPS = 15

# Motion detection tuning
MOTION_MIN_AREA = 4500        # min changed-pixel blob size to count as motion
MOTION_COOLDOWN_SEC = 12      # min seconds between saved motion snapshots (per cam)
MAX_EVENTS = int(os.getenv("MAX_EVENTS", "0"))  # 0 = keep every HomeLink still
EVENT_LIST_LIMIT = int(os.getenv("EVENT_LIST_LIMIT", "200"))

# Black-frame auto-recovery (a stuck USB webcam sometimes streams pure black)
BLACK_MEAN_THRESHOLD = 3.0    # mean pixel < this = "solid black" (real scenes never this low)
BLACK_RECOVER_SEC = 20        # seconds of solid black before one reopen attempt

# Frozen-frame auto-recovery: a hung webcam keeps handing back the SAME
# buffered frame forever - the picture looks fine but never changes. Real
# sensors always have noise, so byte-identical frames mean the device is stuck.
FROZEN_RECOVER_SEC = 45       # seconds of identical frames before reopening

# Live audio
AUDIO_MAX_SECONDS = 1800      # hard cap on one audio stream (zombie protection)

# Zombie-stream protection: phones that lock/lose signal leave MJPEG streams
# pumping into dead connections, eventually saturating the network. Streams
# hard-expire after this long; live viewers auto-reconnect (app refreshes
# its streams every 2 minutes), so nobody notices - but zombies die.
STREAM_MAX_SECONDS = 300

EVENTS_DIR = Path(os.getenv("HOMELINK_CAMERA_ROLL", r"X:\Camera Roll")).expanduser()
EVENTS_DIR_READY = False
EVENTS_DIR_LAST_WARNING = 0.0
EVENTS_DIR_CHECKED_AT = 0.0
# The camera roll may live on ANOTHER machine (UNC path). An unreachable SMB
# share does not fail fast, it blocks for the SMB timeout - and /status probes
# the roll on every request, which is enough to hang the entire guard. So the
# probe gets a deadline and its answer is cached.
CAMERA_ROLL_PROBE_TIMEOUT = float(os.getenv("CAMERA_ROLL_PROBE_TIMEOUT", "3"))
CAMERA_ROLL_CACHE_SEC = float(os.getenv("CAMERA_ROLL_CACHE_SEC", "30"))

# Optional IP/network cameras (RTSP/HTTP streams) live in this config file:
#   {"extra_sources": [{"url": "rtsp://user:pass@192.168.1.50:554/stream1", "name": "front door"}]}
# USB webcams need nothing here - they are auto-detected.
CONFIG_PATH = Path(__file__).resolve().parent / "guard_cameras.json"
NODE_ID = os.getenv("HOMELINK_NODE_ID", socket.gethostname()).strip() or "homelink-guard"

NODE_SLUG = re.sub(r"[^A-Za-z0-9_.-]+", "-", NODE_ID).strip("-._")[:40] or "homelink-guard"

# Matches current shared-roll names plus older HomeLink still names.
EVENT_PATTERNS = [
    re.compile(
        r"^(?P<kind>motion|capture)_(?P<node>[A-Za-z0-9_.-]+)_cam"
        r"(?P<cam>\d+)_(?P<stamp>\d{8}_\d{6})(?:_(?P<nonce>[0-9a-fA-F]{8}))?\.jpg$"
    ),
    re.compile(
        r"^(?P<kind>motion|capture)_cam(?P<cam>\d+)_"
        r"(?P<stamp>\d{8}_\d{6})(?:_(?P<nonce>[0-9a-fA-F]{8}))?\.jpg$"
    ),
    re.compile(r"^(?P<kind>motion)_(?P<stamp>\d{8}_\d{6})\.jpg$"),
]

app = FastAPI(title="HomeLink House Guard")

USB_BACKENDS = [
    cv2.CAP_DSHOW,
    cv2.CAP_MSMF,
    cv2.CAP_ANY,
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


def _run_with_timeout(fn, timeout: float, default=None, what: str = ""):
    """Run fn() on a throwaway thread and give up after `timeout` seconds.

    Windows audio/video device enumeration can hang INDEFINITELY when a USB
    webcam has been moved to another port and left a half-registered device
    behind. That must never take the camera server down with it - pictures
    matter more than microphone names.
    """
    box = {}

    def _target():
        try:
            box["v"] = fn()
        except Exception as e:
            box["e"] = e

    t = threading.Thread(target=_target, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        print(f"[guard] {what or fn.__name__} is hanging (>{timeout:.0f}s) - "
              f"continuing without it (wedged device driver?)")
        return default
    if "e" in box:
        print(f"[guard] {what or fn.__name__} failed: {box['e']}")
        return default
    return box.get("v", default)


def ensure_events_dir(log: bool = True) -> bool:
    """Is the camera roll writable right now? Never blocks the API.

    A dead UNC share blocks instead of erroring, so the actual mkdir runs under
    a deadline and the result is cached for CAMERA_ROLL_CACHE_SEC. Losing the
    roll pauses still-saving; it must never take the cameras offline.
    """
    global EVENTS_DIR_READY, EVENTS_DIR_LAST_WARNING, EVENTS_DIR_CHECKED_AT
    now = time.time()
    if EVENTS_DIR_CHECKED_AT and now - EVENTS_DIR_CHECKED_AT < CAMERA_ROLL_CACHE_SEC:
        return EVENTS_DIR_READY

    def _probe() -> bool:
        EVENTS_DIR.mkdir(parents=True, exist_ok=True)
        return True

    ok = bool(_run_with_timeout(_probe, CAMERA_ROLL_PROBE_TIMEOUT, default=False,
                                what=f"camera roll probe ({EVENTS_DIR})"))
    EVENTS_DIR_CHECKED_AT = time.time()
    EVENTS_DIR_READY = ok
    if not ok and log and now - EVENTS_DIR_LAST_WARNING > 60:
        EVENTS_DIR_LAST_WARNING = now
        print(f"[guard] WARNING: camera roll {EVENTS_DIR} unreachable - "
              f"stills paused, cameras keep streaming.")
    return ok


def parse_event_name(name: str) -> Optional[Dict[str, object]]:
    for pattern in EVENT_PATTERNS:
        match = pattern.match(name)
        if not match:
            continue
        groups = match.groupdict()
        return {
            "kind": groups.get("kind") or "motion",
            "node": groups.get("node"),
            "cam": int(groups.get("cam") or 0),
            "stamp": groups.get("stamp"),
        }
    return None


def home_link_event_files() -> List[Path]:
    if not ensure_events_dir(log=False):
        return []
    files = _run_with_timeout(
        lambda: list(EVENTS_DIR.glob("motion_*.jpg")) + list(EVENTS_DIR.glob("capture_*.jpg")),
        CAMERA_ROLL_PROBE_TIMEOUT, default=[], what="camera roll listing")
    return [path for path in files if parse_event_name(path.name)]


def make_event_path(kind: str, cam_id: int) -> Optional[Path]:
    if not ensure_events_dir():
        return None
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    nonce = uuidlib.uuid4().hex[:8]
    return EVENTS_DIR / f"{kind}_{NODE_SLUG}_cam{cam_id}_{stamp}_{nonce}.jpg"


def save_frame_still(kind: str, cam_id: int, frame) -> Optional[Path]:
    path = make_event_path(kind, cam_id)
    if path is None:
        return None
    if cv2.imwrite(str(path), frame, [cv2.IMWRITE_JPEG_QUALITY, 85]):
        return path
    print(f"[guard] WARNING: failed to write still image to {path}")
    return None


def save_jpeg_still(kind: str, cam_id: int, jpeg: bytes) -> Optional[Path]:
    path = make_event_path(kind, cam_id)
    if path is None:
        return None
    try:
        path.write_bytes(jpeg)
        return path
    except OSError as exc:
        print(f"[guard] WARNING: failed to write still image to {path}: {exc}")
        return None


ensure_events_dir()


def verify_key(x_api_key: Optional[str], key_param: Optional[str]) -> None:
    supplied = x_api_key or key_param
    if not supplied or supplied != API_KEY:
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")


class ScreenCapture:
    """Mirrors a monitor, quacking like a cv2.VideoCapture so the normal
    capture loop can treat a desktop exactly like a webcam.

    Screen grabs return instantly (unlike a webcam, which blocks until its
    next frame), so this paces itself - otherwise the capture thread would
    spin a core at hundreds of frames a second.
    """

    def __init__(self, monitor: int = 0, fps: float = 10.0):
        self._sct = _mss.mss()                # NOT thread-safe: one per thread
        mons = self._sct.monitors             # [0] = all screens joined, [1] = primary
        if monitor < 0:
            self._mon = mons[0]               # "screen:all" - every monitor side by side
        else:
            self._mon = mons[min(monitor + 1, len(mons) - 1)]
        self._interval = 1.0 / max(fps, 1.0)
        self._next_at = 0.0
        self._open = True

    def isOpened(self) -> bool:
        return self._open

    def read(self):
        if not self._open:
            return False, None
        wait = self._next_at - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        self._next_at = time.monotonic() + self._interval
        try:
            shot = self._sct.grab(self._mon)
        except Exception:
            return False, None
        frame = cv2.cvtColor(np.asarray(shot), cv2.COLOR_BGRA2BGR)
        # A 1440p/4K desktop is far more pixels than the grid can show, and
        # JPEG-encoding all of them per frame is what would actually hurt.
        h, w = frame.shape[:2]
        if w > FRAME_WIDTH:
            scale = FRAME_WIDTH / float(w)
            frame = cv2.resize(frame, (FRAME_WIDTH, max(1, int(h * scale))),
                               interpolation=cv2.INTER_AREA)
        return True, frame

    def release(self) -> None:
        self._open = False
        try:
            self._sct.close()
        except Exception:
            pass


def _parse_screen_source(source) -> Optional[int]:
    """'screen' / 'screen:0' -> monitor index, 'screen:all' -> -1. None if
    this source is not a screen at all."""
    if not isinstance(source, str):
        return None
    s = source.strip().lower()
    if s == "screen":
        return 0
    if not s.startswith("screen:"):
        return None
    rest = s.split(":", 1)[1].strip()
    if rest in ("all", "*"):
        return -1
    return int(rest) if rest.isdigit() else 0


class GuardCamera:
    """Owns one camera source - a USB webcam (int index), a network stream
    (rtsp:// or http:// URL), or a monitor on this machine ('screen:0').
    One capture thread feeds every viewer, so each source is opened exactly
    once no matter how many phones are watching."""

    def __init__(self, cam_id: int, source, armed_flag: "ArmedFlag", name: Optional[str] = None):
        self.cam_id = cam_id
        self.source = source                       # int (USB), URL, or "screen:N"
        self.name = name
        self.screen_monitor = _parse_screen_source(source)
        self.is_screen = self.screen_monitor is not None
        self.is_network = isinstance(source, str) and not self.is_screen
        self.is_usb = not isinstance(source, str)
        self.armed_flag = armed_flag
        self.lock = threading.Lock()
        self.frame_ready = threading.Condition(self.lock)
        self.latest_jpeg: Optional[bytes] = None
        self.frame_seq = 0
        self.camera_ok = False
        self.last_motion_saved = 0.0
        self.last_motion_seen: Optional[float] = None
        self._prev_gray = None
        self._stop = threading.Event()
        self._reopen = threading.Event()      # set by /wake to force a fresh device open
        self._dark_since: Optional[float] = None
        self._last_frame_sig: Optional[int] = None
        self._frozen_since: Optional[float] = None
        self._thread = threading.Thread(target=self._run, daemon=True)

    def request_reopen(self) -> None:
        """Force the capture thread to drop and reopen the device.
        Recovers a camera stuck delivering black/frozen frames."""
        self._reopen.set()

    def start(self) -> None:
        self._thread.start()

    def stop(self, timeout: float = 3.0) -> None:
        """Ask the capture thread to exit and release its device. Needed
        before a rescan: an open camera cannot be probed."""
        self._stop.set()
        if self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _open_capture(self) -> Optional[cv2.VideoCapture]:
        if self.is_screen:
            if _mss is None:
                print(f"[guard] Camera {self.cam_id}: screen capture needs the "
                      f"'mss' package (pip install mss)")
                return None
            try:
                return ScreenCapture(self.screen_monitor, fps=SCREEN_FPS)
            except Exception as e:
                print(f"[guard] Camera {self.cam_id}: could not open screen: {e}")
                return None
        if self.is_network:
            # RTSP/HTTP stream via FFmpeg (bundled with opencv-python)
            cap = cv2.VideoCapture(self.source, cv2.CAP_FFMPEG)
            if not cap.isOpened():
                cap.release()
                return None
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # keep latency low
            return cap
        # With several cameras on one USB controller there may not be
        # bandwidth for everyone at 720p - fall back to 480p rather than
        # letting a camera die.
        for width, height in ((FRAME_WIDTH, FRAME_HEIGHT), (640, 480)):
            for backend in USB_BACKENDS:
                cap = cv2.VideoCapture(self.source, backend)
                if not cap.isOpened():
                    cap.release()
                    continue
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                ok, _ = cap.read()
                if ok:
                    if (width, height) != (FRAME_WIDTH, FRAME_HEIGHT):
                        print(f"[guard] Camera {self.cam_id}: fell back to {width}x{height} (USB bandwidth)")
                    return cap
                cap.release()
        return None

    def _run(self) -> None:
        cap: Optional[cv2.VideoCapture] = None
        while not self._stop.is_set():
            # Manual wake (from /wake) or a fresh start both need a new device.
            if self._reopen.is_set():
                self._reopen.clear()
                if cap is not None:
                    cap.release()
                    cap = None
                self._prev_gray = None
                self._dark_since = None
                self._last_frame_sig = None
                self._frozen_since = None
                print(f"[guard] Camera {self.cam_id}: wake requested, reopening device.")

            if cap is None:
                cap = self._open_capture()
                if cap is None:
                    self.camera_ok = False
                    print(f"[guard] Camera {self.cam_id} not available, retrying in 5s...")
                    time.sleep(5)
                    continue
                print(f"[guard] Camera {self.cam_id} opened.")

            ok, frame = cap.read()
            if not ok or frame is None:
                print(f"[guard] Camera {self.cam_id}: frame grab failed, reopening...")
                self.camera_ok = False
                cap.release()
                cap = None
                time.sleep(2)
                continue

            self.camera_ok = True

            # Auto-recover a camera that's gone solid black (driver/exposure
            # hiccup). A genuinely dark night scene is never THIS black, so the
            # threshold is deliberately tiny. One reopen attempt, then leave it
            # alone (covered lens can't be fixed by reopening).
            if self.is_usb and self._is_black(frame):
                now = time.time()
                if self._dark_since is None:
                    self._dark_since = now
                elif now - self._dark_since > BLACK_RECOVER_SEC:
                    print(f"[guard] Camera {self.cam_id}: solid black {BLACK_RECOVER_SEC}s, reopening once.")
                    self._dark_since = None
                    cap.release()
                    cap = None
                    time.sleep(1)
                    continue
            else:
                self._dark_since = None

            # Auto-recover a FROZEN camera: the device keeps returning the
            # exact same buffered frame, so the tile shows a real picture that
            # never updates. Sensor noise makes identical frames impossible on
            # a healthy camera, so this only fires on a genuinely hung device.
            # ...but an idle DESKTOP legitimately produces byte-identical
            # frames, so this check must never run against a screen mirror.
            sig = None if self.is_screen else hash(frame.tobytes())
            now = time.time()
            if sig is not None and sig == self._last_frame_sig:
                if self._frozen_since is None:
                    self._frozen_since = now
                elif now - self._frozen_since > FROZEN_RECOVER_SEC:
                    print(f"[guard] Camera {self.cam_id}: frozen {FROZEN_RECOVER_SEC}s, reopening.")
                    self._frozen_since = None
                    self._last_frame_sig = None
                    cap.release()
                    cap = None
                    time.sleep(1)
                    continue
            else:
                self._last_frame_sig = sig
                self._frozen_since = None

            if self.armed_flag.armed:
                self._detect_motion(frame)

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
            if ok:
                with self.frame_ready:
                    self.latest_jpeg = buf.tobytes()
                    self.frame_seq += 1
                    self.frame_ready.notify_all()

        if cap is not None:
            cap.release()

    @staticmethod
    def _is_black(frame) -> bool:
        # mean intensity ~0 across the whole frame = sensor delivering black,
        # not a real (even dark) scene
        try:
            return float(frame.mean()) < BLACK_MEAN_THRESHOLD
        except Exception:
            return False

    def _detect_motion(self, frame) -> None:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.GaussianBlur(gray, (21, 21), 0)

        if self._prev_gray is None:
            self._prev_gray = gray
            return

        delta = cv2.absdiff(self._prev_gray, gray)
        self._prev_gray = gray
        thresh = cv2.threshold(delta, 25, 255, cv2.THRESH_BINARY)[1]
        thresh = cv2.dilate(thresh, None, iterations=2)
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        motion = any(cv2.contourArea(c) >= MOTION_MIN_AREA for c in contours)
        if not motion:
            return

        now = time.time()
        self.last_motion_seen = now
        if now - self.last_motion_saved < MOTION_COOLDOWN_SEC:
            return
        self.last_motion_saved = now

        path = save_frame_still("motion", self.cam_id, frame)
        if path:
            print(f"[guard] MOTION on cam {self.cam_id} -> saved {path}")
            prune_events()

    def wait_for_frame(self, last_seq: int, timeout: float = 5.0) -> Optional[bytes]:
        with self.frame_ready:
            if self.frame_seq == last_seq:
                self.frame_ready.wait(timeout=timeout)
            return self.latest_jpeg

    def snapshot(self) -> Optional[bytes]:
        with self.lock:
            return self.latest_jpeg


class ArmedFlag:
    """Shared armed state across every camera."""
    def __init__(self):
        self.armed = True


def prune_events() -> None:
    if MAX_EVENTS <= 0:
        return
    files = sorted(home_link_event_files(), key=lambda p: p.stat().st_mtime)
    for old in files[:-MAX_EVENTS]:
        try:
            old.unlink()
        except OSError:
            pass


def detect_camera_indexes() -> List[int]:
    if CAMERA_INDEXES != "auto":
        return [int(i) for i in CAMERA_INDEXES.split(",") if i.strip().isdigit()][:MAX_CAMERAS]
    found = []
    for i in range(MAX_CAMERAS):
        for backend in USB_BACKENDS:
            cap = cv2.VideoCapture(i, backend)
            try:
                if cap.isOpened():
                    ok, _ = cap.read()
                    if ok:
                        found.append(i)
                        break
            finally:
                cap.release()
    return found


armed_flag = ArmedFlag()
cameras: Dict[int, GuardCamera] = {}
started_at = time.time()


def load_extra_sources() -> List[dict]:
    """Network cameras (RTSP/HTTP) from guard_cameras.json."""
    if not CONFIG_PATH.is_file():
        return []
    try:
        cfg = jsonlib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        print(f"[guard] Could not read {CONFIG_PATH.name}: {e}")
        return []
    out = []
    for s in cfg.get("extra_sources", []):
        if isinstance(s, str):
            out.append({"url": s, "name": None})
        elif isinstance(s, dict) and s.get("url"):
            out.append({"url": s["url"], "name": s.get("name")})
    return out


def start_cameras() -> None:
    indexes = detect_camera_indexes()
    extras = load_extra_sources()
    if not indexes and not extras:
        indexes = [0]  # keep retrying index 0 so a later plug-in can recover
        print("[guard] No cameras detected yet - will keep retrying index 0.")
    # DirectShow names make it obvious which physical webcam a tile is - the
    # thing you actually want to know after moving cameras between USB ports.
    usb_names = _video_device_names()
    for i in indexes:
        cam = GuardCamera(i, i, armed_flag,
                          name=usb_names[i] if i < len(usb_names) else None)
        cameras[i] = cam
        cam.start()
    # network cameras get ids from 10 up so they never clash with USB indexes
    for n, extra in enumerate(extras):
        cam_id = 10 + n
        cam = GuardCamera(cam_id, extra["url"], armed_flag, name=extra["name"])
        cameras[cam_id] = cam
        cam.start()
    print(f"[guard] Watching cameras: {sorted(cameras)} "
          f"({len(indexes)} USB, {len(extras)} network)")


# ─────────────────────────────────────────────────────────────────────
#  LIVE AUDIO - stream each camera's own microphone
# ─────────────────────────────────────────────────────────────────────
# Both libraries are optional: without them the guard runs exactly as
# before, just with no audio (has_audio = false everywhere).


_sd = None


def _import_sounddevice():
    """PortAudio scans every audio device at import time, and a wedged USB
    mic makes that scan never return - so it is imported off the main thread.
    If it does finish later, audio simply starts working from then on."""
    global _sd
    try:
        import sounddevice as sd
        _sd = sd
        print("[audio] sounddevice ready")
    except Exception as e:                                # pragma: no cover
        print(f"[audio] sounddevice unavailable ({e}) - audio disabled")


_sd_thread = threading.Thread(target=_import_sounddevice, daemon=True)
_sd_thread.start()
_sd_thread.join(AUDIO_INIT_TIMEOUT)
if _sd is None and _sd_thread.is_alive():
    print(f"[audio] sounddevice still loading after {AUDIO_INIT_TIMEOUT}s - "
          f"starting the cameras now, audio will attach if it ever finishes")

try:
    from pygrabber.dshow_graph import FilterGraph as _FilterGraph
except Exception:
    _FilterGraph = None

# words that carry no identity when matching a camera to its microphone
_GENERIC_TOKENS = {
    "microphone", "mic", "audio", "video", "camera", "cam", "webcam",
    "hd", "usb", "device", "input", "pro", "full", "the", "and",
}


def _tokens(name: str) -> set:
    return {t for t in re.split(r"[^a-z0-9]+", (name or "").lower())
            if len(t) >= 3 and t not in _GENERIC_TOKENS}


def _video_device_names() -> List[str]:
    """DirectShow camera names, index-aligned with OpenCV's CAP_DSHOW."""
    if _FilterGraph is None:
        return []
    return _run_with_timeout(
        lambda: list(_FilterGraph().get_input_devices()),
        DEVICE_ENUM_TIMEOUT, default=[], what="DirectShow camera enumeration")


def _audio_input_devices() -> List[dict]:
    """Real microphone inputs, skipping Windows' aggregate/loopback shims."""
    if _sd is None:
        return []
    skip = ("sound mapper", "primary sound capture", "stereo mix", "midi",
            "wave mapper", "loopback")
    out = []
    devices = _run_with_timeout(lambda: list(_sd.query_devices()),
                                DEVICE_ENUM_TIMEOUT, default=None,
                                what="microphone enumeration")
    if devices is None:
        return []
    try:
        for idx, d in enumerate(devices):
            if d.get("max_input_channels", 0) < 1:
                continue
            name = d.get("name", "")
            if any(s in name.lower() for s in skip):
                continue
            out.append({"index": idx, "name": name,
                        "channels": int(d["max_input_channels"]),
                        "samplerate": int(d.get("default_samplerate") or 44100)})
    except Exception as e:
        print(f"[audio] could not list audio devices: {e}")
    return out


def _match_audio_devices() -> Dict[int, dict]:
    """cam_id -> microphone. Matches each camera to the mic built into that
    same physical device by name (e.g. 'HD Pro Webcam C920' -> 'Microphone
    (HD Pro Webcam C920)'). Explicit overrides in guard_cameras.json win:
        {"audio": {"0": "C920", "1": 18}}      # name substring or device index
    """
    mapping: Dict[int, dict] = {}
    mics = _audio_input_devices()
    if not mics:
        return mapping

    overrides = {}
    if CONFIG_PATH.is_file():
        try:
            overrides = (jsonlib.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                         .get("audio") or {})
        except (ValueError, OSError):
            overrides = {}

    vid_names = _video_device_names()
    used: set = set()

    for cam_id, cam in sorted(cameras.items()):
        if not cam.is_usb:
            continue                       # RTSP/screen audio not handled here

        # 1) explicit override
        ov = overrides.get(str(cam_id))
        if ov is not None:
            hit = None
            if isinstance(ov, int):
                hit = next((m for m in mics if m["index"] == ov), None)
            else:
                hit = next((m for m in mics if str(ov).lower() in m["name"].lower()), None)
            if hit:
                mapping[cam_id] = hit
                used.add(hit["index"])
                continue

        # 2) match this camera's device name against the mic names
        cam_name = vid_names[cam_id] if cam_id < len(vid_names) else ""
        want = _tokens(cam_name)
        if want:
            best, best_score = None, 0
            for m in mics:
                score = len(want & _tokens(m["name"]))
                if score > best_score and m["index"] not in used:
                    best, best_score = m, score
            if best and best_score > 0:
                mapping[cam_id] = best
                used.add(best["index"])
                continue

        # 3) single-microphone machine: it belongs to the only camera that
        #    doesn't already have one
        if len(mics) == 1 and not used:
            mapping[cam_id] = mics[0]
            used.add(mics[0]["index"])

    for cam_id, m in sorted(mapping.items()):
        print(f"[audio] cam {cam_id} -> [{m['index']}] {m['name']}")
    return mapping


audio_map: Dict[int, dict] = {}


class AudioSource:
    """One shared capture per microphone; every listener gets its own queue,
    so two phones listening to the same camera open the device only once."""

    _sources: Dict[int, "AudioSource"] = {}
    _guard = threading.Lock()

    def __init__(self, device: dict):
        self.device = device
        self.samplerate = min(int(device["samplerate"]), 48000)
        self.listeners: List[list] = []      # each: [deque, threading.Event]
        self.lock = threading.Lock()
        self.stream = None

    @classmethod
    def get(cls, device: dict) -> "AudioSource":
        with cls._guard:
            src = cls._sources.get(device["index"])
            if src is None:
                src = cls(device)
                cls._sources[device["index"]] = src
            return src

    def _callback(self, indata, frames, time_info, status):   # PortAudio thread
        chunk = bytes(indata)
        with self.lock:
            for buf, evt in self.listeners:
                if len(buf) > 40:            # ~2s backlog; drop rather than lag
                    buf.clear()
                buf.append(chunk)
                evt.set()

    def add_listener(self):
        from collections import deque
        entry = [deque(), threading.Event()]
        with self.lock:
            self.listeners.append(entry)
            need_stream = self.stream is None
        if need_stream:
            self.stream = _sd.RawInputStream(
                device=self.device["index"], channels=1, samplerate=self.samplerate,
                dtype="int16", blocksize=2048, callback=self._callback,
            )
            self.stream.start()
            print(f"[audio] opened [{self.device['index']}] {self.device['name']} "
                  f"@ {self.samplerate} Hz")
        return entry

    def remove_listener(self, entry):
        with self.lock:
            if entry in self.listeners:
                self.listeners.remove(entry)
            empty = not self.listeners
        if empty and self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None
            print(f"[audio] closed [{self.device['index']}] {self.device['name']}")


def _wav_header(samplerate: int, channels: int = 1, bits: int = 16) -> bytes:
    """WAV header for an open-ended stream (browsers accept the max size)."""
    import struct
    # open-ended stream: keep RIFF size (datasize + 36) inside uint32
    datasize = 0xFFFFFFFF - 36
    byte_rate = samplerate * channels * bits // 8
    return (b"RIFF" + struct.pack("<I", datasize + 36) + b"WAVE"
            + b"fmt " + struct.pack("<IHHIIHH", 16, 1, channels, samplerate,
                                    byte_rate, channels * bits // 8, bits)
            + b"data" + struct.pack("<I", datasize))


@app.get("/audio/devices")
def audio_devices(x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    """Inspect microphones and the camera->mic mapping (for troubleshooting)."""
    verify_key(x_api_key, key)
    return {
        "available": _sd is not None,
        "cameras": _video_device_names(),
        "microphones": _audio_input_devices(),
        "mapping": {str(k): v for k, v in audio_map.items()},
    }


@app.get("/audio")
def audio(cam: int = Query(0), x_api_key: Optional[str] = Header(None),
          key: Optional[str] = Query(None)):
    """Live microphone audio for one camera, as a streaming WAV."""
    verify_key(x_api_key, key)
    if _sd is None:
        raise HTTPException(status_code=503, detail="Audio support not installed on this node")
    device = audio_map.get(cam)
    if device is None:
        raise HTTPException(status_code=404, detail=f"No microphone mapped to camera {cam}")

    source = AudioSource.get(device)

    def generate():
        entry = source.add_listener()
        buf, evt = entry
        try:
            yield _wav_header(source.samplerate)
            started = time.time()
            while time.time() - started < AUDIO_MAX_SECONDS:
                if not buf:
                    if not evt.wait(timeout=5.0):
                        continue          # silence gap - keep the stream open
                    evt.clear()
                while buf:
                    yield buf.popleft()
        finally:
            source.remove_listener(entry)

    return StreamingResponse(generate(), media_type="audio/wav",
                             headers={"Cache-Control": "no-cache, no-store"})


@app.on_event("startup")
def startup() -> None:
    # detection probes each device; do it off the event loop
    def _boot():
        start_cameras()
        global audio_map
        if _sd is not None:
            audio_map = _match_audio_devices()
    threading.Thread(target=_boot, daemon=True).start()


def get_camera(cam: int) -> GuardCamera:
    if cam not in cameras:
        raise HTTPException(status_code=404, detail=f"No camera {cam}. Available: {sorted(cameras)}")
    return cameras[cam]


@app.get("/")
def status(x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    verify_key(x_api_key, key)
    cams = [
        {
            "id": idx,
            "camera_ok": cam.camera_ok,
            "last_motion": cam.last_motion_seen,
            "type": "screen" if cam.is_screen else ("network" if cam.is_network else "usb"),
            "name": cam.name,
            "has_audio": idx in audio_map,
            "audio_device": (audio_map.get(idx) or {}).get("name"),
        }
        for idx, cam in sorted(cameras.items())
    ]
    return {
        "status": "online",
        "service": "house-guard",
        "node_id": NODE_ID,
        "hostname": socket.gethostname(),
        "camera_ok": any(c["camera_ok"] for c in cams),   # legacy field
        "cameras": cams,
        "armed": armed_flag.armed,
        "uptime_seconds": int(time.time() - started_at),
        "last_motion": max((c["last_motion"] for c in cams if c["last_motion"]), default=None),
        "event_count": len(home_link_event_files()),
        "camera_roll": str(EVENTS_DIR),
        "camera_roll_ready": ensure_events_dir(log=False),
    }


@app.get("/stream")
def stream(cam: int = Query(0), x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    verify_key(x_api_key, key)
    camera = get_camera(cam)

    def generate():
        last_seq = -1
        frame_interval = 1.0 / STREAM_MAX_FPS
        stream_started = time.time()
        while time.time() - stream_started < STREAM_MAX_SECONDS:
            start = time.time()
            jpeg = camera.wait_for_frame(last_seq)
            if jpeg is None:
                time.sleep(0.5)
                continue
            last_seq = camera.frame_seq
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n"
                + f"Content-Length: {len(jpeg)}\r\n\r\n".encode()
                + jpeg
                + b"\r\n"
            )
            elapsed = time.time() - start
            if elapsed < frame_interval:
                time.sleep(frame_interval - elapsed)

    return StreamingResponse(
        generate(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-cache, no-store"},
    )


@app.get("/snapshot")
def snapshot(cam: int = Query(0), save: bool = Query(False),
             x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    verify_key(x_api_key, key)
    jpeg = get_camera(cam).snapshot()
    if jpeg is None:
        raise HTTPException(status_code=503, detail="Camera not ready yet")
    if save:
        path = save_jpeg_still("capture", cam, jpeg)
        if path:
            print(f"[guard] CAPTURE on cam {cam} -> saved {path}")
    return Response(content=jpeg, media_type="image/jpeg",
                    headers={"Cache-Control": "no-cache, no-store"})


@app.get("/events")
def list_events(x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    verify_key(x_api_key, key)
    files = sorted(home_link_event_files(), key=lambda p: p.stat().st_mtime, reverse=True)
    if EVENT_LIST_LIMIT > 0:
        files = files[:EVENT_LIST_LIMIT]
    events: List[dict] = []
    for f in files:
        parsed = parse_event_name(f.name)
        if not parsed:
            continue
        try:
            when = datetime.strptime(str(parsed["stamp"]), "%Y%m%d_%H%M%S").isoformat()
        except ValueError:
            when = str(parsed["stamp"])
        events.append({
            "name": f.name,
            "time": when,
            "cam": parsed["cam"],
            "type": parsed["kind"],
            "node": parsed["node"],
        })
    return {"events": events}


@app.get("/events/{name}")
def get_event(name: str, x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    verify_key(x_api_key, key)
    if not parse_event_name(name):
        raise HTTPException(status_code=400, detail="Invalid event name")
    path = EVENTS_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Event not found")
    return FileResponse(path, media_type="image/jpeg")


def _discover_candidate_ips() -> List[str]:
    """IPv4 addresses worth probing for other guard nodes.
    Includes Tailscale peers for remote reachability and local LAN
    neighbors/subnets for same-Wi-Fi guard machines."""
    ips: set = set()
    for ts in (r"C:\Program Files\Tailscale\tailscale.exe", "tailscale"):
        try:
            out = subprocess.run([ts, "status", "--json"], capture_output=True, timeout=6, text=True)
            if out.returncode != 0:
                continue
            data = jsonlib.loads(out.stdout)
            for peer in (data.get("Peer") or {}).values():
                for ip in peer.get("TailscaleIPs") or []:
                    if "." in ip:
                        ips.add(ip)
            for ip in (data.get("Self") or {}).get("TailscaleIPs") or []:
                if "." in ip:
                    ips.add(ip)
            break
        except (OSError, subprocess.SubprocessError, ValueError):
            continue

    local_ips = set()

    # Probe recent LAN neighbors.
    try:
        out = subprocess.run(["arp", "-a"], capture_output=True, timeout=5, text=True)
        for m in re.finditer(r"(\d{1,3}(?:\.\d{1,3}){3})", out.stdout):
            ip = m.group(1)
            if not ip.startswith(("224.", "239.", "255.")) and not ip.endswith(".255"):
                ips.add(ip)
    except (OSError, subprocess.SubprocessError):
        pass

    try:
        local_ips.update(socket.gethostbyname_ex(socket.gethostname())[2])
    except OSError:
        pass

    for ip in local_ips:
        ips.add(ip)
        try:
            addr = ipaddress.ip_address(ip)
        except ValueError:
            continue
        if not isinstance(addr, ipaddress.IPv4Address) or not addr.is_private:
            continue
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
        for host in network.hosts():
            ips.add(str(host))

    return sorted(ips)


def _probe_guard(ip: str, timeout: float = 0.7) -> Optional[dict]:
    try:
        req = urllib.request.Request(
            f"http://{ip}:{PORT}/", headers={"X-API-Key": API_KEY}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = jsonlib.loads(resp.read().decode())
        if data.get("service") != "house-guard":
            return None
        cams = data.get("cameras")
        if cams is None:  # legacy single-camera server
            cams = [{"camera_ok": data.get("camera_ok", False)}]
        return {
            "url": f"http://{ip}:{PORT}",
            "node_id": data.get("node_id") or data.get("hostname") or ip,
            "cameras": sum(1 for c in cams if c.get("camera_ok")),
        }
    except (OSError, ValueError):
        return None


def _node_url_score(url: str) -> int:
    host = url.split("//", 1)[-1].split(":", 1)[0]
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return 20
    if isinstance(ip, ipaddress.IPv4Address) and ip in ipaddress.ip_network("100.64.0.0/10"):
        return 0       # Tailscale works away from home, so prefer it.
    if ip.is_private:
        return 10
    return 20


def _probe_onvif_cameras(timeout: float = 2.5) -> List[dict]:
    """WS-Discovery multicast probe - finds standalone ONVIF IP cameras
    (most wired/wifi security cams) on the local network."""
    probe = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<e:Envelope xmlns:e="http://www.w3.org/2003/05/soap-envelope"'
        ' xmlns:w="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
        ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
        ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
        f'<e:Header><w:MessageID>uuid:{uuidlib.uuid4()}</w:MessageID>'
        '<w:To e:mustUnderstand="true">urn:schemas-xmlsoap-org:ws:2005:04:discovery</w:To>'
        '<w:Action e:mustUnderstand="true">http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</w:Action>'
        '</e:Header><e:Body><d:Probe><d:Types>dn:NetworkVideoTransmitter</d:Types></d:Probe></e:Body>'
        '</e:Envelope>'
    ).encode()

    found: Dict[str, dict] = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        sock.settimeout(timeout)
        sock.sendto(probe, ("239.255.255.250", 3702))
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(65535)
            except socket.timeout:
                break
            xaddrs = re.findall(r"https?://[^\s<>\"]+", data.decode(errors="ignore"))
            found[addr[0]] = {
                "ip": addr[0],
                "xaddr": xaddrs[0] if xaddrs else None,
            }
        sock.close()
    except OSError as e:
        print(f"[guard] ONVIF probe failed: {e}")
    return list(found.values())


@app.get("/discover")
def discover(x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    """Scan the network: other guard nodes + standalone ONVIF IP cameras."""
    verify_key(x_api_key, key)
    candidates = _discover_candidate_ips()
    # 512-host subnet sweeps must finish well inside the app's fetch timeout;
    # probes are cheap sockets, so go wide.
    with ThreadPoolExecutor(max_workers=64) as pool:
        onvif_future = pool.submit(_probe_onvif_cameras)
        found = [r for r in pool.map(_probe_guard, candidates) if r]
        ip_cameras = onvif_future.result()
    unique_nodes: Dict[str, dict] = {}
    for node in found:
        key = node.get("node_id") or node["url"]
        current = unique_nodes.get(key)
        if current is None or _node_url_score(node["url"]) < _node_url_score(current["url"]):
            unique_nodes[key] = node
    found = list(unique_nodes.values())
    tailscale_counts = {
        node["cameras"]
        for node in found
        if _node_url_score(node["url"]) == 0
    }
    found = [
        node for node in found
        if _node_url_score(node["url"]) == 0
        or node.get("node_id") != node["url"].split("//", 1)[-1].split(":", 1)[0]
        or node["cameras"] not in tailscale_counts
    ]
    found.sort(key=lambda n: n["url"])
    return {"nodes": found, "ip_cameras": ip_cameras, "probed": len(candidates)}


@app.post("/arm")
async def arm(request: Request, x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    verify_key(x_api_key, key)
    body = await request.json()
    armed_flag.armed = bool(body.get("armed", True))
    print(f"[guard] Motion detection {'ARMED' if armed_flag.armed else 'DISARMED'}")
    return {"armed": armed_flag.armed}


rescan_lock = threading.Lock()


def rescan_cameras() -> dict:
    """Re-enumerate the USB cameras while the server keeps running.

    /wake reopens the SAME device index, which is useless when the webcams
    have been moved to different USB ports: Windows hands out new indexes,
    so index 0 may now be a camera that no longer exists (solid black) while
    the real camera sits on an index nobody is watching. This tears every USB
    capture down, probes the bus again, and rebuilds the camera set from what
    is actually plugged in right now.

    guard_cameras.json is re-read too, so network and screen sources can be
    added or removed without restarting the guard.
    """
    with rescan_lock:
        before = sorted(i for i in cameras if cameras[i].is_usb)
        # An open camera cannot be probed, so release them all FIRST -
        # otherwise detection reports every working camera as missing.
        for i in before:
            cameras.pop(i).stop()
        time.sleep(1.5)                     # let Windows release the handles

        found = detect_camera_indexes()
        if not found:
            # Don't leave the node camera-less on a transient probe failure:
            # fall back to what was there before (or index 0 on a cold start).
            found = before or [0]
            print("[guard] Rescan found no cameras - keeping the previous set.")

        usb_names = _video_device_names()
        for i in found:
            cam = GuardCamera(i, i, armed_flag,
                              name=usb_names[i] if i < len(usb_names) else None)
            cameras[i] = cam
            cam.start()

        # Re-read guard_cameras.json so network/screen sources can be added or
        # removed live. Ids 10+ are rebuilt from the file, same as at boot.
        extras = load_extra_sources()
        for i in [i for i in cameras if not cameras[i].is_usb]:
            cameras.pop(i).stop()
        for n, extra in enumerate(extras):
            cam_id = 10 + n
            cam = GuardCamera(cam_id, extra["url"], armed_flag, name=extra["name"])
            cameras[cam_id] = cam
            cam.start()

        added = [i for i in found if i not in before]
        removed = [i for i in before if i not in found]
        print(f"[guard] Rescan: cameras {before} -> {found} "
              f"(added {added}, removed {removed}); {len(extras)} extra source(s)")
        result = {
            "cameras": sorted(cameras),
            "usb": found,
            "extras": [e["url"] for e in extras],
            "added": added,
            "removed": removed,
            "devices": usb_names,
        }

    # Mics are enumerated in the same order as the cameras, so a USB reshuffle
    # invalidates the camera -> microphone mapping too. Done outside the lock:
    # audio enumeration is the part most likely to stall, and it must never
    # block the next rescan.
    global audio_map
    if _sd is not None:
        audio_map = _match_audio_devices()
    return result


@app.post("/rescan")
def rescan(x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    """Rebuild the camera list from the hardware that is plugged in NOW.
    Use after moving webcams between USB ports or plugging in a new one.

    Probing every index takes longer than the app's request timeout, so the
    work runs in the background and the client just re-reads /status a few
    seconds later to see the new camera set."""
    verify_key(x_api_key, key)
    if rescan_lock.locked():
        return {"rescanning": True, "cameras": sorted(cameras), "already_running": True}
    threading.Thread(target=rescan_cameras, daemon=True).start()
    return {"rescanning": True, "cameras": sorted(cameras), "already_running": False}


@app.post("/wake")
def wake(cam: Optional[int] = Query(None), x_api_key: Optional[str] = Header(None), key: Optional[str] = Query(None)):
    """Force one camera (?cam=N) or ALL cameras to release and reopen their
    device. Recovers a webcam stuck streaming black/frozen frames."""
    verify_key(x_api_key, key)
    if cam is not None:
        get_camera(cam).request_reopen()
        woken = [cam]
    else:
        for c in cameras.values():
            c.request_reopen()
        woken = sorted(cameras)
    print(f"[guard] Wake requested for cameras: {woken}")
    return {"woken": woken}


@app.options("/{rest_of_path:path}")
async def options_handler(request: Request):
    return JSONResponse(content={"ok": True})


if __name__ == "__main__":
    print("\n" + "=" * 46)
    print("  HOUSE GUARD CAMERA SERVER")
    print("=" * 46)
    print(f"1. In HomeLink Settings, set Camera URL to")
    print(f"   http://<this-laptop's-Tailscale-IP>:{PORT}")
    print(f"2. Shared Secret is the same: {API_KEY}")
    print(f"3. Still images are saved in: {EVENTS_DIR}")
    print(f"4. Cameras are auto-detected (up to {MAX_CAMERAS}).")
    print("=" * 46 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=PORT)
