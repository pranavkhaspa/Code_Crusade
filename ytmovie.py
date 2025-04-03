import json
import os
import re
from moviepy.editor import ImageClip, AudioFileClip, CompositeVideoClip, TextClip
# Ensure moviepy.editor is imported if audio_loop is used directly on the class
import moviepy.editor as mpy
from PIL import Image, ImageDraw, ImageFont
import traceback
import math # For ceiling function in looping

# Set up directories
os.makedirs("assets", exist_ok=True)
os.makedirs("output", exist_ok=True)

# Constants
# --- Configuration ---
# Try to find a suitable background, or fallback to generating one
BACKGROUND_IMAGE_PATH = "assets/background.jpg" # User should place their background here
MUSIC_FILE_PATH = "assets/music.mp3" # User should place their music file here
# Try common system fonts, fallback to Pillow's default if none are found
FONT_PATHS_TO_TRY = [
    "assets/arial.ttf", # Place custom font here first
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", # Common Linux Monospace
    "/System/Library/Fonts/Menlo.ttc", # Common macOS Monospace (might need index)
    "C:\\Windows\\Fonts\\consola.ttf", # Common Windows Monospace
    "cour.ttf", # Courier New (often available)
    "arial.ttf", # Arial (often available, fallback non-mono)
]
OUTPUT_VIDEO_PATH = "output/trick_question_video.mp4"
QUESTION_DATA_CACHE = "output/question_data.json" # Cache for the generated question data
IMAGE_CACHE = "output/question_image.png" # Cache for the generated image

# Video settings
VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
VIDEO_FPS = 30
VIDEO_DURATION_SECONDS = 15 # Standard short video length
ANSWER_REVEAL_START_SECONDS = 12
ANSWER_REVEAL_DURATION_SECONDS = VIDEO_DURATION_SECONDS - ANSWER_REVEAL_START_SECONDS
VIDEO_BITRATE = "5000k"

# Text/Layout settings
PADDING_X = 60 # Left/right padding for text content
TOP_PROMPT_Y = 60 # Y position for the top prompt
TITLE_FONT_SIZE = 65
CODE_FONT_SIZE = 50 # Monospaced font is ideal here
OPTION_FONT_SIZE = 55
PROMPT_FONT_SIZE = 40
TEXT_COLOR = "white"
CODE_COLOR_DEFAULT = (100, 200, 255) # Light blue/cyan
CODE_COLOR_KEYWORD = (255, 150, 0) # Orange
CODE_COLOR_STRING = (0, 255, 150) # Green/aqua
CODE_COLOR_COMMENT = (150, 150, 150) # Grey
ANSWER_TEXT_COLOR = "lime"
OPTION_TEXT_COLOR = "yellow"
CODE_BG_COLOR = (30, 30, 50, 230) # Semi-transparent dark blue/purple
CODE_OUTLINE_COLOR = (100, 200, 255)
OPTION_BG_COLOR = (50, 50, 70, 200) # Semi-transparent dark grey/blue
OPTION_OUTLINE_COLOR = (200, 200, 200, 128) # Semi-transparent light grey
OVERLAY_COLOR = (0, 0, 0, 180) # Semi-transparent black overlay
BOTTOM_MARGIN = 50 # Minimum space to leave at the bottom

# Ollama settings (if used)
OLLAMA_MODEL = 'deepseek-coder:6.7b' # Or choose another suitable model
# --- End Configuration ---

# Global variable for the detected font path
DETECTED_FONT_PATH = None

def find_font():
    """Tries to find a suitable font from the predefined list."""
    global DETECTED_FONT_PATH
    for font_path in FONT_PATHS_TO_TRY:
        try:
            # Basic check: does the file exist?
            if os.path.exists(font_path):
                 # More robust check: can ImageFont load it?
                _ = ImageFont.truetype(font_path, 10)
                print(f"✅ Found and using font: {font_path}")
                DETECTED_FONT_PATH = font_path
                return DETECTED_FONT_PATH
        except Exception:
            continue # Try the next font
    print("⚠️ No suitable TTF/TTC font found in predefined paths. Using Pillow's default font.")
    return None

