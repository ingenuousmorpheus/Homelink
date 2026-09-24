r"""
╔══════════════════════════════════════════════════════════════╗
║   LANA  ·  REMOTE ARM (Agent)                                ║
║   Lana's computer-control engine for ANOTHER PC (no LLM).     ║
║   Deploy on LENOVOMONITOR (or any Windows PC) so Lana can     ║
║   see and drive it remotely — same powers she has locally.    ║
╚══════════════════════════════════════════════════════════════╝

Run on the target PC:
    pip install flask flask-cors pyautogui mss opencv-python
    set LANA_AGENT_TOKEN=<the-shared-secret>          (recommended)
    python lana_agent.py                              (listens on :7060)

Then on the BRAIN PC, register it in C:\LANA\lana_hosts.json:
    { "lenovomonitor": { "url": "http://192.168.1.145:7060", "token": "<same-secret>" } }

Security: /exec runs shell commands + drives the mouse/keyboard, so set a token —
every request must send header  X-Lana-Token: <token>  (skipped only if no token set).
Optional deps (mss/cv2, uiautomation, rapidocr) degrade gracefully if missing.
"""

import os, sys, json, time, base64, subprocess, platform, threading, tempfile, hmac, ipaddress
try:  # never crash on a cp1252 console (this runs on other PCs too)
    sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass
from io import BytesIO
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import Flask, request, jsonify, Response
try:
    from flask_cors import CORS
except Exception:
    CORS = None

PORT  = int(os.getenv("LANA_AGENT_PORT", "7060"))
HOST  = "0.0.0.0"
TOKEN = os.getenv("LANA_AGENT_TOKEN") or (
    Path(r"C:\LANA\lana_agent_token.txt").read_text().strip()
    if Path(r"C:\LANA\lana_agent_token.txt").exists() else "")
ALLOW_SHELL = os.getenv("LANA_AGENT_ALLOW_SHELL", "0").strip().lower() in ("1", "true", "yes", "on")

app = Flask(__name__)
if CORS:
    _cors_env = os.getenv("LANA_AGENT_CORS_ORIGINS", "")
    if _cors_env.strip():
        _origins = "*" if _cors_env.strip() == "*" else [o.strip() for o in _cors_env.split(",") if o.strip()]
        CORS(app, resources={r"/*": {"origins": _origins}})

# ── Lana's Aura: red screen-edge glow on THIS pc while she controls it ──
OVERLAY_STATE = os.getenv("LANA_OVERLAY_STATE") or str(Path(__file__).with_name("overlay_state.json"))
_CTRL_VERBS = {"click","double_click","right_click","move_mouse","scroll","type_text","press_key",
               "open_app","open_browser","click_text","click_screen_text"}
def _aura_on(secs=4.0):
    try: Path(OVERLAY_STATE).write_text(json.dumps({"until": time.time()+secs, "color": "#ff0026"}))
    except Exception: pass
def _launch_overlay():
    try:
        ov = Path(__file__).with_name("lana_overlay.py")
        if not ov.exists():
            print("[agent] lana_overlay.py not found — aura disabled (re-run the bootstrap to add it)"); return
        # Launch with THIS interpreter (sys.executable) — deriving pythonw fails on Store-alias Pythons.
        subprocess.Popen([sys.executable, str(ov)],
                         env=dict(os.environ, LANA_OVERLAY_STATE=OVERLAY_STATE),
                         creationflags=0x08000000)   # CREATE_NO_WINDOW (hides any console)
        print("[agent] Lana's Aura overlay launched")
    except Exception as e:
        print(f"[agent] overlay launch failed: {e}")

# ── auth ──────────────────────────────────────────────────────────────────────
def require_token(fn):
    @wraps(fn)
    def _w(*a, **k):
        remote = (request.remote_addr or "").split("%", 1)[0]
        if remote.startswith("::ffff:"):
            remote = remote.rsplit(":", 1)[-1]
        try:
            loopback = ipaddress.ip_address(remote).is_loopback
        except ValueError:
            loopback = remote in ("localhost", "")
        if not TOKEN and not loopback:
            return jsonify({"error": "remote_control_locked", "message": "Set LANA_AGENT_TOKEN before exposing the remote arm."}), 403
        if TOKEN and not hmac.compare_digest(request.headers.get("X-Lana-Token", ""), TOKEN):
            return jsonify({"error": "unauthorized"}), 401
        return fn(*a, **k)
    return _w

