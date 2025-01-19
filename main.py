import os
import time
import base64
import io
import json
from mss import mss
import PIL.Image
import google.generativeai as genai
from google.ai.generativelanguage_v1beta.types import content
import pyautogui
from datetime import datetime
from pathlib import Path
import logging
import asyncio

class BlobTruncatingFormatter(logging.Formatter):
    """Custom formatter that truncates Blob data in logs"""
    def format(self, record):
        try:
            if isinstance(record.msg, str) and "Blob(data=" in record.msg:
                # Truncate the Blob data to first 100 chars
                record.msg = record.msg.split("Blob(data=")[0] + "Blob(data=<truncated>)"
            elif isinstance(record.args, tuple):
                # Handle format string logs
                args = list(record.args)
                for i, arg in enumerate(args):
                    if isinstance(arg, str) and "Blob(data=" in arg:
                        args[i] = arg.split("Blob(data=")[0] + "Blob(data=<truncated>)"
                record.args = tuple(args)
        except Exception as e:
            record.msg = f"Error formatting log: {e}"
        return super().format(record)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Output to console
        logging.FileHandler('app.log')  # Also save to file
    ]
)

# Set custom formatter for all handlers
formatter = BlobTruncatingFormatter('%(asctime)s - %(levelname)s - %(message)s')
for handler in logging.getLogger().handlers:
    handler.setFormatter(formatter)

# Configure Google API and client
GOOGLE_API_KEY = os.getenv('GOOGLE_API_KEY')
if not GOOGLE_API_KEY:
    raise ValueError("please set google_api_key environment variable")

# Initialize client
genai.configure(api_key=GOOGLE_API_KEY)

# Configure model
generation_config = {
    "temperature": 1,
    "top_p": 0.95,
    "top_k": 40,
    "max_output_tokens": 8192,
    "response_mime_type": "text/plain",
}

# Load expert context first
with open('context.json', 'r') as f:
    EXPERT_CONTEXT = json.load(f)
    # Fix: get function declarations from the last element of tools array
    # FUNCTION_DECLARATIONS = next(
    #     item['function_declarations'] 
    #     for item in EXPERT_CONTEXT['tools'] 
    #     if isinstance(item, dict) and 'function_declarations' in item
    # )

# Create model with tools
model = genai.GenerativeModel(
    model_name="gemini-2.0-flash-exp",
    generation_config=generation_config,
    tools=[
        {
            "function_declarations": [
                {
                    "name": "type_letters",
                    "description": "Type 2-3 letters to perform click",
                    "parameters": {
                        "type": "object",
                        "required": ["letters"],
                        "properties": {
                            "letters": {
                                "type": "string"
                            }
                        }
                    }
                },
                {
                    "name": "type_text",
                    "description": "Type text to make a comment",
                    "parameters": {
                        "type": "object",
                        "required": ["text"],
                        "properties": {
                            "text": {
                                "type": "string"
                            }
                        }
                    }
                }
            ]
        }
    ],
    tool_config={'function_calling_config': 'ANY'}
)



# Create screenshots directory if it doesn't exist
SCREENSHOTS_DIR = os.path.join(os.path.dirname(__file__), 'screenshots')
os.makedirs(SCREENSHOTS_DIR, exist_ok=True)

# Add after other global variables
LOG_FILE = Path(__file__).parent / "log.json"
if not LOG_FILE.exists():
    LOG_FILE.write_text("[]", encoding='utf-8')

def save_log(action: str, result: str = ""):
    """Save a log entry to log.json"""
    try:
        logs = json.loads(LOG_FILE.read_text())
        logs.append({
            "timestamp": datetime.now().isoformat(),
            "action": action,
            "result": result
        })
        LOG_FILE.write_text(json.dumps(logs, indent=2))
        logging.info(f"[LOG] {action}: {result}")
    except Exception as e:
        logging.error(f"failed to save log: {e}")

def get_recent_logs(n: int = 10) -> str:
    """Get the n most recent logs as a formatted string"""
    try:
        if not LOG_FILE.exists():
            return ""
        logs = json.loads(LOG_FILE.read_text(encoding='utf-8'))
        recent = logs[-n:]
        return "\n".join([f"[{log['timestamp']}] {log['action']}: {log['result']}" for log in recent])
    except Exception as e:
        logging.error(f"failed to read logs: {e}")
        return ""

def capture_screenshot():
    """Capture a screenshot of the top left quarter of the screen"""
    with mss() as sct:
        # Get the first monitor
        monitor = sct.monitors[1]  # Primary monitor
        
        # Calculate the region - width reduced to 1/3, height increased by 1/4
        width = monitor["width"] // 3  # Reduced from 1/2 to 1/3
        height = int(monitor["height"] * 0.625)  # Increased by 1/4 (0.5 * 1.25 = 0.625)
        region = {
            "top": monitor["top"],
            "left": monitor["left"],
            "width": width,
            "height": height
        }
        
        # Capture the screenshot
        screenshot = sct.grab(region)
        # Convert to PIL Image
        img = PIL.Image.frombytes("RGB", screenshot.size, screenshot.rgb)
        return img, region

