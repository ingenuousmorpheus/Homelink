# HOMELINK MOBILE APP → LANA CONNECTION GUIDE

## Current Problem

Your Homelink mobile app can't talk to LANA because the backend server isn't connecting to LM Studio properly. Here's how to fix it.

## Architecture Overview

```
[Homelink Mobile App]
        ↓ WiFi
[Your PC: LANA Server on port 6969]
        ↓
[LM Studio on port 1234]
        ↓
[AI Model: kimi-vl-a3b-thinking-2506]
```

## The Issue

Your repository shows a React/TypeScript mobile app with a Python backend. The backend needs to connect to LM Studio, but it's probably configured incorrectly.

Common issues:
1. **Wrong IP address** - Using `localhost` instead of your PC's actual IP
2. **Wrong model name** - Hardcoded model doesn't match what's loaded
3. **LM Studio not running** - Server not started
4. **Firewall blocking** - Windows blocking port 6969 or 1234
5. **Different networks** - Phone and PC on different WiFi

## Quick Fix Steps

### Step 1: Find Your PC's IP Address

**Windows:**
```cmd
ipconfig
```
Look for "IPv4 Address" under your WiFi adapter (e.g., `192.168.1.109`)

**Keep this number handy - you'll need it!**

### Step 2: Set Up Configuration

Copy these files to your Homelink backend directory:
- `lana_config.json`
- `lm_studio_client.py`
- `lana_server_fixed.py`
- `vision_router_fixed.py`

Edit `lana_config.json`:
```json
{
  "lm_studio": {
    "base_url": "http://YOUR_PC_IP:1234"  ← Change this!
  },
  "models": {
    "primary": "kimi-vl-a3b-thinking-2506"  ← Your model name
  },
  "server": {
    "host": "0.0.0.0",  ← Important: 0.0.0.0 allows mobile connections
    "port": 6969
  }
}
```

### Step 3: Start LM Studio

1. Open LM Studio
2. Go to "Local Server" tab
3. Load your model: `kimi-vl-a3b-thinking-2506`
4. Click "Start Server"
5. Verify it shows something like: `Server running at http://192.168.1.109:1234`

### Step 4: Test Your Setup

Run the diagnostic:
```bash
cd /path/to/your/homelink/backend
python homelink_connection_test.py
```

This will tell you:
- ✅ What's working
- ❌ What's broken
- 💡 How to fix it

### Step 5: Start LANA Server

```bash
python lana_server_fixed.py
```

You should see:
```
🖤 LANA OS-Link Server Starting...
✅ LM Studio connection established
✅ Primary model loaded: kimi-vl-a3b-thinking-2506
🌐 Starting server on 0.0.0.0:6969
🚀 LANA OS-Link Ready
```

### Step 6: Configure Homelink App

In your Homelink mobile app settings:

**Server URL:** `http://YOUR_PC_IP:6969`

Example: `http://192.168.1.109:6969`

**Important:** 
- Use your PC's IP, NOT `localhost`
- Make sure phone and PC are on the SAME WiFi network
- No trailing slash in the URL

### Step 7: Test Connection

From your Homelink app:
1. Send a test message: "Hello LANA"
2. You should get a response back
3. Check the LANA server terminal - you should see the message logged

## Troubleshooting

### "Connection refused" or "Cannot connect"

**Cause:** Phone can't reach your PC

**Fix:**
1. Verify phone and PC are on same WiFi
2. Check Windows Firewall:
   - Open Windows Defender Firewall
   - Click "Allow an app through firewall"
   - Find Python or add new rule for port 6969
3. Try pinging your PC from phone (use Network Analyzer app)

### "Server not responding"

**Cause:** LANA server not running

**Fix:**
```bash
python lana_server_fixed.py
```

### "Model not found" or "No response"

**Cause:** LM Studio not running or wrong model

**Fix:**
1. Open LM Studio
2. Verify server is started (green indicator)
3. Check the model name matches your config
4. Reload model if needed

### "Timeout" errors

**Cause:** Model is slow or request taking too long

**Fix:** In `lana_config.json`:
```json
{
  "timeouts": {
    "chat_completion": 180  ← Increase this
  }
}
```

### Can connect but no AI responses

**Cause:** Backend not forwarding to LM Studio

**Fix:**
1. Check LM Studio is running
2. Verify `lana_config.json` has correct IP
3. Run: `python homelink_connection_test.py`
4. Check LANA server logs for errors

## Network Setup

### Same WiFi Network

Your phone and PC **MUST** be on the same WiFi network. 

**Check:**
- Phone: Settings → WiFi → Note network name
- PC: Settings → Network → Note network name
- Must match!