# ── screen capture (mss+cv2 fast path, pyautogui fallback) ────────────────────
_MSS = None
def grab_jpeg(width=1280, quality=60) -> bytes:
    try:
        global _MSS
        if _MSS is None:
            import mss as _m; _MSS = getattr(_m, "MSS", None) or _m.mss
        import numpy as np, cv2
        with _MSS() as sct:
            arr = np.asarray(sct.grab(sct.monitors[1]))[:, :, :3]
        h, w = arr.shape[:2]
        if width and w > width:
            arr = cv2.resize(arr, (int(width), int(h * width / w)), interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".jpg", arr, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        if ok: return buf.tobytes()
    except Exception:
        pass
    import pyautogui
    img = pyautogui.screenshot(); w, h = img.size
    if width and w > width: img = img.resize((int(width), int(h * width / w)))
    b = BytesIO(); img.convert("RGB").save(b, format="JPEG", quality=int(quality)); return b.getvalue()

# ── webcam capture ──────────────────────────────────────────────────────────────
def capture_camera(index=0, width=1024, quality=72):
    try:
        import cv2
        cap = cv2.VideoCapture(index, cv2.CAP_DSHOW)
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1); time.sleep(0.35)
        ok, frame = cap.read()
        if not ok or frame is None:
            cap.release(); cap = cv2.VideoCapture(index); time.sleep(0.35); ok, frame = cap.read()
        cap.release()
        if not ok or frame is None:
            return None
        h, w = frame.shape[:2]
        if width and w > width:
            frame = cv2.resize(frame, (int(width), int(h * width / w)))
        ok2, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, int(quality)])
        return buf.tobytes() if ok2 else None
    except Exception:
        return None

# ── speech (play a provided WAV, else Windows SAPI) ──────────────────────────────
def _sapi_say(text):
    try:
        fd, tp = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write((text or "")[:1200])
        ps = ("Add-Type -AssemblyName System.Speech;"
              "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
              "try{$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::Female)}catch{};"
              f"$t=[IO.File]::ReadAllText('{tp}',[Text.Encoding]::UTF8);$s.Speak($t)")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                       timeout=60, capture_output=True, creationflags=0x08000000)
        try: os.unlink(tp)
        except Exception: pass
    except Exception:
        pass

def _wav_b64(frames_int16, rate=16000):
    import io, wave
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        w.writeframes(frames_int16)
    return base64.b64encode(buf.getvalue()).decode()

# Pick the capture device by NAME, not a fragile PortAudio index (indices renumber when
# the Waves SoundGrid devices come/go). Prefer the physical HD-Audio mic, which is the live
# input on this rig; the Waves line-in reads dead (nothing plugged in). Override via env.
_MIC_NAME_PREFS = ("high definition audio", "hd audio microphone", "microphone")
_MIC_NAME_AVOID = ("waves", "soundgrid", "sg wave", "line in")

def _resolve_mic_device():
    env = os.getenv("LANA_MIC_DEVICE")
    if env not in (None, ""):
        try: return int(env)
        except Exception: pass
    try:
        import sounddevice as sd
        ins = [(i, d) for i, d in enumerate(sd.query_devices())
               if d.get("max_input_channels", 0) > 0]
        for pref in _MIC_NAME_PREFS:
            for i, d in ins:
                nm = d["name"].lower()
                if pref in nm and not any(a in nm for a in _MIC_NAME_AVOID):
                    return i
    except Exception:
        pass
    return None   # fall back to system default

