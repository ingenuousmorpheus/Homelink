"""
diagnose_connection.py
Comprehensive diagnostic tool for LANA <-> LM Studio connection
"""

import json
import requests
import sys
import time
from typing import Dict, Any


class ConnectionDiagnostics:
    """Diagnose all connection issues between LANA and LM Studio"""
    
    def __init__(self):
        self.issues = []
        self.warnings = []
        self.config = None
        self.lm_studio_url = None
    
    def run_all_checks(self):
        """Run complete diagnostic suite"""
        print("=" * 60)
        print("🔍 LANA ↔ LM STUDIO CONNECTION DIAGNOSTICS")
        print("=" * 60)
        print()
        
        # 1. Config file check
        if not self.check_config_file():
            print("\n❌ CRITICAL: Cannot proceed without config file")
            return False
        
        # 2. LM Studio reachability
        if not self.check_lm_studio_reachable():
            print("\n❌ CRITICAL: LM Studio not accessible")
            self.suggest_fixes()
            return False
        
        # 3. Model checks
        self.check_models()
        
        # 4. Endpoint tests
        self.test_endpoints()
        
        # 5. Camera check
        self.check_camera()
        
        # Summary
        print("\n" + "=" * 60)
        self.print_summary()
        print("=" * 60)
        
        return len(self.issues) == 0
    
    def check_config_file(self) -> bool:
        """Check if config file exists and is valid"""
        print("📋 Step 1: Checking configuration file...")
        
        try:
            with open("lana_config.json", "r") as f:
                self.config = json.load(f)
            
            # Validate structure
            required_keys = ["lm_studio", "models"]
            for key in required_keys:
                if key not in self.config:
                    self.issues.append(f"Missing '{key}' in lana_config.json")
            
            if "lm_studio" in self.config:
                lm_config = self.config["lm_studio"]
                self.lm_studio_url = lm_config.get("base_url")
                
                print(f"   ✅ Config loaded")
                print(f"   📍 LM Studio URL: {self.lm_studio_url}")
                return True
            else:
                self.issues.append("Invalid config structure")
                return False
                
        except FileNotFoundError:
            self.issues.append("lana_config.json not found")
            print("   ❌ Config file missing")
            print("\n   💡 Create lana_config.json with:")
            print('   {')
            print('     "lm_studio": {')
            print('       "base_url": "http://YOUR_IP:1234"')
            print('     },')
            print('     "models": {')
            print('       "primary": "your-model-name"')
            print('     }')
            print('   }')
            return False
            
        except json.JSONDecodeError:
            self.issues.append("lana_config.json has invalid JSON")
            print("   ❌ Config file has syntax errors")
            return False
    
    def check_lm_studio_reachable(self) -> bool:
        """Test if LM Studio server is accessible"""
        print("\n🔌 Step 2: Testing LM Studio connection...")
        
        if not self.lm_studio_url:
            print("   ❌ No LM Studio URL configured")
            return False
        
        endpoints_to_test = [
            "/v1/models",
            "/v1/chat/completions"
        ]
        
        for endpoint in endpoints_to_test:
            url = self.lm_studio_url + endpoint
            
            try:
                print(f"   Testing: {url}")
                
                if endpoint == "/v1/models":
                    response = requests.get(url, timeout=5)
                else:
                    # Just test reachability, not full request
                    response = requests.post(
                        url,
                        json={"model": "test", "messages": []},
                        timeout=5
                    )
                
                if response.status_code in [200, 400, 422]:
                    print(f"   ✅ Endpoint reachable: {endpoint}")
                else:
                    print(f"   ⚠️ Unexpected status {response.status_code}: {endpoint}")
                    
            except requests.exceptions.ConnectionError:
                self.issues.append(f"Cannot connect to {self.lm_studio_url}")
                print(f"   ❌ Connection refused")
                print(f"\n   💡 Possible causes:")
                print(f"      1. LM Studio is not running")
                print(f"      2. LM Studio server is not started")
                print(f"      3. IP address is wrong")
                print(f"      4. Firewall blocking connection")
                return False
                
            except requests.exceptions.Timeout:
                self.issues.append("LM Studio connection timeout")
                print(f"   ❌ Connection timeout")
                return False
                
            except Exception as e:
                self.issues.append(f"Connection error: {e}")
                print(f"   ❌ Error: {e}")
                return False
        
        print("   ✅ LM Studio is reachable")
        return True
    
    def check_models(self) -> bool:
        """Check if required models are loaded"""
        print("\n📦 Step 3: Checking loaded models...")
        
        try:
            url = self.lm_studio_url + "/v1/models"
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            
            data = response.json()
            loaded_models = [model["id"] for model in data.get("data", [])]
            
            print(f"   📋 Loaded models in LM Studio:")
            for model in loaded_models:
                print(f"      • {model}")
            
            # Check if configured models are loaded
            if "models" in self.config:
                primary = self.config["models"].get("primary")
                vision = self.config["models"].get("vision")
                
                if primary and primary not in loaded_models:
                    self.warnings.append(f"Primary model not loaded: {primary}")
                    print(f"   ⚠️ Primary model NOT loaded: {primary}")
                elif primary:
                    print(f"   ✅ Primary model loaded: {primary}")
                
                if vision and vision not in loaded_models:
                    self.warnings.append(f"Vision model not loaded: {vision}")
                    print(f"   ⚠️ Vision model NOT loaded: {vision}")
                elif vision:
                    print(f"   ✅ Vision model loaded: {vision}")
            
            return True
            
        except Exception as e:
            self.warnings.append(f"Could not check models: {e}")
            print(f"   ⚠️ Could not retrieve model list: {e}")
            return False
    
    def test_endpoints(self) -> bool:
        """Test actual API calls"""
        print("\n🧪 Step 4: Testing API endpoints...")
        
        # Test chat completion
        try:
            url = self.lm_studio_url + "/v1/chat/completions"
            
            payload = {
                "model": self.config["models"]["primary"],
                "messages": [
                    {"role": "user", "content": "Say 'Connection successful' in exactly two words."}
                ],
                "max_tokens": 10,
                "temperature": 0.1
            }
            
            print(f"   Sending test message...")
            
            start = time.time()
            response = requests.post(url, json=payload, timeout=30)
            elapsed = time.time() - start
            
            response.raise_for_status()
            data = response.json()
            
            result = data["choices"][0]["message"]["content"]
            
            print(f"   ✅ Chat completion works!")
            print(f"   ⏱️  Response time: {elapsed:.2f}s")
            print(f"   💬 Response: {result}")
            
            return True
            
        except requests.exceptions.HTTPError as e:
            self.issues.append(f"Chat API error: {e}")
            print(f"   ❌ API returned error: {e}")
            
            if response.status_code == 404:
                print(f"   💡 Model may not be loaded in LM Studio")
            
            return False
            
        except Exception as e:
            self.issues.append(f"Chat test failed: {e}")
            print(f"   ❌ Test failed: {e}")
            return False
    
    def check_camera(self):
        """Check if camera is available for vision features"""
        print("\n📸 Step 5: Checking camera availability...")
        
        try:
            import cv2
            
            cap = cv2.VideoCapture(0)
            if cap.isOpened():
                ret, frame = cap.read()
                cap.release()
                
                if ret:
                    print(f"   ✅ Camera is available")
                    print(f"   📐 Frame size: {frame.shape}")
                else:
                    self.warnings.append("Camera opened but frame capture failed")
                    print(f"   ⚠️ Camera opened but cannot capture frames")
            else:
                self.warnings.append("No camera detected")
                print(f"   ⚠️ No camera found")
                print(f"   💡 Vision features will not work without a camera")
                
        except ImportError:
            self.warnings.append("OpenCV not installed")
            print(f"   ⚠️ OpenCV (cv2) not installed")
            print(f"   💡 Install with: pip install opencv-python")
        
        except Exception as e:
            self.warnings.append(f"Camera check failed: {e}")
            print(f"   ⚠️ Camera check failed: {e}")
    
    def suggest_fixes(self):
        """Suggest fixes for common issues"""
        print("\n🔧 TROUBLESHOOTING STEPS:\n")
        
        print("1️⃣ Verify LM Studio is running:")
        print("   • Open LM Studio application")
        print("   • Load a model (kimi-vl-a3b-thinking-2506)")
        print("   • Click 'Start Server' in the Server tab")
        print()
        
        print("2️⃣ Check IP address:")
        print("   • In LM Studio, note the server address")
        print("   • Update lana_config.json with correct address")
        print("   • If on same machine, use: http://127.0.0.1:1234")
        print("   • If on different machine, use: http://192.168.1.109:1234")
        print()
        
        print("3️⃣ Test connection manually:")
        print("   • Open browser to: http://192.168.1.109:1234/v1/models")
        print("   • You should see JSON with loaded models")
        print()
        
        print("4️⃣ Check firewall:")
        print("   • Windows Firewall may block port 1234")
        print("   • Add exception for LM Studio")
        print()
    
    def print_summary(self):
        """Print diagnostic summary"""
        print("\n📊 DIAGNOSTIC SUMMARY\n")
        
        if not self.issues and not self.warnings:
            print("✅ ALL CHECKS PASSED - System ready!")
            print("\nYou can now:")
            print("  • Run: python lana_server_fixed.py")
            print("  • Test with your app")
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
        
        if self.issues:
            print("❌ System NOT ready - fix critical issues first")
        else:
            print("⚠️ System functional but has warnings")


def main():
    """Run diagnostics"""
    diagnostics = ConnectionDiagnostics()
    success = diagnostics.run_all_checks()
    
    if not success:
        sys.exit(1)
    
    sys.exit(0)


if __name__ == "__main__":
    main()
