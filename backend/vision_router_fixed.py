"""
vision_router_fixed.py
Updated vision router using unified LM Studio client
"""

import base64
import cv2
import time
from typing import Optional, Dict, Any

from lm_studio_client import get_client
from vision_state import update_vision_state

# Vision-specific intents
VISION_INTENTS = {
    "see",
    "see_me",
    "check_wellbeing",
    "identify_objects",
    "read_text",
    "save_view"
}


def _capture_frame() -> Optional[str]:
    """
    Capture a frame from the camera and return as base64
    
    Returns:
        Base64-encoded JPEG or None if failed
    """
    try:
        cap = cv2.VideoCapture(0)
        time.sleep(0.2)  # Let camera warm up
        
        ret, frame = cap.read()
        cap.release()
        
        if not ret:
            print("❌ Camera capture failed")
            return None
        
        # Encode as JPEG
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
        image_b64 = base64.b64encode(buffer).decode("utf-8")
        
        print(f"📸 Captured frame ({len(image_b64)} bytes)")
        return image_b64
        
    except Exception as e:
        print(f"❌ Camera error: {e}")
        return None


def _get_vision_prompt(intent: str, user_prompt: str = "") -> str:
    """
    Generate appropriate prompt based on intent
    
    Args:
        intent: The vision intent type
        user_prompt: Original user input
        
    Returns:
        Optimized prompt for the vision model
    """
    
    prompts = {
        "see": "Describe what you see in this image in 2-3 sentences.",
        
        "see_me": (
            "Is there a person visible in this image? "
            "If yes, briefly describe what you can see about them (position, posture, etc). "
            "If no, describe what is visible instead."
        ),
        
        "check_wellbeing": (
            "Analyze the person in this image. "
            "Do they appear tired, stressed, energetic, or calm? "
            "Provide a brief wellbeing assessment based on visible cues."
        ),
        
        "identify_objects": (
            "List all objects you can identify in this image. "
            "Format: Object 1, Object 2, Object 3, etc."
        ),
        
        "read_text": (
            "Extract and transcribe any visible text in this image. "
            "If no text is visible, state 'No text detected'."
        ),
        
        "save_view": "Describe this scene in detail for archival purposes."
    }
    
    # Use custom prompt or default
    if user_prompt and len(user_prompt) > 10:
        # User provided specific instructions
        return user_prompt
    else:
        return prompts.get(intent, "Describe what you see.")


def handle_vision_intent(
    intent: str,
    prompt: str = "",
    save_image: bool = False
) -> Dict[str, Any]:
    """
    Handle vision-based intents using camera + vision model
    
    Args:
        intent: Vision intent type
        prompt: User's original prompt (optional)
        save_image: Whether to save the captured image
        
    Returns:
        Dictionary with result or error
    """
    
    print(f"\n👁️ Vision request: {intent}")
    
    # Update state to active
    update_vision_state(intent=intent, active=True)
    
    # Capture frame
    image_b64 = _capture_frame()
    
    if not image_b64:
        update_vision_state(
            result="Camera capture failed",
            active=False
        )
        return {
            "error": "camera_failed",
            "message": "Unable to access camera"
        }
    
    # Save image if requested
    if save_image:
        try:
            import datetime
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"lana_view_{timestamp}.jpg"
            
            # Decode and save
            img_data = base64.b64decode(image_b64)
            with open(filename, "wb") as f:
                f.write(img_data)
            
            print(f"💾 Saved image: {filename}")
        except Exception as e:
            print(f"⚠️ Failed to save image: {e}")
    
    # Generate appropriate prompt
    vision_prompt = _get_vision_prompt(intent, prompt)
    
    print(f"🎯 Vision prompt: {vision_prompt[:80]}...")
    
    # Get LM Studio client
    lm_client = get_client()
    
    # Check connection
    if not lm_client.health_check():
        error_msg = "LM Studio not connected"
        update_vision_state(result=error_msg, active=False)
        return {
            "error": "lm_studio_disconnected",
            "message": error_msg
        }
    
    # Send vision request
    try:
        result_text = lm_client.vision_completion(
            prompt=vision_prompt,
            image_base64=image_b64
        )
        
        if result_text:
            print(f"✅ Vision result: {result_text[:100]}...")
            
            update_vision_state(
                result=result_text,
                active=False
            )
            
            return {
                "intent": intent,
                "result": result_text,
                "success": True
            }
        else:
            error_msg = "Vision model returned no response"
            update_vision_state(result=error_msg, active=False)
            return {
                "error": "no_response",
                "message": error_msg
            }
    
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Vision error: {error_msg}")
        
        update_vision_state(result=error_msg, active=False)
        
        return {
            "error": "vision_failed",
            "message": error_msg
        }


def quick_vision_check() -> Optional[str]:
    """Quick vision check - what does LANA see right now?"""
    result = handle_vision_intent("see", "Describe what you see briefly")
    return result.get("result") if "result" in result else None


# =========================
# TESTING
# =========================

if __name__ == "__main__":
    print("🧪 Testing Vision Router\n")
    
    # Test camera
    print("1. Testing camera capture...")
    frame = _capture_frame()
    if frame:
        print(f"   ✅ Camera works (captured {len(frame)} bytes)\n")
    else:
        print("   ❌ Camera failed\n")
        exit(1)
    
    # Test vision intent
    print("2. Testing vision intent...")
    result = handle_vision_intent("see", "What do you see?")
    
    if "error" in result:
        print(f"   ❌ Vision failed: {result['error']}")
        print(f"      {result.get('message', '')}")
    else:
        print(f"   ✅ Vision result:")
        print(f"      {result['result']}")
    
    print("\n✅ Vision router test complete")