def click_region_center(region):
    """Click the center of the specified region"""
    center_x = region["left"] + (region["width"] // 2)
    center_y = region["top"] + (region["height"] // 2)
    pyautogui.click(center_x, center_y)

def wait_for_load():
    """Wait for X.com feed to load by checking for common elements"""
    # logging.info("starting wait_for_load...")
    time.sleep(3)
    # logging.info("skipping load check - returning True")
    return True

def press_option():
    """Press and release the option key"""
    if wait_for_load():
        pyautogui.keyDown('option')
        time.sleep(0.1)
        pyautogui.keyUp('option')
    else:
        print("Page did not load within the expected time")
        
def type_letters(letters):
    """
    Type a sequence of 2-3 letters with a small delay between each and press option
    Args:
        letters (str): String of 2-3 letters to type
    Returns:
        tuple: (PIL.Image, dict) - The new screenshot and its region
    """
    if not isinstance(letters, str):
        raise ValueError("Input must be a string")
    
    if not 2 <= len(letters) <= 3:
        raise ValueError("Must provide 2-3 letters")
    
    if not letters.isalpha():
        raise ValueError("Input must contain only letters")
    
    # Type each letter with a small delay
    for letter in letters.lower():
        pyautogui.write(letter)
        time.sleep(0.1)  # Small delay between keystrokes
    
    # Press option after typing letters
    press_option()
    return capture_screenshot()

def type_text(text):
    """
    Type any text string with a small delay between characters
    Args:
        text (str): String to type
    """
    for char in text:
        pyautogui.write(char)
        time.sleep(0.1)  # Small delay between characters

def navigate_chrome():
    """Navigate Chrome to x.com in a new tab"""
    # Small pause to ensure Chrome is active
    time.sleep(0.5)
    
    # Open new tab with Command+T
    pyautogui.hotkey('command', 't')
    time.sleep(0.5)
    
    # Type x.com and press enter
    pyautogui.write('x.com')
    pyautogui.press('enter')
    
    # Wait for feed to load

    press_option()

def twitter_helper(image, max_retries=3, retry_delay=60):
    """Send the screenshot to Gemini 2 for analysis with social media expert context"""
    try:
        # logging.info("starting image conversion...")
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        temp_path = f'temp_screenshot_{timestamp}.jpg'
        image.save(temp_path, format="JPEG")
        
        file = genai.upload_file(temp_path, mime_type="image/jpeg")
        # logging.info(f"uploaded image as: {file.uri}")
        
        context = f"""{EXPERT_CONTEXT['identity']}
        
        Recent actions:
        {get_recent_logs()}
        
        Your tasks:
        {' and '.join(EXPERT_CONTEXT['tasks'])}
        
        Navigation rules:
        {' '.join(EXPERT_CONTEXT['rules'])}
        """
        
        chat = model.start_chat(history=[])
        response = chat.send_message([context, file, "What is next?"])
        
        # Handle response and execute functions
        for part in response.parts:
            if part.text:
                logging.info(f"received text: {part.text}")
            
            if fn := part.function_call:
                # logging.info(f"received function call: {fn.name}({fn.args})")
                
                # Execute the appropriate function
                if fn.name == "type_letters":
                    letters = fn.args.get("letters")
                    if letters:
                        logging.info(f"executing type_letters with: {letters}")
                        type_letters(letters)
                        save_log("type_letters", letters)
                
                elif fn.name == "type_text":
                    text = fn.args.get("text")
                    if text:
                        logging.info(f"executing type_text with: {text}")
                        type_text(text)
                        save_log("type_text", text)
                
                else:
                    logging.warning(f"unknown function call: {fn.name}")
        
        # Cleanup temp file
        os.remove(temp_path)
        return True
            
    except Exception as e:
        error_msg = f"error analyzing screenshot: {str(e)}"
        logging.error(error_msg)
        save_log("error", error_msg)
        if "429" in str(e) and max_retries > 0:
            retry_msg = f"hit rate limit, waiting {retry_delay} seconds before retry"
            logging.warning(retry_msg)
            save_log("warning", retry_msg)
            time.sleep(retry_delay)
            return twitter_helper(image, max_retries - 1, retry_delay)
        return False

def save_screenshot(image):
    """Save screenshot with timestamp"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'screenshot_{timestamp}.png'
    filepath = os.path.join(SCREENSHOTS_DIR, filename)
    image.save(filepath)
    print(f"Saved screenshot: {filename}")
    return filepath

def main():
    """Main function to run the social media engagement assistant"""
    try:
        print("Starting social media engagement assistant. Press Ctrl+C to stop.")
        
        # Create screenshots directory if it doesn't exist
        os.makedirs("screenshots", exist_ok=True)
        print(f"Screenshots will be saved in: {os.path.abspath('screenshots')}")
        
        # First capture screenshot and click center
        logging.info("capturing initial screenshot...")
        screenshot, region = capture_screenshot()
        logging.info("clicking center...")
        click_region_center(region)
        
        # Then navigate to X.com
        logging.info("navigating to x.com...")
        navigate_chrome()
        
        # Capture and analyze current view
        # logging.info("capturing first analysis screenshot...")
        screenshot, region = capture_screenshot()
        # logging.info("saving screenshot...")
        save_screenshot(screenshot)
        
        # Main engagement loop
        logging.info("starting main loop...")
        while True:
            # logging.info("calling twitter_helper...")
            # Get model's analysis and function calls
            success = twitter_helper(screenshot)
            # logging.info(f"twitter_helper returned: {success}")
            
            if not success:
                logging.error("no analysis returned, continuing...")
                time.sleep(5)  # Add delay before retry
                continue
            
            # Capture new screenshot for next iteration
            logging.info("capturing next screenshot...")
            screenshot, region = capture_screenshot()
            save_screenshot(screenshot)
                        
    except KeyboardInterrupt:
        print("\nStopping social media assistant...")
    except Exception as e:
        logging.error(f"Error in main loop: {e}")
        raise

if __name__ == "__main__":
    main()
