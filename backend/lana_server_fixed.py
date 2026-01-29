"""
lana_server_fixed.py
Updated LANA server with proper LM Studio connection management
"""

from flask import Flask, request, jsonify
import json
import os

from lm_studio_client import get_client
from intent_engine import match_intent
from actions import execute_command
from vision_router import handle_vision_intent, VISION_INTENTS

# =========================
# FLASK APP
# =========================

app = Flask(__name__)

# =========================
# BOOT
# =========================

print("=" * 50)
print("🖤 LANA OS-Link Server Starting...")
print("=" * 50)

# Load manifest
with open("lana_manifest.json", "r") as f:
    lana_manifest = json.load(f)

print(f"📋 Manifest loaded:")
print(f"   Type: {lana_manifest.get('type')}")
print(f"   User: {lana_manifest.get('linked_user')}")
print(f"   Signature: {lana_manifest.get('signature')}")

# Initialize LM Studio client
lm_client = get_client()

print("\n🔌 Testing LM Studio connection...")
if lm_client.health_check(force=True):
    print("✅ LM Studio connection established")
    
    # Verify models
    print("\n📦 Checking loaded models...")
    models = lm_client.get_loaded_models()
    
    if models:
        config = lm_client.get_config()
        primary = config["models"]["primary"]
        vision = config["models"]["vision"]
        
        if primary in models:
            print(f"   ✅ Primary model loaded: {primary}")
        else:
            print(f"   ⚠️ Primary model NOT loaded: {primary}")
            print(f"      Please load it in LM Studio")
        
        if vision in models:
            print(f"   ✅ Vision model loaded: {vision}")
        else:
            print(f"   ⚠️ Vision model NOT loaded: {vision}")
            print(f"      Vision commands will fail")
else:
    print("❌ LM Studio connection FAILED")
    print("   Please check:")
    print("   1. LM Studio is running")
    print("   2. Server is started in LM Studio")
    print("   3. IP address in lana_config.json is correct")
    print("\n⚠️ Server will start but LLM features will not work")

print("\n" + "=" * 50)
print("🚀 LANA OS-Link Ready")
print("=" * 50 + "\n")

# =========================
# MEMORY
# =========================

MEMORY_FILE = "learned_triggers.json"

def load_memory():
    """Load conversation memory from file"""
    if not os.path.exists(MEMORY_FILE):
        return {
            "recent_memory": [],
            "known_intents": {}
        }
    
    try:
        with open(MEMORY_FILE, "r") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return {
            "recent_memory": [],
            "known_intents": {}
        }
    
    # Ensure structure
    if "recent_memory" not in data:
        data["recent_memory"] = []
    if "known_intents" not in data:
        data["known_intents"] = {}
    
    return data


def save_context(entry):
    """Save conversation entry to memory"""
    data = load_memory()
    data["recent_memory"].append(entry)
    
    # Keep only last 100 entries
    if len(data["recent_memory"]) > 100:
        data["recent_memory"] = data["recent_memory"][-100:]
    
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

# =========================
# ROUTES
# =========================

@app.route("/")
def home():
    """Health check endpoint"""
    lm_status = "connected" if lm_client.health_check() else "disconnected"
    
    return jsonify({
        "service": "LANA OS-Link",
        "status": "running",
        "lm_studio": lm_status,
        "version": lana_manifest.get("version"),
        "user": lana_manifest.get("linked_user")
    })


@app.route("/health")
def health():
    """Detailed health check"""
    lm_healthy = lm_client.health_check()
    models = lm_client.get_loaded_models() if lm_healthy else []
    
    return jsonify({
        "lana": "healthy",
        "lm_studio": {
            "connected": lm_healthy,
            "endpoint": lm_client.base_url,
            "loaded_models": models
        }
    })


@app.route("/v1/chat/completions", methods=["POST"])
def chat_completions():
    """
    Main chat endpoint - compatible with OpenAI API format
    Handles both local commands and LLM queries
    """
    
    try:
        body = request.get_json(force=True)
        
        # Extract prompt (support multiple formats)
        prompt = body.get("prompt") or body.get("input")
        
        if not prompt:
            # Check for messages array (OpenAI format)
            messages = body.get("messages", [])
            if messages and len(messages) > 0:
                prompt = messages[-1].get("content", "")
        
        if not prompt:
            return jsonify({"error": "No input provided"}), 400
        
        # Get user identifier
        linked_user = body.get("linked_user", lana_manifest.get("linked_user", "unknown"))
        
        print(f"\n💬 [{linked_user}]: {prompt}")
        
        # =========================
        # INTENT MATCHING
        # =========================
        
        intent = match_intent(prompt)
        
        if intent:
            print(f"🎯 Intent matched: {intent}")
            
            # Check if vision intent
            if intent in VISION_INTENTS:
                print("👁️ Processing vision request...")
                vision_result = handle_vision_intent(intent, prompt)
                
                if "error" in vision_result:
                    response_text = f"Vision error: {vision_result['error']}"
                else:
                    response_text = vision_result.get("result", "No vision result")
            
            else:
                # Execute local command
                print("⚙️ Executing local command...")
                response_text = execute_command(intent, prompt)
        
        else:
            # No intent match - forward to LLM
            print("🤖 Forwarding to LLM...")
            
            # Check LM Studio connection
            if not lm_client.health_check():
                response_text = (
                    "I can't connect to my language model right now. "
                    "Please make sure LM Studio is running and the server is started."
                )
            else:
                # Send to LLM
                system_prompt = (
                    f"You are LANA, a helpful AI assistant linked to {linked_user}. "
                    "Be warm, concise, and helpful."
                )
                
                llm_response = lm_client.chat_completion(
                    prompt=prompt,
                    system_prompt=system_prompt
                )
                
                if llm_response:
                    response_text = llm_response
                else:
                    response_text = "I'm having trouble generating a response right now."
        
        print(f"💬 LANA: {response_text[:100]}{'...' if len(response_text) > 100 else ''}")
        
        # =========================
        # SAVE MEMORY
        # =========================
        
        save_context({
            "user": linked_user,
            "prompt": prompt,
            "response": response_text,
            "intent": intent
        })
        
        # =========================
        # RETURN RESPONSE
        # =========================
        
        return jsonify({
            "id": "lana-local",
            "object": "chat.completion",
            "model": lm_client.primary_model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": response_text
                    },
                    "finish_reason": "stop"
                }
            ],
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": len(response_text.split()),
                "total_tokens": len(prompt.split()) + len(response_text.split())
            }
        })
    
    except Exception as e:
        print(f"❌ Error in chat_completions: {e}")
        import traceback
        traceback.print_exc()
        
        return jsonify({
            "error": str(e),
            "type": "server_error"
        }), 500


@app.route("/test", methods=["POST"])
def test():
    """Quick test endpoint"""
    try:
        data = request.get_json()
        prompt = data.get("prompt", "Hello")
        
        response = lm_client.chat_completion(prompt)
        
        return jsonify({
            "prompt": prompt,
            "response": response,
            "connected": lm_client.health_check()
        })
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# =========================
# START SERVER
# =========================

if __name__ == "__main__":
    config = lm_client.get_config()
    server_config = config["server"]
    
    print(f"🌐 Starting server on {server_config['host']}:{server_config['port']}")
    
    app.run(
        host=server_config["host"],
        port=server_config["port"],
        debug=False
    )