def _record_mic(maxsecs=8, rate=16000, silence=0.8, thresh=280):
    """VAD capture: wait for speech, record until ~`silence`s of quiet, return base64 WAV.
    Returns '' if no speech within maxsecs (so the brain skips). Feels responsive vs a fixed window."""
    # echo gate: if Lana is speaking through this PC's speakers, don't capture (she'd hear herself).
    if _speaking_now():
        time.sleep(min(maxsecs, max(0.0, _SPEAKING_UNTIL - time.time())))
        return ""
    dev = _resolve_mic_device()
    try:
        import sounddevice as sd, numpy as np, queue
        # NB: use the CALLBACK path, not blocking stream.read(). Blocking reads return pure
        # silence (peak 0) on this rig's DirectSound capture devices, while the callback path
        # (the same mechanism sd.rec uses) captures correctly. This was the intercom's deafness.
        q = queue.Queue()
        def _cb(indata, frames_, t_, status):
            q.put(bytes(indata))
        frames = []; started = False; silent = 0.0; elapsed = 0.0; peak = 0
        step = 0.1; n = int(rate * step)
        with sd.InputStream(samplerate=rate, channels=1, dtype="int16",
                            device=dev, blocksize=n, callback=_cb):
            while elapsed < maxsecs:
                try:
                    data = q.get(timeout=1.0)
                except Exception:
                    break
                frames.append(data); elapsed += step
                samples = np.frombuffer(data, dtype="int16")
                energy = float(np.abs(samples).mean())
                if samples.size: peak = max(peak, int(np.abs(samples).max()))
                if energy > thresh:
                    started = True; silent = 0.0
                elif started:
                    silent += step
                    if silent >= silence:
                        break
                elif len(frames) > 4:
                    frames = frames[-4:]          # keep a little pre-roll, drop leading silence
        print(f"[Mic] device={dev} peak={peak} started={started}", flush=True)
        if not started:
            return ""
        return _wav_b64(b"".join(frames), rate)
    except Exception as e:
        print(f"[Mic] stream error on device={dev}: {e}", flush=True)
        # fallback: fixed 5s grab via sd.rec (callback-based, proven to work here)
        try:
            import sounddevice as sd
            rec = sd.rec(int(5 * rate), samplerate=rate, channels=1, dtype="int16", device=dev); sd.wait()
            return _wav_b64(rec.tobytes(), rate)
        except Exception:
            return ""

# ── echo gate: while Lana is talking through THIS pc's speakers, the mic must not listen,
# or it captures her own voice and she answers herself in a loop. _speak holds the gate open
# for the whole playback + a short tail; _record_mic refuses to capture while it's held.
_SPEAKING_UNTIL = 0.0
_SPEAK_TAIL = 0.7   # extra quiet seconds after playback for the speaker echo to die down

def _speaking_now():
    return time.time() < _SPEAKING_UNTIL

def _speak(text, audio_b64=None):
    global _SPEAKING_UNTIL
    # estimate a generous upper bound so the gate stays shut even if playback runs long
    est = max(2.0, min(30.0, len(text or "") / 11.0 + 1.5))
    _SPEAKING_UNTIL = time.time() + est + _SPEAK_TAIL
    try:
        if audio_b64:
            try:
                import winsound
                data = base64.b64decode(audio_b64)
                fd, path = tempfile.mkstemp(suffix=".wav"); os.write(fd, data); os.close(fd)
                try:
                    winsound.PlaySound(path, winsound.SND_FILENAME)   # blocking, in this daemon thread
                    return
                finally:
                    try: os.unlink(path)
                    except Exception: pass
            except Exception:
                pass
        _sapi_say(text)
    finally:
        # playback finished (or failed) — close the gate after a short echo tail
        _SPEAKING_UNTIL = time.time() + _SPEAK_TAIL

# ── OCR (optional) ─────────────────────────────────────────────────────────────
_OCR = None
def _ocr():
    global _OCR
    if _OCR is None:
        from rapidocr_onnxruntime import RapidOCR; _OCR = RapidOCR()
    return _OCR

def ocr_screen(scale=0.6):
    try:
        import pyautogui, numpy as np
        shot = pyautogui.screenshot()
        if scale != 1.0:
            shot = shot.resize((int(shot.width*scale), int(shot.height*scale)))
        res, _ = _ocr()(np.array(shot)); inv = 1.0/scale; out = []
        for box, text, score in (res or []):
            xs=[p[0] for p in box]; ys=[p[1] for p in box]
            out.append((text.strip(), int(sum(xs)/4*inv), int(sum(ys)/4*inv), float(score)))
        return out
    except Exception as e:
        return [("(ocr unavailable: %s)" % e, 0, 0, 0.0)]

