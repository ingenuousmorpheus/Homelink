"""
homelink_connection_test.py

Test script to diagnose connection issues between:
- Homelink mobile app → Backend server → LM Studio

This tests the entire connection chain.
"""

import json
import requests
import socket
import time
from typing import Dict, Any, Optional


class HomelinkConnectionTest:
    """Test all connection points for Homelink app"""
    
    def __init__(self):
        self.config = None
        self.local_ip = None
        self.issues = []
        self.warnings = []
    
    def get_local_ip(self) -> str:
        """Get the local IP address of this machine"""
        try:
            # Connect to external address to determine local IP
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return local_ip
        except Exception:
            return "127.0.0.1"
    
    def run_all_tests(self):
        """Run complete diagnostic suite"""
        print("=" * 70)
        print("🔍 HOMELINK APP → LANA SERVER → LM STUDIO CONNECTION TEST")
        print("=" * 70)
        print()
        
        # Get local IP
        self.local_ip = self.get_local_ip()
        print(f"📍 Your PC's IP Address: {self.local_ip}")
        print(f"   Use this in your Homelink app settings!\n")
        
        # Step 1: Load config
        if not self.test_config():
            print("\n❌ STOP: Fix configuration first")
            self.print_config_help()
            return False
        
        # Step 2: Test LM Studio
        if not self.test_lm_studio():
            print("\n❌ STOP: Fix LM Studio connection first")
            self.print_lm_studio_help()
            return False
        
        # Step 3: Test LANA server
        if not self.test_lana_server():
            print("\n⚠️ WARNING: LANA server not running")
            self.print_server_help()
        
        # Step 4: Test from "mobile" perspective
        self.test_mobile_connection()
        
        # Summary
        print("\n" + "=" * 70)
        self.print_summary()
        print("=" * 70)
        
        return len(self.issues) == 0
    
    def test_config(self) -> bool:
        """Test if config file exists and is valid"""
        print("📋 Step 1: Checking configuration...")
        
        try:
            with open("lana_config.json", "r") as f:
                self.config = json.load(f)
            
            # Check required fields
            if "lm_studio" not in self.config:
                self.issues.append("Missing 'lm_studio' in config")
                print("   ❌ Config missing LM Studio settings")
                return False
            
            lm_config = self.config["lm_studio"]
            base_url = lm_config.get("base_url")
            
            if not base_url:
                self.issues.append("Missing LM Studio base_url")
                print("   ❌ Config missing LM Studio URL")
                return False
            
            print(f"   ✅ Config loaded")
            print(f"   📡 LM Studio URL: {base_url}")
            
            # Check if URL matches local IP
            if "localhost" in base_url or "127.0.0.1" in base_url:
                self.warnings.append(
                    "LM Studio URL uses localhost - mobile app won't be able to connect"
                )
                print(f"   ⚠️ Config uses localhost (won't work from mobile)")
                print(f"   💡 Change to: http://{self.local_ip}:1234")
            
            return True
            
        except FileNotFoundError:
            self.issues.append("lana_config.json not found")
            print("   ❌ Config file not found")
            return False
        except json.JSONDecodeError:
            self.issues.append("Invalid JSON in config")
            print("   ❌ Config has syntax errors")
            return False
    
    def test_lm_studio(self) -> bool:
        """Test LM Studio connection"""
        print("\n🤖 Step 2: Testing LM Studio connection...")
        
        if not self.config:
            return False
        
        lm_url = self.config["lm_studio"]["base_url"]
        models_endpoint = lm_url + "/v1/models"
        
        try:
            print(f"   Testing: {models_endpoint}")
            response = requests.get(models_endpoint, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            models = [m["id"] for m in data.get("data", [])]
            
            print(f"   ✅ LM Studio is running")
            print(f"   📦 Loaded models: {len(models)}")
            for model in models:
                print(f"      • {model}")
            
            # Check if configured model is loaded
            configured_model = self.config.get("models", {}).get("primary")
            if configured_model and configured_model not in models:
                self.warnings.append(f"Configured model '{configured_model}' not loaded")
                print(f"   ⚠️ Your configured model is not loaded!")
                print(f"      Expected: {configured_model}")
            
            return True
            
        except requests.exceptions.ConnectionError:
            self.issues.append("Cannot connect to LM Studio")
            print(f"   ❌ Cannot connect to {lm_url}")
            print(f"   💡 Is LM Studio running? Is server started?")
            return False
        
        except Exception as e:
            self.issues.append(f"LM Studio error: {e}")
            print(f"   ❌ Error: {e}")
            return False
    
    def test_lana_server(self) -> bool:
        """Test if LANA server is running"""
        print("\n🖤 Step 3: Testing LANA server...")
        
        server_config = self.config.get("server", {})
        port = server_config.get("port", 6969)
        
        # Test localhost
        local_url = f"http://localhost:{port}/"
        
        try:
            print(f"   Testing: {local_url}")
            response = requests.get(local_url, timeout=3)
            
            if response.status_code == 200:
                data = response.json()
                print(f"   ✅ LANA server is running")
                print(f"   📡 Service: {data.get('service', 'unknown')}")
                print(f"   👤 User: {data.get('user', 'unknown')}")
                print(f"   🔌 LM Studio: {data.get('lm_studio', 'unknown')}")
                return True
            else:
                self.warnings.append(f"LANA server returned status {response.status_code}")
                print(f"   ⚠️ Server responded with status {response.status_code}")
                return True
                
        except requests.exceptions.ConnectionError:
            self.warnings.append("LANA server not running")
            print(f"   ❌ LANA server is not running")
            print(f"   💡 Start it with: python lana_server_fixed.py")
            return False
        
        except Exception as e:
            self.warnings.append(f"Server test error: {e}")
            print(f"   ⚠️ Error: {e}")
            return False
    
    def test_mobile_connection(self):
        """Test connection as if from mobile app"""
        print("\n📱 Step 4: Testing mobile app perspective...")
        
        server_config = self.config.get("server", {})
        port = server_config.get("port", 6969)
        
        # Test via local IP (how mobile would connect)
        mobile_url = f"http://{self.local_ip}:{port}/"
        
        print(f"   Mobile app should connect to: {mobile_url}")
        
        try:
            print(f"   Testing from mobile perspective...")
            response = requests.get(mobile_url, timeout=3)
            
            if response.status_code == 200:
                print(f"   ✅ Mobile app can reach server at {mobile_url}")
            else:
                self.warnings.append("Mobile connection returned unexpected status")
                print(f"   ⚠️ Got status {response.status_code}")
        
        except requests.exceptions.ConnectionError:
            self.issues.append("Mobile app cannot reach server")
            print(f"   ❌ Mobile app CANNOT reach server at {mobile_url}")
            print(f"   💡 Possible causes:")
            print(f"      • LANA server not running")
            print(f"      • Firewall blocking port {port}")
            print(f"      • Phone and PC on different networks")
            
        except Exception as e:
            self.warnings.append(f"Mobile test error: {e}")
            print(f"   ⚠️ Error: {e}")
        
        # Test chat endpoint
        chat_url = f"http://{self.local_ip}:{port}/v1/chat/completions"
        print(f"\n   Testing chat endpoint: {chat_url}")
        
        try:
            test_payload = {
                "prompt": "test",
                "linked_user": "Homelink Test"
            }
            
            response = requests.post(chat_url, json=test_payload, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                message = data.get("choices", [{}])[0].get("message", {}).get("content", "")
                print(f"   ✅ Chat endpoint works!")
                print(f"   💬 Response: {message[:80]}...")
            else:
                print(f"   ⚠️ Chat endpoint returned status {response.status_code}")
        
        except requests.exceptions.ConnectionError:
            print(f"   ❌ Chat endpoint not reachable")
        
        except Exception as e:
            print(f"   ⚠️ Chat test error: {e}")
    
    def print_config_help(self):
        """Print help for fixing config"""
        print("\n" + "=" * 70)
        print("🔧 HOW TO FIX CONFIG")
        print("=" * 70)
        print("\n1. Create lana_config.json in the same folder as your server")
        print("\n2. Copy this template and update the values:\n")
        print('''{
  "lm_studio": {
    "host": "''' + self.local_ip + '''",
    "port": 1234,
    "base_url": "http://''' + self.local_ip + ''':1234",
    "endpoints": {
      "chat": "/v1/chat/completions",
      "models": "/v1/models"
    }
  },
  "models": {
    "primary": "kimi-vl-a3b-thinking-2506",
    "vision": "zai-org/glm-4.6v-flash"
  },
  "server": {
    "host": "0.0.0.0",
    "port": 6969
  },
  "timeouts": {
    "chat_completion": 120,
    "vision_request": 60,
    "health_check": 5
  }
}''')
        print("\n3. Make sure to use your PC's IP address, not localhost!")
    
    def print_lm_studio_help(self):
        """Print help for fixing LM Studio"""
        print("\n" + "=" * 70)
        print("🔧 HOW TO FIX LM STUDIO")
        print("=" * 70)
        print("\n1. Open LM Studio")
        print("2. Go to 'Local Server' tab")
        print("3. Load a model (e.g., kimi-vl-a3b-thinking-2506)")
        print("4. Click 'Start Server'")
        print("5. Note the address shown (should be like http://192.168.1.109:1234)")
        print("6. Update lana_config.json with this address")
    
    def print_server_help(self):
        """Print help for starting server"""
        print("\n" + "=" * 70)
        print("🔧 HOW TO START LANA SERVER")
        print("=" * 70)
        print("\n1. Open terminal in your LANA project folder")
        print("2. Run: python lana_server_fixed.py")
        print("3. You should see:")
        print("   ✅ LM Studio connection established")
        print("   🚀 LANA OS-Link Ready")
        print(f"\n4. Server will listen on port 6969")
    
    def print_summary(self):
        """Print final summary"""
        print("\n📊 CONNECTION TEST SUMMARY\n")
        
        if not self.issues and not self.warnings:
            print("✅ ALL SYSTEMS GO!")
            print("\n🎯 NEXT STEPS FOR YOUR HOMELINK APP:\n")
            print(f"1. In your Homelink mobile app settings:")
            print(f"   • Set server URL to: http://{self.local_ip}:6969")
            print(f"   • Test connection")
            print()
            print(f"2. Make sure your phone and PC are on the SAME WiFi network")
            print()
            print(f"3. If using firewall, allow port 6969")
            print()
            print(f"4. Send test message from app to verify it works")
            return
        
        if self.issues:
            print(f"❌ CRITICAL ISSUES ({len(self.issues)}):")
            for i, issue in enumerate(self.issues, 1):
                print(f"   {i}. {issue}")
            print()
        
        if self.warnings:
            print(f"⚠️ WARNINGS ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"   {i}. {warning}")
            print()
        
        print("\n🎯 ACTION ITEMS:\n")
        
        if "lana_config.json not found" in self.issues:
            print("   1. Create lana_config.json (see template above)")
        
        if any("LM Studio" in i for i in self.issues):
            print("   2. Start LM Studio server")
        
        if any("server not running" in w.lower() for w in self.warnings):
            print("   3. Start LANA server: python lana_server_fixed.py")
        
        if any("localhost" in w for w in self.warnings):
            print(f"   4. Update config to use {self.local_ip} instead of localhost")
        
        print(f"\n   5. In Homelink app, set server to: http://{self.local_ip}:6969")
        print(f"   6. Ensure phone and PC are on same WiFi network")


def main():
    """Run connection tests"""
    tester = HomelinkConnectionTest()
    success = tester.run_all_tests()
    
    if not success:
        print("\n⚠️ Please fix the issues above before using your Homelink app")
        return 1
    
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