# Helper function to clean markdown/quotes from string values
def clean_string_value(text):
    """Removes common markdown/quoting artifacts from start/end of a string."""
    if not isinstance(text, str):
        return text # Return as-is if not a string

    # Remove leading/trailing whitespace first
    cleaned_text = text.strip()

    # Patterns to remove from start/end (more comprehensive)
    patterns_start = [
        r"```(?:python|json|text|)\s*", # ```python, ```json, ```text, ```
        r"'''(?:python|)\s*",          # '''python, '''
        r'"""(?:python|)\s*',          # """python, """
        r"['\"]",                      # Leading single/double quote
    ]
    patterns_end = [
        r"\s*```",   # Trailing ```
        r"\s*'''",   # Trailing '''
        r'\s*"""',   # Trailing """
        r"['\"]",   # Trailing single/double quote
    ]

    # Remove start patterns iteratively
    made_change = True
    while made_change:
        made_change = False
        original_length = len(cleaned_text)
        for pattern in patterns_start:
            cleaned_text = re.sub(f"^{pattern}", "", cleaned_text, flags=re.IGNORECASE)
        if len(cleaned_text) != original_length:
            made_change = True
        cleaned_text = cleaned_text.strip() # Strip again after potential removal

    # Remove end patterns iteratively
    made_change = True
    while made_change:
        made_change = False
        original_length = len(cleaned_text)
        for pattern in patterns_end:
            cleaned_text = re.sub(f"{pattern}$", "", cleaned_text)
        if len(cleaned_text) != original_length:
            made_change = True
        cleaned_text = cleaned_text.strip() # Strip again

    return cleaned_text

# Step 1: Fetch a tricky programming question from Ollama or use sample
def fetch_question():
    """
    Fetches a programming question from Ollama or returns a sample if unavailable/fails.
    Ensures the returned data structure is validated.
    """
    # Try to import ollama, handle gracefully if not available
    try:
        import ollama
        prompt = """Generate a tricky programming question in Python.
        Provide a code snippet, 4 answer choices (A, B, C, D), and the correct answer.
        Format the response strictly as a valid JSON object with fields: "question", "code", "options", "correct_answer".
        - "question": A string containing only the question text.
        - "code": A string containing only the Python code, correctly indented. Use literal \\n for newlines within this string. No surrounding markdown.
        - "options": A JSON list of 4 strings, exactly like ["A) Option 1", "B) Option 2", "C) Option 3", "D) Option 4"]. Ensure each option starts clearly with A), B), C), or D).
        - "correct_answer": A single capital letter string (A, B, C, or D) indicating the correct option.

        Strictly adhere to this JSON structure. Do NOT include explanations or any text outside the JSON object. Do NOT use markdown formatting like ```json or ```python around the JSON object or within the string values.

        Example structure:
        {
          "question": "What is the output of this list comprehension?",
          "code": "my_list = [1, 2, 3, 4]\nresult = [x * 2 for x in my_list if x % 2 == 0]\nprint(result)",
          "options": ["A) [2, 4, 6, 8]", "B) [4, 8]", "C) [2, 6]", "D) Error"],
          "correct_answer": "B"
        }
        """

        print(f"🤖 Contacting Ollama model '{OLLAMA_MODEL}'...")
        try:
            response = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])

            if response and 'message' in response and 'content' in response['message']:
                content = response['message']['content'].strip()
                print("🔍 Raw response received from Ollama.")

                # --- JSON Extraction and Cleaning ---
                # 1. Try to find JSON within ```json ... ```
                json_match = re.search(r'```json\s*({.*?})\s*```', content, re.DOTALL | re.IGNORECASE)
                if json_match:
                    content = json_match.group(1)
                    print("🧹 Extracted JSON from ```json block.")
                else:
                    # 2. If no ```json, try finding JSON within ```python ... ``` (less likely but possible)
                    python_match = re.search(r'```python\s*({.*?})\s*```', content, re.DOTALL | re.IGNORECASE)
                    if python_match:
                       content = python_match.group(1)
                       print("🧹 Extracted JSON from ```python block.")
                    else:
                        # 3. If no code blocks, assume the core content might be JSON. Find the first '{' and last '}'
                        start_brace = content.find('{')
                        end_brace = content.rfind('}')
                        if start_brace != -1 and end_brace != -1 and end_brace > start_brace:
                            content = content[start_brace : end_brace + 1]
                            print("🧹 Extracted content between first '{' and last '}'.")
                        else:
                            print("⚠️ Could not reliably find JSON structure in the response.")
                            # Keep 'content' as is for the json.loads attempt below, maybe it's just the raw JSON

                # 4. Basic cleanup of potential lingering issues before parsing
                # Remove potential python comments if they surround the JSON
                content = re.sub(r"^\s*#.*?\n", "", content, flags=re.MULTILINE)
                # Remove potential escaped newlines that shouldn't be there in the structure
                # (but keep the literal \n needed inside code strings)
                content = content.replace("\\\n", "")
                # Fix trailing commas before closing brackets/braces
                content = re.sub(r',\s*([}\]])', r'\1', content)

                print("Attempting to parse JSON...")
                try:
                    data = json.loads(content)
                    print("✅ JSON parsed successfully.")

                    # --- Field-level Cleaning and Validation ---
                    print("🧹 Cleaning and validating JSON fields...")
                    validated_data = {}
                    is_valid = True

                    # Question
                    q_val = data.get('question')
                    if isinstance(q_val, str):
                        validated_data['question'] = clean_string_value(q_val)
                    else:
                        print("❌ Field 'question' is missing or not a string.")
                        is_valid = False

                    # Code
                    c_val = data.get('code')
                    if isinstance(c_val, str):
                        # Clean markdown, but preserve internal newlines and indentation
                        validated_data['code'] = clean_string_value(c_val)
                        # Basic check for expected newlines
                        if r'\n' not in validated_data['code'] and '\n' in validated_data['code'].strip():
                             # If model used literal newlines instead of escaped \n, fix it for JSON
                             print("⚠️ Fixing literal newlines in 'code' field to escaped '\\n'.")
                             validated_data['code'] = validated_data['code'].replace('\n', '\\n')
                    else:
                        print("❌ Field 'code' is missing or not a string.")
                        is_valid = False

                    # Options
                    o_val = data.get('options')
                    if isinstance(o_val, list) and len(o_val) == 4 and all(isinstance(opt, str) for opt in o_val):
                        cleaned_options = [clean_string_value(opt) for opt in o_val]
                        # Check if options start with A/B/C/D)
                        # Making check more robust to handle optional space after parenthesis
                        valid_prefixes = [r"A\)\s*", r"B\)\s*", r"C\)\s*", r"D\)\s*"]
                        if all(any(re.match(p, opt.strip(), re.IGNORECASE) for p in valid_prefixes) for opt in cleaned_options):
                             validated_data['options'] = cleaned_options
                        else:
                             print("❌ Field 'options' list items do not all start with A)/B)/C)/D) format.")
                             is_valid = False
                    else:
                        print("❌ Field 'options' is missing, not a list of 4 strings.")
                        is_valid = False

                    # Correct Answer
                    ca_val = data.get('correct_answer')
                    if isinstance(ca_val, str):
                         cleaned_ca = clean_string_value(ca_val).strip().upper()
                         if re.match(r'^[A-D]$', cleaned_ca):
                            validated_data['correct_answer'] = cleaned_ca
                         else:
                            print(f"❌ Field 'correct_answer' is not a single letter A, B, C, or D. Found: '{cleaned_ca}'")
                            is_valid = False
                    else:
                         print("❌ Field 'correct_answer' is missing or not a string.")
                         is_valid = False

                    if is_valid:
                        print("✅ All fields validated successfully.")
                        return validated_data
                    else:
                        print("❌ Validation failed. Falling back to sample question.")
                        print(f"🔧 Invalid Data Structure Received:\n{json.dumps(data, indent=2)}")
                        return None # Indicate failure

                except json.JSONDecodeError as e:
                    print(f"❌ JSON Decode Error: {e}")
                    print(f"📜 Raw Content attempted to parse:\n---\n{content}\n---")
                    return None # Indicate failure
                except Exception as e_val:
                    print(f"❌ Error during data validation/fixing: {e_val}")
                    traceback.print_exc()
                    return None # Indicate failure

            else:
                print("❌ Error: Unexpected Ollama response format.")
                print(f"📜 Response received: {response}")
                return None
        except Exception as e:
            print(f"❌ Error fetching or processing question from Ollama: {e}")
            traceback.print_exc()
            return None # Indicate failure

    except ImportError:
        print("ℹ️ Ollama module not installed. To generate questions dynamically, run: pip install ollama")
        return None # Indicate Ollama is not available

