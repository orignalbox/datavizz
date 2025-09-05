import os
import subprocess
import uuid
import logging
from flask import Flask, request, jsonify, render_template, send_file
from flask_cors import CORS
import google.generativeai as genai
import io

# --- Configuration ---
logging.basicConfig(level=logging.INFO)
# It's recommended to set the API key as an environment variable for security
# For Render deployment, this will be set in the service's environment settings.
# For local testing, you can set it in your shell: export GOOGLE_API_KEY='your_key'
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    logging.warning("GOOGLE_API_KEY environment variable not set. API calls will fail.")
else:
    genai.configure(api_key=GOOGLE_API_KEY)

# --- Flask App Initialization ---
app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

# --- Gemini Model Configuration ---
# Upgraded to a more powerful model to handle complex chained prompts better.
generation_config = {
    "temperature": 0.7,
    "top_p": 1,
    "top_k": 1,
    "max_output_tokens": 8192,
}
safety_settings = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
]
model = genai.GenerativeModel(
    model_name="gemini-2.5-pro", # Using the more advanced model
    generation_config=generation_config,
    safety_settings=safety_settings
)

# --- System Prompts for Multi-Step Generation (Refined for Clarity) ---
PROMPT_ENHANCER_SYSTEM = """
You are a creative assistant for a data visualization expert.
Your task is to take a user's simple idea and expand it into a detailed, scene-by-scene concept for a short Manim animation.
Describe camera movements, object animations (like FadeIn, GrowFromCenter, Transform), and the overall narrative flow.
Be descriptive and imaginative. Output only the detailed concept.
"""

PROMPT_DESIGNER_SYSTEM = """
You are a senior UI/UX and motion graphics designer.
You will be given a detailed animation concept. Your job is to define a complete visual theme.
Structure your output into three distinct sections: 'Color Palette' (with hex codes), 'Typography' (suggesting modern font styles), and 'Overall Aesthetic' (e.g., 'minimalist', 'futuristic').
Output only these design specifications.
"""

PROMPT_PROGRAMMER_SYSTEM = """
You are an expert Manim programmer. You will receive a detailed animation concept and design specifications.
Your task is to write a single, complete, and executable Python script using the Manim library.
The script must define a single Manim scene class inheriting from `Scene` that generates the described animation.
Incorporate the specified colors, fonts, and aesthetic.
Only output the raw Python code. Do not wrap it in markdown fences (```python) or add any explanations.
"""

# --- Helper Functions ---
def run_manim(manim_code: str, quality: str) -> (bool, str, str):
    """
    Saves Manim code to a file and runs the Manim process to render the video.
    Returns the success status, the output video path, and any error messages.
    """
    unique_id = uuid.uuid4()
    # Using /tmp ensures files are written to a temporary, in-memory filesystem in many cloud environments
    script_path = f"/tmp/generated_scene_{unique_id}.py"
    
    with open(script_path, "w") as f:
        f.write(manim_code)

    output_filename = f"video_{unique_id}.mp4"
    output_path = f"/tmp/{output_filename}"
    
    quality_flag = {
        "1080p": "--quality h", # High quality
        "720p": "--quality m", # Medium quality
        "480p": "--quality l"  # Low quality
    }.get(quality, "--quality l") # Default to low quality

    command = [
        "manim",
        script_path,
        "-o", output_filename,
        "--media_dir", "/tmp",
        *quality_flag.split(), # Splits "--quality l" into two arguments
        "--format", "mp4",
        "--progress_bar", "none",
        "--quiet" # Correct flag to suppress non-error output
    ]

    try:
        logging.info(f"Running Manim command: {' '.join(command)}")
        # Increased timeout to handle potentially long renders
        process = subprocess.run(command, capture_output=True, text=True, check=True, timeout=300)
        logging.info("Manim process completed successfully.")
        logging.info(f"Manim stdout: {process.stdout}")
        return True, output_path, None
    except subprocess.CalledProcessError as e:
        error_message = f"Manim rendering failed.\nExit Code: {e.returncode}\nStdout: {e.stdout}\nStderr: {e.stderr}"
        logging.error(error_message)
        return False, None, error_message
    except subprocess.TimeoutExpired as e:
        error_message = f"Manim rendering timed out.\nStdout: {e.stdout}\nStderr: {e.stderr}"
        logging.error(error_message)
        return False, None, "Rendering process took too long and was terminated."
    except Exception as e:
        error_message = f"An unexpected error occurred during Manim execution: {e}"
        logging.error(error_message)
        return False, None, error_message