# ── the action engine (mirrors the brain's local verbs) ───────────────────────
APP_MAP = {"chrome":"chrome","firefox":"firefox","notepad":"notepad","explorer":"explorer",
           "edge":"msedge","discord":"discord","spotify":"spotify","vscode":"code","obs":"obs64",
           "cmd":"cmd","powershell":"powershell","calc":"calc","task":"taskmgr"}

def do_action(action: str, p: dict) -> str:
    if action in _CTRL_VERBS:
        _aura_on()                 # red glow on this PC while she acts
    try:
        if action == "scan_network":
            sys.path.insert(0, str(Path(__file__).parent))
            import lana_netscan
            devices, summary = lana_netscan.scan()
            return json.dumps({"summary": summary, "count": len(devices), "devices": devices})
        if action == "say":
            threading.Thread(target=_speak, args=(p.get("text", ""), p.get("audio")), daemon=True).start()
            return "speaking through this PC's speakers"
        if action == "camera":
            jpg = capture_camera(int(p.get("index", 0)), int(p.get("width", 1024)))
            return base64.b64encode(jpg).decode() if jpg else "camera unavailable"
        if action == "listen":
            return _record_mic(float(p.get("maxsecs", p.get("secs", 8)))) or "no-audio"
        if action == "screenshot":
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = Path(rf"C:\LANA\agent_shots\shot_{ts}.png"); path.parent.mkdir(parents=True, exist_ok=True)
            import pyautogui; pyautogui.screenshot(str(path)); return f"Screenshot saved → {path}"
        if action in ("click","double_click","right_click"):
            import pyautogui
            x=int(float(p.get("x",0))); y=int(float(p.get("y",0)))
            fn={"click":pyautogui.click,"double_click":pyautogui.doubleClick,"right_click":pyautogui.rightClick}[action]
            fn(x,y) if (x or y) else fn(); return f"{action} at ({x},{y})"
        if action == "move_mouse":
            import pyautogui; pyautogui.moveTo(int(float(p.get("x",0))),int(float(p.get("y",0))),duration=0.15); return "moved"
        if action == "scroll":
            import pyautogui
            if p.get("x") and p.get("y"): pyautogui.moveTo(int(float(p["x"])),int(float(p["y"])))
            pyautogui.scroll(int(float(p.get("amount",-400)))); return "scrolled"
        if action == "type_text":
            import pyautogui; t=p.get("text","")[:1000]
            if any(ord(c)>127 for c in t):
                try:
                    import pyperclip; pyperclip.copy(t); pyautogui.hotkey("ctrl","v")
                except Exception: pyautogui.typewrite(t, interval=0.02)
            else: pyautogui.write(t, interval=0.03)
            return f"typed: {t[:40]}"
        if action == "press_key":
            import pyautogui; pyautogui.hotkey(*p.get("key","enter").split("+")); return f"pressed {p.get('key')}"
        if action == "open_app":
            name=p.get("name",""); subprocess.Popen(APP_MAP.get(name.lower(),name), shell=True); return f"launched {name}"
        if action == "open_browser":
            url=p.get("url","https://google.com")
            if not url.startswith("http"): url="https://"+url
            subprocess.Popen(["start", url], shell=True); return f"opened {url}"
        if action == "run_command":
            if not ALLOW_SHELL:
                return "remote shell is locked; set LANA_AGENT_ALLOW_SHELL=1 on this room node to enable it"
            r=subprocess.run(p.get("cmd",""), shell=True, capture_output=True, text=True, timeout=int(p.get("timeout",20)))
            return (r.stdout or r.stderr or "(no output)")[:1200]
        if action == "find_text":
            words=[f"'{w}' @({x},{y})" for (w,x,y,s) in ocr_screen() if w and s>=0.4][:50]
            return "Text on screen:\n"+"\n".join(words) if words else "no text detected"
        if action in ("click_text","click_screen_text"):
            import pyautogui; tgt=p.get("text","").strip().lower()
            cand=[it for it in ocr_screen() if it[0] and it[3]>=0.4 and (it[0].lower()==tgt or tgt in it[0].lower())]
            if not cand: return f"couldn't find '{tgt}' on screen"
            cand.sort(key=lambda it:it[3], reverse=True); w,x,y,s=cand[0]; pyautogui.click(x,y); return f"clicked '{w}' @({x},{y})"
        if action == "read_ui":
            try:
                import uiautomation as auto
                fg=auto.GetForegroundControl(); top=fg.GetTopLevelControl() if fg else None
                items=[];
                if top:
                    for ctrl,_d in auto.WalkControl(top, includeTop=False, maxDepth=12):
                        if ctrl.ControlTypeName in ('ButtonControl','HyperlinkControl','MenuItemControl','ListItemControl','TabItemControl','CheckBoxControl','EditControl'):
                            nm=(ctrl.Name or '').strip()
                            if nm:
                                r=ctrl.BoundingRectangle
                                if r.width()>0: items.append(f"{nm} @({(r.left+r.right)//2},{(r.top+r.bottom)//2})")
                        if len(items)>=40: break
                return "Clickable:\n"+"\n".join(items) if items else "no UI tree (game/custom surface — use find_text)"
            except Exception as e:
                return f"read_ui unavailable: {e}"
        if action == "wait":
            time.sleep(max(0.0, min(10.0, float(p.get("seconds",1))))); return "waited"
        return f"unknown action: {action}"
    except ImportError as e:
        return f"missing dependency for {action}: {e}"
    except Exception as e:
        return f"{action} failed: {e}"

