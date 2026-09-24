
# HomeLink LLM Setup Guide

## Step 1: LM Studio
1. Open LM Studio on PC.
2. Go to **Local Server** (↔️).
3. Set Port to `1234` and **Start Server**.

## Step 2: Proxy (main.py)
1. Run: `python backend/main.py` (Proxy starts on Port 8000).

## Step 3: Connect via Tailscale (BEST)
1. Open Tailscale on your PC and copy your PC's IP (e.g., `100.107.136.88`).
2. Open HomeLink App -> Settings (Cog icon).
3. Set Server URL to: `http://YOUR-IP:8000`.
4. **IMPORTANT: Bypass Browser Security**
   - Click the **Lock icon** in your phone's browser bar.
   - Go to **Site Settings**.
   - Find **Insecure content** and set to **Allow**.
   - Refresh the page.

---

# House Guard Camera Setup

Turn any laptop/PC webcam into a security camera you can watch from anywhere.

## Step 1: One-time setup on each guard laptop
1. Install **Python** from python.org (check **"Add python.exe to PATH"** during install).
2. Install **Tailscale** and sign in with the **same account** as your PC and phone.
3. Copy the `backend` folder to the guard laptop (USB stick, or network share).
4. Point the laptop at what you want to guard (front door, living room, etc.).

## Step 2: Keep the laptop awake
Since the lid may be closed / screen broken, stop Windows from sleeping. In Command Prompt **(Run as Administrator)**:
```cmd
powercfg /change standby-timeout-ac 0
powercfg /change monitor-timeout-ac 10
powercfg /setacvalueindex SCHEME_CURRENT SUB_BUTTONS LIDACTION 0
powercfg /setactive SCHEME_CURRENT
```
(The last two lines make "close the lid" do nothing while plugged in.)

## Step 3: Start the guard
1. Double-click `start_guard.bat` in the backend folder (installs dependencies the first time, then starts the camera server on port **7171**).
2. Leave that window open. The webcam light should come on.

## Step 4: Connect the app
1. On RedKryptonite, open Tailscale and copy the laptop's IP (looks like `100.x.x.x`).
2. In the HomeLink app, open **Settings** -> **House Guard Camera** and enter `http://THAT-IP:7171`.
3. Tap the red camera test button — it should say "Camera online!"
4. Tap the **Guard** tab at the top of the app to watch live.
5. Same browser note as chat: if the video won't load, allow **Insecure content** for that IP in your phone browser's site settings.

## Updating an existing guard laptop
From the guard laptop, run this in PowerShell:
```powershell
irm http://100.107.136.88:8080/guard-update/update_guard.ps1 | iex
```
This installs the latest multi-camera/audio guard and restarts the camera server.

## What Guard mode does
- **Live view**: real-time stream from the webcam, from anywhere (via Tailscale).
- **Live audio**: tap a live feed to focus it; if that camera has a mapped microphone, audio starts for that feed only.
- **Armed/Disarmed**: when armed, motion is detected automatically and a snapshot is saved to `X:\Camera Roll` (max one every 12 seconds per camera).
- **Motion Events**: grid of the newest 200 HomeLink stills with timestamps — tap one to view full screen.
- **Snapshot**: grab a full-quality frame right now and save it to `X:\Camera Roll`.

## Adding cameras

- **USB webcams**: plug in -> restart that machine's guard (or reboot). No drivers needed — Windows handles UVC webcams automatically.
- **Another PC/laptop**: run the guard setup on it, then tap **SCAN NETWORK FOR CAMERAS** in the app's Settings.
- **Standalone IP cameras (RTSP/ONVIF)**: the SCAN button detects them on the network. To add one, create `guard_cameras.json` next to `camera_server.py` on any guard machine:
  ```json
  {"extra_sources": [{"url": "rtsp://user:password@192.168.1.50:554/stream1", "name": "front door"}]}
  ```
  then restart that guard. The RTSP URL and password come from the camera's app/manual. Note: cloud-locked cameras (Ring, Nest) don't expose RTSP and can't be added.

## Auto-start on boot (optional)
1. Press `Win+R` on RedKryptonite, type `shell:startup`, press Enter.
2. Copy a shortcut to `start_guard.bat` into that folder.
Now the guard starts whenever the laptop powers on.

---

## Alternative: SSH Tunnel (If Tailscale fails)
If you can't bypass the browser security, run this in Command Prompt:
```cmd
ssh -R 80:localhost:8000 nokey@localhost.run
```
Copy the `https://...` link it gives you and use that in settings instead.