def get_sample_question():
    """Returns a default sample question dictionary."""
    print(" Ruko Jara - using sample question")
    # Example with a potentially longer option
    return {
        "question": "What data structure results from this Python code?",
        "code": "data = {i: i*i for i in range(5)}\nprint(type(data))",
        "options": [
            "A) List",
            "B) Tuple",
            "C) Set of key-value pairs representing squares (Dictionary)",
            "D) Array"
        ],
        "correct_answer": "C"
    }
    # return {
    #     "question": "What is the output of the following Python code?",
    #     "code": "def mystery(n):\n  a, b = 0, 1\n  result = []\n  while a < n:\n    result.append(a)\n    a, b = b, a + b\n  return result\n\nprint(mystery(10))",
    #     "options": ["A) [0, 1, 1, 2, 3, 5, 8]", "B) [1, 1, 2, 3, 5, 8]", "C) [0, 1, 2, 3, 5, 8]", "D) Error"],
    #     "correct_answer": "A"
    # }


# Step 2: Generate an image with formatted question text
def wrap_text(text, font, max_width):
    """Wraps text to fit max_width, preserving existing newlines."""
    text = str(text) # Ensure text is a string
    lines = []
    paragraphs = text.split('\n')

    for paragraph in paragraphs:
        words = paragraph.split(' ')
        if not words:
            lines.append('') # Preserve empty lines
            continue

        current_line = ""
        for word in words:
            # Handle potential empty strings from multiple spaces
            if not word:
                 # If the line isn't empty, add a space, otherwise ignore
                 if current_line:
                     current_line += " "
                 continue

            test_line = f"{current_line} {word}".strip()

            # Calculate text width using the reliable method
            line_width, _ = get_text_size(font, test_line)

            if line_width <= max_width:
                current_line = test_line
            else:
                # Add the previous line if it had content
                if current_line:
                    lines.append(current_line)
                # Start the new line with the current word
                current_line = word
                # Check if the single word itself exceeds max_width (force break)
                word_width, _ = get_text_size(font, current_line)

                if word_width > max_width:
                    # Simple character-based break for overly long words/tokens
                    # This is a basic fallback, might break mid-word
                    avg_char_width = word_width / len(current_line) if len(current_line) > 0 else 10 # Estimate
                    chars_per_line = max(1, int(max_width / avg_char_width)) if avg_char_width > 0 else 1
                    while len(current_line) > chars_per_line:
                        # Find last space before wrap point if possible for cleaner break
                        break_point = current_line[:chars_per_line].rfind(' ')
                        if break_point != -1 and break_point > 0 : # Found a space
                            lines.append(current_line[:break_point])
                            current_line = current_line[break_point:].strip()
                        else: # No space, hard break
                            lines.append(current_line[:chars_per_line])
                            current_line = current_line[chars_per_line:]

        # Add the last remaining part of the line for the paragraph
        if current_line:
            lines.append(current_line)

    return lines