# ── routes ─────────────────────────────────────────────────────────────────────
@app.route("/status")
@require_token
def status():
    try:
        import pyautogui; w,h = pyautogui.size()
    except Exception: w,h = 0,0
    return jsonify({"agent":"lana", "host":platform.node(), "os":platform.platform(),
                    "screen":[int(w),int(h)], "token_required":bool(TOKEN),
                    "shell_enabled": ALLOW_SHELL})

@app.route("/exec", methods=["POST"])
@require_token
def exec_route():
    d=request.json or {}; action=d.get("action",""); params=d.get("params",{}) or {}
    if not action: return jsonify({"error":"no action"}),400
    return jsonify({"result": do_action(action, params)})

@app.route("/screenshot")
@require_token
def screenshot_route():
    return Response(grab_jpeg(int(request.args.get("width",1280)), int(request.args.get("quality",60))),
                    mimetype="image/jpeg", headers={"Cache-Control":"no-cache"})

@app.route("/camera")
@require_token
def camera_route():
    jpg = capture_camera(int(request.args.get("index", 0)), int(request.args.get("width", 1024)))
    if not jpg:
        return jsonify({"error": "camera unavailable"}), 503
    return Response(jpg, mimetype="image/jpeg", headers={"Cache-Control": "no-cache"})

@app.route("/screen/live.mjpg")
@require_token
def live_route():
    fps=max(1,min(15,int(request.args.get("fps",6)))); width=int(request.args.get("width",1280)); q=int(request.args.get("quality",55))
    def gen():
        while True:
            t0=time.time()
            try: jpg=grab_jpeg(width,q)
            except Exception: time.sleep(0.4); continue
            yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: "+str(len(jpg)).encode()+b"\r\n\r\n"+jpg+b"\r\n")
            dt=1.0/fps-(time.time()-t0)
            if dt>0: time.sleep(dt)
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame", headers={"Cache-Control":"no-cache"})

if __name__ == "__main__":
    # ── single instance: a second copy exits immediately (prevents stacking on :7060) ──
    try:
        import ctypes
        _mtx = ctypes.windll.kernel32.CreateMutexW(None, False, "Local\\LanaRemoteArm")
        if ctypes.windll.kernel32.GetLastError() == 183:   # ERROR_ALREADY_EXISTS
            print("[LANA REMOTE ARM] already running — exiting this copy")
            raise SystemExit(0)
    except SystemExit:
        raise
    except Exception:
        pass
    print(f"[LANA REMOTE ARM] host={platform.node()} port={PORT} token={'set' if TOKEN else 'OPEN (no token!)'}")
    _launch_overlay()              # Lana's Aura (red glow when she drives this PC)
    app.run(host=HOST, port=PORT, threaded=True)