# --- API Routes ---
@app.route('/')
def index():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/generate', methods=['POST'])
def generate_animation():
    """
    The main endpoint to generate an animation.
    It takes a user prompt and returns the video file directly.
    """
    if not GOOGLE_API_KEY:
        return jsonify({"error": "Server is not configured with a Google API key."}), 500

    data = request.json
    user_prompt = data.get('prompt')
    orientation = data.get('orientation', 'landscape')
    quality = data.get('quality', '720p')

    if not user_prompt:
        return jsonify({"error": "Prompt is required."}), 400

    try:
        # Step 1: Enhance the prompt
        logging.info("Step 1: Enhancing prompt...")
        enhancer_prompt = f"{PROMPT_ENHANCER_SYSTEM}\n\nUser Idea: {user_prompt}"
        enhanced_concept_response = model.generate_content(enhancer_prompt)
        enhanced_concept = enhanced_concept_response.text
        logging.info(f"Enhanced Concept: {enhanced_concept[:200]}...")

        # Step 2: Design the visual theme
        logging.info("Step 2: Designing theme...")
        designer_prompt = f"{PROMPT_DESIGNER_SYSTEM}\n\nAnimation Concept: {enhanced_concept}"
        design_specs_response = model.generate_content(designer_prompt)
        design_specs = design_specs_response.text
        logging.info(f"Design Specs: {design_specs[:200]}...")

        # Step 3: Generate the Manim code
        logging.info("Step 3: Generating Manim code...")
        programmer_prompt = (
            f"{PROMPT_PROGRAMMER_SYSTEM}\n\n"
            f"Animation Concept:\n{enhanced_concept}\n\n"
            f"Design Specifications:\n{design_specs}\n\n"
            f"Additional Requirements:\n- The final video orientation must be {orientation}."
        )
        manim_code_response = model.generate_content(programmer_prompt)
        manim_code = manim_code_response.text
        logging.info("Manim code generated.")

        # Step 4: Run Manim to render the video
        logging.info("Step 4: Rendering video with Manim...")
        success, video_path, error = run_manim(manim_code, quality)

        if not success:
            return jsonify({"error": "Manim rendering failed.", "details": error}), 500
        
        # Step 5: Send the video file from memory
        logging.info(f"Video rendered successfully at {video_path}. Sending file to client.")

        with open(video_path, 'rb') as f:
            video_buffer = io.BytesIO(f.read())
        
        # Clean up the temporary files to save space
        os.remove(video_path)
        script_file_to_remove = video_path.replace(".mp4",".py").replace("video_","generated_scene_")
        if os.path.exists(script_file_to_remove):
             os.remove(script_file_to_remove)

        video_buffer.seek(0)

        return send_file(
            video_buffer,
            mimetype='video/mp4',
            as_attachment=False,
            download_name='animation.mp4'
        )

    except Exception as e:
        # This will catch errors from the API calls if they are blocked
        logging.error(f"An error occurred in the generation pipeline: {e}")
        # Check if it's a blocked prompt error and provide a user-friendly message
        if "response.text" in str(e):
             return jsonify({"error": "The AI model blocked the request due to safety concerns. Please try a different prompt."}), 500
        return jsonify({"error": "An unexpected server error occurred."}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get("PORT", 8080)))