### Firewall Configuration

If using Windows Firewall, add rule:
1. Windows Defender Firewall → Advanced Settings
2. Inbound Rules → New Rule
3. Port → TCP → 6969
4. Allow the connection
5. Name it "LANA Server"

Repeat for port 1234 if needed.

### Router Issues

Some routers block device-to-device communication (AP Isolation).

**Fix:**
- Check router settings
- Disable "AP Isolation" or "Client Isolation"
- Or connect both to guest network (if guest isolation is off)

## Testing Checklist

- [ ] LM Studio running and server started
- [ ] Model loaded in LM Studio
- [ ] `lana_config.json` created with correct IP
- [ ] Diagnostic script passes all tests
- [ ] LANA server running (port 6969)
- [ ] Phone and PC on same WiFi
- [ ] Firewall allows port 6969
- [ ] Homelink app configured with PC IP
- [ ] Test message works from app

## Integration with Your Existing Backend

If you already have a backend in your Homelink repo (in `/backend`), you have two options:

### Option 1: Use the New Server (Recommended)

Replace your existing backend with `lana_server_fixed.py`:
1. Copy all the new files to `/backend`
2. Update your app to point to port 6969
3. Keep your existing frontend unchanged

### Option 2: Integrate with Existing Backend

Add to your existing backend:

```python
from lm_studio_client import get_client

# In your chat endpoint:
@app.route("/api/chat", methods=["POST"])
def chat():
    data = request.json
    prompt = data.get("message")
    
    # Use LM Studio client
    lm_client = get_client()
    response = lm_client.chat_completion(prompt)
    
    return jsonify({"response": response})
```

## Mobile App Configuration

Your Homelink app likely has a settings screen. Configure:

```typescript
// In your app's config or settings
const API_CONFIG = {
  baseURL: "http://192.168.1.109:6969",  // Your PC IP
  endpoints: {
    chat: "/v1/chat/completions"
  },
  timeout: 30000  // 30 second timeout
};
```

## Verification Steps

1. **LM Studio working:**
   ```bash
   curl http://YOUR_PC_IP:1234/v1/models
   ```
   Should return JSON with loaded models

2. **LANA server working:**
   ```bash
   curl http://YOUR_PC_IP:6969/
   ```
   Should return LANA status

3. **Chat working:**
   ```bash
   curl -X POST http://YOUR_PC_IP:6969/v1/chat/completions \
     -H "Content-Type: application/json" \
     -d '{"prompt": "test", "linked_user": "Prinze"}'
   ```
   Should return AI response

4. **From phone:**
   - Use a REST client app (like Postman mobile)
   - Send POST to `http://YOUR_PC_IP:6969/v1/chat/completions`
   - Should work if on same network

## Success Indicators

When everything is working:

✅ LM Studio shows "Server running"
✅ LANA server shows "Ready"
✅ Diagnostic script passes all checks
✅ Phone can ping your PC IP
✅ Homelink app gets responses from LANA
✅ Messages appear in LANA server logs

## Next Steps After Connection Works

1. **Add more commands** - Extend intent_engine.py
2. **Enable vision** - Connect camera for visual queries
3. **Add voice** - Integrate voice input/output
4. **Persistent memory** - Save conversation context
5. **Custom personality** - Tune LANA's responses

## Support Resources

**If still not working:**

1. Run: `python homelink_connection_test.py` and share output
2. Check LANA server logs for errors
3. Verify LM Studio logs show incoming requests
4. Test with curl commands first before using app
5. Check Windows Event Viewer for firewall blocks

## File Locations

```
your-homelink-repo/
├── backend/
│   ├── lana_config.json              ← Configuration
│   ├── lm_studio_client.py           ← LM Studio connector
│   ├── lana_server_fixed.py          ← Main server
│   ├── vision_router_fixed.py        ← Vision handler
│   ├── homelink_connection_test.py   ← Diagnostic tool
│   └── intent_engine.py              ← Intent matching
├── components/                        ← Your React components
├── services/                          ← Your frontend services
└── App.tsx                            ← Your main app
```

Update your frontend service to use the new backend URL.

## Final Notes

- **Always use your PC's actual IP** (not localhost) in config
- **Keep phone and PC on same WiFi**
- **Start services in order:** LM Studio → LANA Server → Homelink App
- **Check logs** if anything fails
- **Test with diagnostic script** after any changes

The files I created earlier (lana_config.json, lm_studio_client.py, etc.) provide the complete connection infrastructure. The diagnostic script will tell you exactly what's wrong and how to fix it.
