"""
lm_studio_client.py
Unified LM Studio connection manager with health checks and error handling
"""

import json
import requests
import time
from typing import Optional, Dict, Any, List


class LMStudioClient:
    """Centralized client for all LM Studio API interactions"""
    
    def __init__(self, config_path: str = "lana_config.json"):
        self.config = self._load_config(config_path)
        self.base_url = self.config["lm_studio"]["base_url"]
        self.chat_endpoint = self.base_url + self.config["lm_studio"]["endpoints"]["chat"]
        self.models_endpoint = self.base_url + self.config["lm_studio"]["endpoints"]["models"]
        self.primary_model = self.config["models"]["primary"]
        self.vision_model = self.config["models"]["vision"]
        self.timeout = self.config["timeouts"]["chat_completion"]
        self.health_timeout = self.config["timeouts"]["health_check"]
        self.max_retries = self.config["retry"]["max_attempts"]
        self.retry_delay = self.config["retry"]["delay_seconds"]
        
        self._last_health_check = None
        self._is_healthy = False
    
    def _load_config(self, path: str) -> dict:
        """Load configuration from JSON file"""
        try:
            with open(path, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            raise FileNotFoundError(
                f"Configuration file not found: {path}\n"
                "Please create lana_config.json with LM Studio settings."
            )
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
    
    def health_check(self, force: bool = False) -> bool:
        """
        Check if LM Studio is accessible
        Uses cached result unless forced or stale (>30 seconds)
        """
        now = time.time()
        
        # Use cached result if recent
        if not force and self._last_health_check:
            if now - self._last_health_check < 30:
                return self._is_healthy
        
        try:
            response = requests.get(
                self.models_endpoint,
                timeout=self.health_timeout
            )
            
            self._is_healthy = response.status_code == 200
            self._last_health_check = now
            
            if self._is_healthy:
                print(f"✅ LM Studio connected at {self.base_url}")
            else:
                print(f"⚠️ LM Studio responded with status {response.status_code}")
            
            return self._is_healthy
            
        except requests.exceptions.ConnectionError:
            self._is_healthy = False
            self._last_health_check = now
            print(f"❌ Cannot connect to LM Studio at {self.base_url}")
            print("   Make sure LM Studio is running and the server is started.")
            return False
            
        except requests.exceptions.Timeout:
            self._is_healthy = False
            self._last_health_check = now
            print(f"⏱️ Connection to LM Studio timed out")
            return False
            
        except Exception as e:
            self._is_healthy = False
            self._last_health_check = now
            print(f"❌ Health check error: {e}")
            return False
    
    def get_loaded_models(self) -> Optional[List[str]]:
        """Get list of currently loaded models in LM Studio"""
        try:
            response = requests.get(
                self.models_endpoint,
                timeout=self.health_timeout
            )
            response.raise_for_status()
            
            data = response.json()
            models = [model["id"] for model in data.get("data", [])]
            
            print(f"📋 Loaded models: {models}")
            return models
            
        except Exception as e:
            print(f"❌ Failed to get models: {e}")
            return None
    
    def verify_model(self, model_name: str) -> bool:
        """Check if a specific model is loaded"""
        models = self.get_loaded_models()
        if models is None:
            return False
        
        is_loaded = model_name in models
        
        if not is_loaded:
            print(f"⚠️ Model '{model_name}' not loaded in LM Studio")
            print(f"   Available models: {models}")
        
        return is_loaded
    
    def chat_completion(
        self,
        prompt: str,
        model: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 1000,
        system_prompt: Optional[str] = None
    ) -> Optional[str]:
        """
        Send a chat completion request to LM Studio
        
        Args:
            prompt: User message
            model: Model name (uses primary if not specified)
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            system_prompt: Optional system message
            
        Returns:
            Generated text or None if failed
        """
        
        # Health check first
        if not self.health_check():
            return None
        
        model = model or self.primary_model
        
        # Build messages
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        # Retry logic
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.chat_endpoint,
                    json=payload,
                    timeout=self.timeout
                )
                response.raise_for_status()
                
                data = response.json()
                content = data["choices"][0]["message"]["content"]
                
                return content
                
            except requests.exceptions.ConnectionError:
                print(f"❌ Connection failed (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    
            except requests.exceptions.Timeout:
                print(f"⏱️ Request timed out (attempt {attempt + 1}/{self.max_retries})")
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    
            except requests.exceptions.HTTPError as e:
                print(f"❌ HTTP error: {e}")
                return None
                
            except KeyError:
                print(f"❌ Unexpected response format from LM Studio")
                return None
                
            except Exception as e:
                print(f"❌ Unexpected error: {e}")
                return None
        
        return None
    
    def vision_completion(
        self,
        prompt: str,
        image_base64: str,
        model: Optional[str] = None,
        temperature: float = 0.2
    ) -> Optional[str]:
        """
        Send a vision completion request with image
        
        Args:
            prompt: Text prompt
            image_base64: Base64-encoded image
            model: Vision model name (uses vision model if not specified)
            temperature: Sampling temperature
            
        Returns:
            Generated text or None if failed
        """
        
        if not self.health_check():
            return None
        
        model = model or self.vision_model
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{image_base64}"
                            }
                        }
                    ]
                }
            ],
            "temperature": temperature
        }
        
        try:
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                timeout=self.config["timeouts"]["vision_request"]
            )
            response.raise_for_status()
            
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            
            return content
            
        except Exception as e:
            print(f"❌ Vision request failed: {e}")
            return None
    
    def get_config(self) -> Dict[str, Any]:
        """Return current configuration"""
        return self.config


# Singleton instance
_client = None

def get_client() -> LMStudioClient:
    """Get singleton client instance"""
    global _client
    if _client is None:
        _client = LMStudioClient()
    return _client


# Convenience functions
def chat(prompt: str, **kwargs) -> Optional[str]:
    """Quick chat completion"""
    return get_client().chat_completion(prompt, **kwargs)

def vision(prompt: str, image_base64: str, **kwargs) -> Optional[str]:
    """Quick vision completion"""
    return get_client().vision_completion(prompt, image_base64, **kwargs)

def is_connected() -> bool:
    """Quick health check"""
    return get_client().health_check()


if __name__ == "__main__":
    print("🔧 LM Studio Client Test\n")
    
    client = LMStudioClient()
    
    # Test connection
    print("1. Testing connection...")
    if client.health_check(force=True):
        print("   ✅ Connection successful\n")
    else:
        print("   ❌ Connection failed\n")
        exit(1)
    
    # Check models
    print("2. Checking loaded models...")
    models = client.get_loaded_models()
    print()
    
    # Test chat
    print("3. Testing chat completion...")
    response = client.chat_completion("Say 'Hello from LANA' in one sentence.")
    if response:
        print(f"   Response: {response}\n")
    else:
        print("   ❌ Chat failed\n")
    
    print("✅ All tests complete")
