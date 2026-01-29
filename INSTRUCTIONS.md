
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

## Alternative: SSH Tunnel (If Tailscale fails)
If you can't bypass the browser security, run this in Command Prompt:
```cmd
ssh -R 80:localhost:8000 nokey@localhost.run
```
Copy the `https://...` link it gives you and use that in settings instead.