def get_text_size(font, text):
    """Abstraction layer for getting text dimensions."""
    try:
        if hasattr(font, 'getbbox'):
            # Ensure text is string for PIL
            bbox = font.getbbox(str(text))
            # Calculate width and height from bounding box
            width = bbox[2] - bbox[0]
            height = bbox[3] - bbox[1]
            return width, height
        elif hasattr(font, 'getsize'):
            # Fallback for older versions or default fonts
            size = font.getsize(str(text))
            return size[0], size[1] # width, height
        else:
             # Absolute fallback if no size method found
             print(f"⚠️ Font object {font} has no getbbox or getsize method.")
             fallback_height = 20 # Estimate
             return len(str(text)) * (fallback_height // 2), fallback_height

    except Exception as e:
        print(f"⚠️ Error calculating text size for '{str(text)[:20]}...': {e}. Using fallback size.")
        # Provide a reasonable fallback size to avoid crashing
        fallback_height = 20 # Estimate
        if hasattr(font, 'size'): # Default font might have size attribute
             try: fallback_height = font.size
             except: pass
        return len(str(text)) * (fallback_height // 2), fallback_height


def create_text_image(question_data):
    """Generates the main image with question, code, options, etc."""
    global DETECTED_FONT_PATH # Use the globally found font

    try:
        # --- Background Setup ---
        try:
            if os.path.exists(BACKGROUND_IMAGE_PATH):
                img = Image.open(BACKGROUND_IMAGE_PATH).convert("RGBA")
                # Resize while maintaining aspect ratio (cover)
                img_ratio = img.width / img.height
                target_ratio = VIDEO_WIDTH / VIDEO_HEIGHT
                if img_ratio > target_ratio: # Wider than target: fit height, crop width
                    new_height = VIDEO_HEIGHT
                    new_width = int(new_height * img_ratio)
                else: # Taller than target: fit width, crop height
                    new_width = VIDEO_WIDTH
                    new_height = int(new_width / img_ratio)

                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Center crop
                left = (new_width - VIDEO_WIDTH) / 2
                top = (new_height - VIDEO_HEIGHT) / 2
                right = (new_width + VIDEO_WIDTH) / 2
                bottom = (new_height + VIDEO_HEIGHT) / 2
                img = img.crop((left, top, right, bottom))

            else:
                print(f"⚠️ Background image '{BACKGROUND_IMAGE_PATH}' not found. Creating plain background.")
                img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (20, 20, 40, 255)) # Dark blue default
        except Exception as e_img:
            print(f"⚠️ Error loading/resizing background image: {e_img}. Using plain background.")
            img = Image.new("RGBA", (VIDEO_WIDTH, VIDEO_HEIGHT), (20, 20, 40, 255))

        # --- Overlay ---
        overlay = Image.new('RGBA', img.size, OVERLAY_COLOR)
        img = Image.alpha_composite(img, overlay)
        draw = ImageDraw.Draw(img)

        # --- Font Loading ---
        try:
            if DETECTED_FONT_PATH:
                title_font = ImageFont.truetype(DETECTED_FONT_PATH, TITLE_FONT_SIZE)
                code_font = ImageFont.truetype(DETECTED_FONT_PATH, CODE_FONT_SIZE)
                option_font = ImageFont.truetype(DETECTED_FONT_PATH, OPTION_FONT_SIZE)
                prompt_font = ImageFont.truetype(DETECTED_FONT_PATH, PROMPT_FONT_SIZE)
            else: # Fallback to Pillow's default bitmap font
                title_font = ImageFont.load_default()
                code_font = ImageFont.load_default()
                option_font = ImageFont.load_default()
                prompt_font = ImageFont.load_default()
                print("ℹ️ Using default bitmap font. Appearance may vary.")

        except Exception as e_font:
            print(f"❌ Error loading font '{DETECTED_FONT_PATH}': {e_font}. Cannot create image.")
            traceback.print_exc()
            return None

        # --- Layout Variables ---
        content_width = VIDEO_WIDTH - 2 * PADDING_X
        current_y = TOP_PROMPT_Y # Start with space for the top prompt
        line_spacing_title = 15
        line_spacing_code = 10
        line_spacing_option = 10 # Spacing between lines *within* a wrapped option
        block_spacing = 40 # Space between major elements (prompt/question/code/options)
        option_inter_box_spacing = 25 # Vertical space between option boxes

        # --- 0. Draw Prompt at Top ---
        prompt_text = "Tap to pause! Answer in comments!"
        prompt_width, prompt_height = get_text_size(prompt_font, prompt_text)
        prompt_x = (VIDEO_WIDTH - prompt_width) // 2
        # Draw text using the initial current_y
        draw.text((prompt_x, current_y), prompt_text, fill=TEXT_COLOR, font=prompt_font)
        # Update current_y to be below the prompt for the next element
        current_y += prompt_height + block_spacing

        # --- 1. Draw Question Text ---
        question_text = question_data.get('question', "Error: Question missing")
        question_lines = wrap_text(question_text, title_font, content_width)
        # Use line height from the actual font if possible
        _, line_height_title = get_text_size(title_font, "Tg") # Approx height for setup
        for line in question_lines:
            # Recalculate actual line height in case of font variations
            _, actual_line_height = get_text_size(title_font, line)
            draw.text((PADDING_X, current_y), line, fill=TEXT_COLOR, font=title_font)
            current_y += actual_line_height + line_spacing_title
        # Adjust Y: Add block spacing, remove last line spacing added
        current_y += block_spacing - line_spacing_title

        # --- 2. Draw Code Block ---
        code_text = question_data.get('code', "# Error: Code missing")
        # Decode the escaped newlines from JSON into actual newlines for display
        code_text_display = code_text.encode().decode('unicode_escape')
        code_lines = code_text_display.split('\n')
        # Calculate code block dimensions for the background box
        code_block_content_height = 0
        max_code_line_height = 0
        if code_lines:
             # Calculate total height based on actual lines
             for line in code_lines:
                  _, h = get_text_size(code_font, line if line else " ") # Use space for empty line height
                  code_block_content_height += h + line_spacing_code
                  max_code_line_height = max(max_code_line_height, h)
             # Remove last spacing
             code_block_content_height -= line_spacing_code
        else: # Handle empty code block case
             _, max_code_line_height = get_text_size(code_font, " ")
             code_block_content_height = max_code_line_height

        code_block_padding_y = 20
        code_block_padding_x = 20
        code_block_total_height = code_block_content_height + 2 * code_block_padding_y
        code_box_y_start = current_y
        code_box_y_end = code_box_y_start + code_block_total_height

        # Draw the code background box
        draw.rectangle(
            [(PADDING_X - code_block_padding_x, code_box_y_start),
             (VIDEO_WIDTH - PADDING_X + code_block_padding_x, code_box_y_end)],
            fill=CODE_BG_COLOR,
            outline=CODE_OUTLINE_COLOR,
            width=2 # Outline width
        )

        # Draw code lines with basic syntax highlighting
        code_y = code_box_y_start + code_block_padding_y
        for line in code_lines:
            color = CODE_COLOR_DEFAULT
            stripped_line = line.strip()
            # Check order: comment > keyword > string
            if stripped_line.startswith('#'):
                color = CODE_COLOR_COMMENT
            # More robust keyword check (matches whole words)
            elif re.match(r'^\s*(def|class|if|else|elif|for|while|try|except|finally|return|import|from|with|yield|pass|break|continue|in|is|not|and|or|lambda|async|await|global|nonlocal|assert|del)\b', line):
                color = CODE_COLOR_KEYWORD
            # Simple check for quotes (can be improved)
            elif re.search(r'(\'|"|f\'|f"|\'\'\'|""")', line):
                color = CODE_COLOR_STRING

            # Draw the text (using code_x for indentation within the box)
            code_x = PADDING_X
            _, line_h = get_text_size(code_font, line if line else " ")
            draw.text((code_x, code_y), line, fill=color, font=code_font)
            code_y += line_h + line_spacing_code

        current_y = code_box_y_end + block_spacing # Move Y below the code box + spacing

        # --- 3. Draw Answer Options (Dynamically Sized) ---
        options = question_data.get('options', ["Error: Options missing"] * 4)
        option_box_internal_padding_y = 15
        option_box_internal_padding_x = 15 # Padding inside the option box L/R
        option_wrap_width = content_width - (2 * option_box_internal_padding_x) # Width available for text wrap inside box

        for i, option_text in enumerate(options):
            box_y_start = current_y

            # --- Calculate Dynamic Height ---
            wrapped_option_lines = wrap_text(str(option_text), option_font, option_wrap_width)
            option_content_height = 0
            if wrapped_option_lines:
                for line in wrapped_option_lines:
                    _, line_h = get_text_size(option_font, line if line else " ")
                    option_content_height += line_h + line_spacing_option
                option_content_height -= line_spacing_option # Remove trailing spacing
            else: # Handle empty option case
                _, line_h = get_text_size(option_font, " ")
                option_content_height = line_h

            dynamic_option_box_height = option_content_height + (2 * option_box_internal_padding_y)
            box_y_end = box_y_start + dynamic_option_box_height
            # --- End Calculate Dynamic Height ---

            # --- Overflow Check ---
            # Check if the *bottom* of the current box exceeds the screen limit minus margin
            if box_y_end > VIDEO_HEIGHT - BOTTOM_MARGIN:
                print(f"⚠️ Content overflow detected at option {i+1}. Stopping drawing options.")
                # Optionally draw an ellipsis or warning?
                # draw.text((PADDING_X, current_y), "...", fill="red", font=option_font)
                # current_y += get_text_size(option_font, "...")[1] # Move down slightly if drawing ellipsis
                break # Stop drawing more options

            # Draw option background box using dynamic height
            draw.rectangle(
                [(PADDING_X - 10, box_y_start), # Use main PADDING_X for box horizontal position
                 (VIDEO_WIDTH - PADDING_X + 10, box_y_end)],
                fill=OPTION_BG_COLOR,
                outline=OPTION_OUTLINE_COLOR,
                width=1
            )

            # --- Draw Wrapped Option Text ---
            option_text_y = box_y_start + option_box_internal_padding_y
            option_text_x = PADDING_X + option_box_internal_padding_x # Start text inside the box padding

            for line in wrapped_option_lines:
                _, line_h = get_text_size(option_font, line if line else " ")
                draw.text((option_text_x, option_text_y), line, fill=OPTION_TEXT_COLOR, font=option_font)
                option_text_y += line_h + line_spacing_option
            # --- End Draw Wrapped Option Text ---

            # Move Y for the next option box
            current_y = box_y_end + option_inter_box_spacing

        # Adjust current_y if options didn't overflow (remove last inter-box spacing)
        # Check if the loop completed fully (i points to the last index drawn)
        if i == len(options) - 1 and box_y_end <= VIDEO_HEIGHT - BOTTOM_MARGIN:
             current_y -= option_inter_box_spacing


        # --- 4. Prompt at Bottom (Removed - Moved to Top) ---

        # --- Save Image ---
        img_rgb = img.convert("RGB") # Convert to RGB for JPEG/MP4 compatibility
        img_rgb.save(IMAGE_CACHE)
        print(f"✅ Image successfully generated: {IMAGE_CACHE}")
        return IMAGE_CACHE

    except Exception as e:
        print(f"❌ Fatal Error creating image: {e}")
        traceback.print_exc()
        return None


# Step 3: Generate the video with animations
def create_video(image_path, question_data):
    """Creates the final video using the generated image and question data."""
    if not image_path or not os.path.exists(image_path):
        print(f"❌ Cannot create video: Image path '{image_path}' is invalid or missing.")
        return

    # --- Resource Handles (for finally block) ---
    img_clip = None
    music_clip = None
    answer_text_clip = None
    final_composite_clip = None
    full_music_clip = None # Handle for original music file

    try:
        print("🎬 Starting video creation process...")
        # --- Base Image Clip ---
        img_clip = ImageClip(image_path).set_duration(VIDEO_DURATION_SECONDS)

        # --- Audio ---
        if os.path.exists(MUSIC_FILE_PATH):
            try:
                print(f"🎵 Loading music: {MUSIC_FILE_PATH}")
                full_music_clip = mpy.AudioFileClip(MUSIC_FILE_PATH)

                # Ensure audio matches video duration using audio_loop
                if full_music_clip.duration < VIDEO_DURATION_SECONDS:
                    print(f"⚠️ Music duration ({full_music_clip.duration:.2f}s) is shorter than video ({VIDEO_DURATION_SECONDS}s). Looping.")
                    # Use audio_loop to fill the duration
                    # Note: audio_loop creates a new clip instance
                    music_clip = full_music_clip.audio_loop(duration=VIDEO_DURATION_SECONDS)
                    # No need to close full_music_clip here yet, finally block handles it
                else:
                    # Trim longer audio
                    music_clip = full_music_clip.subclip(0, VIDEO_DURATION_SECONDS)
                    # If subclip is the same object, don't close original yet
                    # If subclip created a new instance, we might close original, but finally is safer

                print(f"✅ Music prepared with target duration: {VIDEO_DURATION_SECONDS:.2f}s (Actual: {music_clip.duration:.2f}s)")

            except Exception as e_music:
                print(f"⚠️ Error loading or processing music file '{MUSIC_FILE_PATH}': {e_music}. Video will have no audio.")
                music_clip = None
                # full_music_clip might still be open if error occurred mid-process
        else:
            print(f"ℹ️ Music file not found at '{MUSIC_FILE_PATH}'. Creating video without audio.")
            music_clip = None

        # --- Answer Reveal Text Clip ---
        clips_to_compose = [img_clip] # Start with the base image
        correct_answer_letter = question_data.get('correct_answer', '?').strip().upper()
        options = question_data.get('options', [])
        correct_option_full_text = f"({correct_answer_letter})" # Fallback text

        # Find the full text of the correct option
        for opt in options:
            opt_str = str(opt).strip()
            # Check if the option string starts with the correct letter followed by common separators
            # Case-insensitive match, allowing optional space after parenthesis/dot etc.
            if re.match(rf"^\s*{re.escape(correct_answer_letter)}[\s).:\]]", opt_str, re.IGNORECASE):
                correct_option_full_text = opt_str
                break
             # Less reliable fallback if no separator matched (e.g., "AOption")
            elif opt_str.upper().startswith(correct_answer_letter):
                correct_option_full_text = opt_str # Keep searching for a better match potentially

        answer_display_text = f"✅ Answer: {correct_option_full_text}"

        try:
            print("🎨 Creating answer reveal text clip...")
            # Use detected font or common fallback if needed
            font_for_answer = DETECTED_FONT_PATH if DETECTED_FONT_PATH else "Arial-Bold"

            answer_text_clip = TextClip(
                txt=answer_display_text,
                fontsize=60, # Slightly larger font for answer
                color=ANSWER_TEXT_COLOR, # Use constant
                font=font_for_answer,
                bg_color='rgba(0, 0, 0, 0.7)', # Slightly darker background
                method='caption', # Wraps text automatically
                size=(VIDEO_WIDTH - 2 * PADDING_X, None), # Width constrained by padding, height auto
                align='West' # Align text left within the caption box
            )

            # Calculate position *after* clip is rendered to know its height
            answer_clip_height = answer_text_clip.h
            # Position it higher up, e.g., below the code block (estimate position)
            # This needs refinement - ideally calculate based on actual content height
            # For now, place it near the bottom but above the margin
            pos_y = VIDEO_HEIGHT - answer_clip_height - BOTTOM_MARGIN - 20 # Position above bottom margin

            answer_text_clip = answer_text_clip.set_position(('center', pos_y))
            answer_text_clip = answer_text_clip.set_start(ANSWER_REVEAL_START_SECONDS)
            answer_text_clip = answer_text_clip.set_duration(ANSWER_REVEAL_DURATION_SECONDS)

            # Add fade-in effect (optional)
            answer_text_clip = answer_text_clip.fadein(0.5)

            clips_to_compose.append(answer_text_clip)
            print("✅ Answer reveal clip created.")

        except Exception as e_textclip:
            print(f"❌ Error creating answer TextClip: {e_textclip}")
            print("ℹ️ Check font availability and TextClip parameters.")
            traceback.print_exc()
            # Continue without answer reveal if it fails

        # --- Composite Video ---
        print("🧩 Compositing video clips...")
        final_composite_clip = CompositeVideoClip(clips_to_compose, size=(VIDEO_WIDTH, VIDEO_HEIGHT))

        # --- Set Audio ---
        if music_clip:
            print("🔊 Adding audio track...")
            # Ensure audio duration precisely matches video after all composition
            # Allow a small tolerance for floating point comparisons
            if abs(music_clip.duration - final_composite_clip.duration) > 0.05:
                 print(f"⚠️ Final audio/video duration mismatch. Adjusting audio clip duration from {music_clip.duration:.2f}s to {final_composite_clip.duration:.2f}s.")
                 # Create a new subclip with the exact duration needed
                 # This is safer than set_duration which can have issues
                 try:
                    # Create a subclip from the *looped* or *trimmed* clip
                    adjusted_music_clip = music_clip.subclip(0, final_composite_clip.duration)
                    # Close the previous music_clip instance *if* it's different
                    if music_clip != adjusted_music_clip and hasattr(music_clip, 'close'):
                        try: music_clip.close()
                        except: pass
                    music_clip = adjusted_music_clip # Use the adjusted clip
                 except Exception as e_adjust:
                     print(f"❌ Error adjusting audio duration: {e_adjust}. Audio might be out of sync.")
                     # Proceed with potentially mismatched audio

            final_composite_clip = final_composite_clip.set_audio(music_clip)

        # --- Write Video File ---
        print(f"💾 Writing video file to: {OUTPUT_VIDEO_PATH}")
        final_composite_clip.write_videofile(
            OUTPUT_VIDEO_PATH,
            fps=VIDEO_FPS,
            codec="libx264",         # Good balance of quality/compatibility
            audio_codec="aac",       # Standard audio codec for MP4
            bitrate=VIDEO_BITRATE,   # Control video quality/filesize
            threads=os.cpu_count(),  # Use available CPU cores for faster rendering
            preset='medium',         # Encoding speed vs compression ('slow'/'veryslow' for better quality/smaller size, but slower)
            logger='bar',            # Show progress bar
            ffmpeg_params=[          # Additional FFmpeg parameters if needed
                '-profile:v', 'high', # H.264 profile
                '-pix_fmt', 'yuv420p' # Pixel format for compatibility
            ]
        )
        print(f"✅ Video generated successfully: {OUTPUT_VIDEO_PATH}")

    except Exception as e:
        print(f"❌ Fatal Error generating video: {e}")
        traceback.print_exc()
    finally:
        # --- Resource Cleanup ---
        print("🧹 Cleaning up resources...")
        # Safely attempt to close all MoviePy clip objects that were definitely created
        clips_to_close = [img_clip, music_clip, answer_text_clip, final_composite_clip, full_music_clip]

        for clip in clips_to_close:
            # Check if the variable exists and holds a clip object
            if clip is not None and hasattr(clip, 'close') and callable(clip.close):
                try:
                    clip.close()
                    print(f"Closed clip: {type(clip).__name__}")
                except Exception as e_close:
                    # Don't crash the script if closing fails, just log it
                    print(f"⚠️ Error closing clip resource ({type(clip).__name__}): {e_close}")
        print("✅ Cleanup finished.")


# Main process execution
def main():
    """Main function to orchestrate the video generation."""
    print("="*50)
    print("🎬 Starting YouTube Shorts/Reels Trick Question Video Generator")
    print("="*50)

    # --- Font Setup ---
    find_font() # Determine which font to use globally

    # --- Step 1: Get Question Data ---
    question_data = None
    try:
        question_data = fetch_question()
    except Exception as e_fetch:
        print(f"❌ Unhandled error during fetch_question: {e_fetch}")
        traceback.print_exc()

    if not question_data:
        print("⚠️ Fetching question failed or Ollama not available. Using sample question.")
        question_data = get_sample_question()

    # Final validation of the data we're about to use
    if not isinstance(question_data, dict) or not all(k in question_data for k in ["question", "code", "options", "correct_answer"]):
        print("❌ FATAL: Question data is invalid even after fallback. Cannot proceed.")
        print(f"Data structure: {question_data}")
        return # Exit script

    print("\n📝 Using Question Data:")
    print(f"   Question: {question_data.get('question', 'N/A')[:80]}...") # Truncate long questions
    # print(f"   Code:\n{question_data.get('code', 'N/A').encode().decode('unicode_escape')}") # Print decoded code if needed for debug
    print(f"   Options: {len(question_data.get('options', []))} found")
    print(f"   Correct Answer: {question_data.get('correct_answer', 'N/A')}")

    # Save the final question data used (useful for debugging/re-running)
    try:
        with open(QUESTION_DATA_CACHE, "w", encoding='utf-8') as f:
            json.dump(question_data, f, indent=4, ensure_ascii=False)
        print(f"ℹ️ Question data saved to {QUESTION_DATA_CACHE}")
    except Exception as e_json_save:
        print(f"⚠️ Error saving final question data to JSON: {e_json_save}")


    # --- Step 2: Create Image ---
    image_path = None
    try:
        print("\n🖼️ Generating content image...")
        image_path = create_text_image(question_data)
    except Exception as e_img_create:
        print(f"❌ Unhandled error during create_text_image: {e_img_create}")
        traceback.print_exc()

    # --- Step 3: Create Video ---
    if image_path:
        try:
            create_video(image_path, question_data)
        except Exception as e_vid_create:
            print(f"❌ Unhandled error during create_video: {e_vid_create}")
            traceback.print_exc()
    else:
        print("❌ Image creation failed. Cannot proceed to video generation.")

    print("\n🏁 Process finished.")
    print("="*50)


if __name__ == "__main__":
    main()