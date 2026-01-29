
import json
import httpx
import uvicorn
import os
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

# --- CONFIGURATION ---
# LM Studio default OpenAI-compatible API endpoint
LM_STUDIO_URL = "http://127.0.0.1:1234/v1"
# Shared secret for mobile-to-proxy authentication
API_KEY = "home-link-secret" 

app = FastAPI(title="HomeLink Proxy")

# EXTREMELY permissive CORS for local dev and mobile connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    model: str = "default"
    messages: List[Message]
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = True

def verify_key(x_api_key: Optional[str]):
    if not x_api_key or x_api_key != API_KEY:
        print(f"DEBUG: Auth failed. Expected '{API_KEY}', got '{x_api_key}'")
        raise HTTPException(status_code=403, detail="Forbidden: Invalid API Key")

@app.get("/")
async def root():
    return {"status": "online", "message": "HomeLink Proxy is active. Forwarding to LM Studio."}

@app.post("/chat")
async def proxy_chat(request: ChatRequest, x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    print(f"DEBUG: Incoming chat request for model: {request.model}")
    
    async def event_generator():
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                async with client.stream(
                    "POST", 
                    f"{LM_STUDIO_URL}/chat/completions",
                    json=request.dict(),
                    headers={"Content-Type": "application/json"}
                ) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        print(f"DEBUG: LM Studio Error: {error_body.decode()}")
                        yield f"data: {json.dumps({'error': f'LM Studio error: {error_body.decode()}'})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if line:
                            yield f"{line}\n\n"
            except Exception as e:
                print(f"DEBUG: Proxy exception: {str(e)}")
                yield f"data: {json.dumps({'error': f'Proxy Error: {str(e)}'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@app.get("/models")
async def get_models(x_api_key: Optional[str] = Header(None)):
    verify_key(x_api_key)
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(f"{LM_STUDIO_URL}/models")
            return resp.json()
        except Exception as e:
            print(f"DEBUG: Failed to fetch models: {str(e)}")
            raise HTTPException(status_code=503, detail="LM Studio unreachable on port 1234. Is LM Studio Server started?")

@app.options("/{rest_of_path:path}")
async def options_handler(request: Request):
    return JSONResponse(content={"ok": True})

if __name__ == "__main__":
    # Defaulting to 6969 as it seems to be the user's preferred port
    port = int(os.getenv("PORT", 6969))
    print(f"\n" + "="*40)
    print(f"🚀 HOMELINK PROXY IS STARTING")
    print(f"="*40)
    print(f"1. On your phone app, go to Settings (Cog icon)")
    print(f"2. Set Proxy URL to: http://100.107.136.88:{port}")
    print(f"3. Set Shared Secret to: {API_KEY}")
    print(f"4. Ensure LM Studio Server is RUNNING on port 1234")
    print(f"="*40 + "\n")
    uvicorn.run(app, host="0.0.0.0", port=port)
