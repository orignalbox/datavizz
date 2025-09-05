import os
import re
import json
import subprocess
from flask import Flask, request, jsonify, render_template_string

import google.generativeai as genai

# --- Constants ---
STATIC_DIR = "static"
GENERATED_CODE_FILENAME = "generated_scene.py"

# --- App Initialization ---
app = Flask(__name__)

# --- Gemini API Configuration ---
def configure_gemini():
    """Configures the Gemini API."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("FATAL: GOOGLE_API_KEY environment variable not set.")
    genai.configure(api_key=api_key)

try:
    configure_gemini()
    model = genai.GenerativeModel('gemini-1.5-flash')
except ValueError as e:
    print(e)
    model = None

# --- Prompt Engineering Module ---
class Prompts:
    PROMPT_ENHANCER = """
    You are a world-class creative director for a motion graphics studio specializing in Manim animations.
    A client has given you a simple idea. Your task is to expand this into a detailed, scene-by-scene storyboard.
    Focus on visual storytelling. Describe the objects, their transformations, the camera movements, and the overall narrative flow.
    The output should be a rich, descriptive paragraph that will inspire a designer and a programmer.
    Client's Idea: "{prompt}"
    """

    DESIGNER = """
    You are a senior visual designer with a keen eye for aesthetics and color theory.
    Based on the following storyboard, develop a cohesive visual theme for a Manim animation.
    Your output MUST be a JSON object with the following keys:
    - "palette": A list of 5-7 complementary hex color codes.
    - "background_color": A single hex color code for the scene background.
    - "font": A suggestion for a common font family (e.g., "Inter", "Lato", "Roboto").
    - "animation_style": A brief description of the animation's feel (e.g., "Smooth and fluid", "Minimal and precise", "Playful and bouncy").

    Storyboard: "{description}"
    """

    MANIM_CODER = """
    You are a lead Manim developer with extensive experience in writing clean, efficient, and correct animation code.
    Your task is to write a complete, runnable Python script for a Manim animation based on a storyboard and a design brief.
    **CRITICAL INSTRUCTIONS:**
    1. The script MUST be a single, complete Python file.
    2. Import all necessary classes from `manim`.
    3. The main animation class MUST inherit from `Scene`.
    4. The entire animation logic MUST be within the `construct` method.
    5. **Strictly adhere to the design brief**: Use the provided `palette`, `background_color`, and `font`. Set the background color using `config.background_color`.
    6. **Aspect Ratio**: Design the animation for a '{aspect_ratio}' aspect ratio.
    7. **Code Only**: Your output MUST be ONLY the raw Python code. Do not wrap it in markdown.
    **Storyboard:** {description}
    **Design Brief (JSON):** {theme}
    """

    PROMPT_SUGGESTER = """
    You are a creative spark. Brainstorm 3 diverse and visually interesting ideas for a short animation using Manim.
    The ideas should range from mathematical concepts to abstract data visualizations.
    Return your answer as a perfectly formatted JSON array of strings. Example: ["idea 1", "idea 2", "idea 3"].
    """

    CODE_EXPLAINER = """
    You are a friendly and skilled Manim teaching assistant.
    Explain the following Manim code in a clear, concise, and beginner-friendly way.
    Break down your explanation into logical sections using markdown headings (e.g., ### Setup, ### Animation Sequence).
    Explain what the code *does* and *why*. Your output should be clean, well-formatted markdown.
    **Manim Code to Explain:** ```python\n{code}\n```
    """

    TITLE_GENERATOR = """
    You are a creative copywriter specializing in catchy titles for video content.
    Based on the following animation storyboard, generate a title and a short, engaging description (1-2 sentences).
    The tone should be intriguing and suitable for platforms like YouTube or Twitter.
    Return your answer as a single, perfectly formatted JSON object with two keys: "title" and "description".
    **Storyboard:** {description}
    """

# --- Helper function for sanitizing LLM JSON output ---
def clean_json_response(text):
    """Extracts a JSON object or array from a string."""
    text = text.strip()
    # Find the start of the JSON (either { or [)
    start_brace = text.find('{')
    start_bracket = text.find('[')
    
    start_index = -1
    if start_brace != -1 and start_bracket != -1:
        start_index = min(start_brace, start_bracket)
    elif start_brace != -1:
        start_index = start_brace
    else:
        start_index = start_bracket

    if start_index == -1:
        raise ValueError("No JSON object or array found in the response.")
        
    # Find the corresponding end brace/bracket
    end_char = '}' if text[start_index] == '{' else ']'
    return text[start_index : text.rfind(end_char) + 1]


# --- Core Logic / Services ---
def enhance_prompt(user_prompt):
    print("Step 1: Enhancing prompt...")
    response = model.generate_content(Prompts.PROMPT_ENHANCER.format(prompt=user_prompt))
    return response.text

def design_theme(description):
    print("Step 2: Designing theme...")
    response = model.generate_content(Prompts.DESIGNER.format(description=description))
    return clean_json_response(response.text)

def generate_title_and_desc(description):
    print("Step 2.5: Generating title...")
    response = model.generate_content(Prompts.TITLE_GENERATOR.format(description=description))
    return clean_json_response(response.text)

def generate_manim_code(description, theme, aspect_ratio):
    print("Step 3: Generating Manim code...")
    response = model.generate_content(Prompts.MANIM_CODER.format(description=description, theme=theme, aspect_ratio=aspect_ratio))
    return response.text.strip()

def render_manim_video(code, quality):
    print(f"Step 4: Rendering video with quality '{quality}'...")
    with open(GENERATED_CODE_FILENAME, "w") as f: f.write(code)
    scene_match = re.search(r"class (\w+)\(Scene\):", code)
    if not scene_match: raise ValueError("Could not find a Scene class in the generated code.")
    scene_name = scene_match.group(1)
    
    quality_flags = {"fast": "-pql", "good": "-pqm", "best": "-pqh"}
    command = ["manim", quality_flags.get(quality, "-pqh"), GENERATED_CODE_FILENAME, scene_name, "--media_dir", STATIC_DIR]
    
    result = subprocess.run(command, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"--- MANIM ERROR ---\n{result.stderr}\n--- END MANIM ERROR ---")
        raise RuntimeError("Manim rendering failed. Check console for details.")
    
    print("Manim render successful!")
    video_folder = GENERATED_CODE_FILENAME.replace('.py', '')
    res_folder_map = {"fast": "480p15", "good": "720p30", "best": "1080p60"}
    res_folder = res_folder_map.get(quality, "1080p60")
    search_dir = os.path.join(STATIC_DIR, "videos", video_folder, res_folder)
    
    if os.path.exists(search_dir):
        for file in os.listdir(search_dir):
            if file.endswith(".mp4") and scene_name in file:
                return os.path.join("static/videos", video_folder, res_folder, file).replace("\\", "/")
    raise FileNotFoundError("Could not locate the rendered video file.")

# --- API Endpoints / Controllers ---
@app.route('/')
def index():
    return render_template_string(open('templates/index.html').read())

@app.route('/generate', methods=['POST'])
def generate_endpoint():
    if not model: return jsonify({'error': 'Gemini API not configured.'}), 503
    data = request.json
    if not data or 'prompt' not in data: return jsonify({'error': 'Prompt is required.'}), 400
    
    try:
        description = enhance_prompt(data['prompt'])
        theme = design_theme(description)
        meta_json = generate_title_and_desc(description)
        code = generate_manim_code(description, theme, data.get('aspectRatio', 'landscape'))
        video_path = render_manim_video(code, data.get('quality', 'best'))
        
        return jsonify({
            'video_path': video_path,
            'code': code,
            'meta': json.loads(meta_json)
        })
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return jsonify({'error': f'An error occurred: {str(e)}'}), 500

@app.route('/suggest_prompts', methods=['GET'])
def suggest_prompts_endpoint():
    if not model: return jsonify({'error': 'Gemini API not configured.'}), 503
    try:
        response = model.generate_content(Prompts.PROMPT_SUGGESTER)
        suggestions = json.loads(clean_json_response(response.text))
        return jsonify(suggestions)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/explain_code', methods=['POST'])
def explain_code_endpoint():
    if not model: return jsonify({'error': 'Gemini API not configured.'}), 503
    data = request.json
    if not data or 'code' not in data: return jsonify({'error': 'Code is required.'}), 400
    try:
        response = model.generate_content(Prompts.CODE_EXPLAINER.format(code=data['code']))
        return jsonify({'explanation': response.text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5001)


