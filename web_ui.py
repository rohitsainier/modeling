# web_ui.py
"""
Optional web interface for the CATIA 3D model generator.
Provides a browser-based UI as an alternative to the CLI.
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
import uvicorn
import json
import logging

from catia_bridge import get_bridge
from ollama_generator import create_generator
from code_executor import CodeExecutor

app = FastAPI(title="CATIA 3D Model Generator")
logger = logging.getLogger("WebUI")

# Initialize on startup
bridge = None
generator = None
executor = None


class ModelRequest(BaseModel):
    prompt: str
    create_new_part: bool = True
    part_name: str = "AI_Generated"


class CodeRequest(BaseModel):
    code: str


@app.on_event("startup")
async def startup():
    global bridge, generator, executor
    bridge = get_bridge()
    bridge.connect()
    generator = create_generator("qwen2.5-coder:14b")
    executor = CodeExecutor(bridge)
    logger.info("Web UI initialized")


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>CATIA 3D Model Generator</title>
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', system-ui, sans-serif;
                background: #0f172a;
                color: #e2e8f0;
                min-height: 100vh;
            }
            .container {
                max-width: 900px;
                margin: 0 auto;
                padding: 2rem;
            }
            h1 {
                text-align: center;
                font-size: 2rem;
                margin-bottom: 0.5rem;
                background: linear-gradient(135deg, #60a5fa, #a78bfa);
                -webkit-background-clip: text;
                -webkit-text-fill-color: transparent;
            }
            .subtitle {
                text-align: center;
                color: #94a3b8;
                margin-bottom: 2rem;
            }
            .input-section {
                background: #1e293b;
                border-radius: 12px;
                padding: 1.5rem;
                margin-bottom: 1.5rem;
            }
            textarea {
                width: 100%;
                min-height: 100px;
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 8px;
                color: #e2e8f0;
                padding: 1rem;
                font-size: 1rem;
                resize: vertical;
                font-family: inherit;
            }
            textarea:focus {
                outline: none;
                border-color: #60a5fa;
            }
            .btn {
                display: inline-block;
                padding: 0.75rem 1.5rem;
                border: none;
                border-radius: 8px;
                font-size: 1rem;
                font-weight: 600;
                cursor: pointer;
                margin-top: 1rem;
                margin-right: 0.5rem;
                transition: all 0.2s;
            }
            .btn-primary {
                background: linear-gradient(135deg, #3b82f6, #8b5cf6);
                color: white;
            }
            .btn-primary:hover { transform: translateY(-1px); opacity: 0.9; }
            .btn-secondary {
                background: #334155;
                color: #e2e8f0;
            }
            .result-section {
                background: #1e293b;
                border-radius: 12px;
                padding: 1.5rem;
                display: none;
            }
            .result-section.active { display: block; }
            .code-block {
                background: #0f172a;
                border-radius: 8px;
                padding: 1rem;
                overflow-x: auto;
                font-family: 'Fira Code', 'Consolas', monospace;
                font-size: 0.9rem;
                line-height: 1.5;
                margin: 1rem 0;
                border: 1px solid #334155;
            }
            .status {
                padding: 0.5rem 1rem;
                border-radius: 6px;
                margin: 0.5rem 0;
                font-weight: 600;
            }
            .status.success { background: #065f46; color: #6ee7b7; }
            .status.error { background: #7f1d1d; color: #fca5a5; }
            .status.loading { background: #1e3a5f; color: #93c5fd; }
            .examples {
                display: grid;
                grid-template-columns: 1fr 1fr;
                gap: 0.5rem;
                margin-top: 1rem;
            }
            .example-btn {
                background: #0f172a;
                border: 1px solid #334155;
                border-radius: 6px;
                padding: 0.5rem;
                color: #94a3b8;
                cursor: pointer;
                font-size: 0.85rem;
                text-align: left;
                transition: all 0.2s;
            }
            .example-btn:hover {
                border-color: #60a5fa;
                color: #e2e8f0;
            }
            .spinner {
                display: inline-block;
                width: 20px;
                height: 20px;
                border: 2px solid #334155;
                border-top: 2px solid #60a5fa;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                margin-right: 0.5rem;
                vertical-align: middle;
            }
            @keyframes spin { to { transform: rotate(360deg); } }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🏭 CATIA 3D Model Generator</h1>
            <p class="subtitle">Describe a 3D model → AI generates it in CATIA</p>
            
            <div class="input-section">
                <textarea id="prompt" placeholder="Describe the 3D model you want to create...&#10;&#10;Example: Create a flanged pipe with outer diameter 60mm, inner diameter 50mm, length 150mm, with a 100mm diameter flange at one end that is 10mm thick with 4 bolt holes of 12mm diameter on a 80mm bolt circle."></textarea>
                <div>
                    <button class="btn btn-primary" onclick="generateModel()">
                        🚀 Generate 3D Model
                    </button>
                    <button class="btn btn-secondary" onclick="addFeature()">
                        ➕ Add Feature
                    </button>
                    <button class="btn btn-secondary" onclick="newPart()">
                        📄 New Part
                    </button>
                </div>
                
                <div class="examples">
                    <button class="example-btn" onclick="setPrompt('Create a cube with 50mm sides')">
                        📦 Simple Cube (50mm)
                    </button>
                    <button class="example-btn" onclick="setPrompt('Create a cylinder with radius 25mm and height 80mm')">
                        🔵 Cylinder (R25, H80)
                    </button>
                    <button class="example-btn" onclick="setPrompt('Create a plate 200x100x10mm with a centered 30mm through-hole')">
                        🕳️ Plate with Hole
                    </button>
                    <button class="example-btn" onclick="setPrompt('Create an L-bracket: 100x80x10mm vertical, 60mm horizontal base, 5mm fillets')">
                        📐 L-Bracket with Fillets
                    </button>
                </div>
            </div>
            
            <div class="result-section" id="results">
                <div id="status"></div>
                <h3 style="margin: 1rem 0 0.5rem">Generated Code:</h3>
                <div class="code-block" id="codeOutput"></div>
            </div>
        </div>
        
        <script>
            function setPrompt(text) {
                document.getElementById('prompt').value = text;
            }
            
            async function generateModel() {
                const prompt = document.getElementById('prompt').value;
                if (!prompt) return;
                
                const results = document.getElementById('results');
                const status = document.getElementById('status');
                const codeOut = document.getElementById('codeOutput');
                
                results.classList.add('active');
                status.className = 'status loading';
                status.innerHTML = '<span class="spinner"></span> Generating code with Ollama...';
                codeOut.textContent = '';
                
                try {
                    const resp = await fetch('/api/generate', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({prompt, create_new_part: true})
                    });
                    const data = await resp.json();
                    
                    if (data.success) {
                        status.className = 'status success';
                        status.textContent = '✅ ' + data.message;
                    } else {
                        status.className = 'status error';
                        status.textContent = '❌ ' + data.message;
                    }
                    codeOut.textContent = data.generated_code || '';
                } catch(e) {
                    status.className = 'status error';
                    status.textContent = '❌ Connection error: ' + e.message;
                }
            }
            
            async function addFeature() {
                const prompt = document.getElementById('prompt').value;
                if (!prompt) return;
                
                const results = document.getElementById('results');
                const status = document.getElementById('status');
                const codeOut = document.getElementById('codeOutput');
                
                results.classList.add('active');
                status.className = 'status loading';
                status.innerHTML = '<span class="spinner"></span> Adding feature...';
                
                try {
                    const resp = await fetch('/api/add-feature', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({prompt})
                    });
                    const data = await resp.json();
                    
                    status.className = data.success ? 'status success' : 'status error';
                    status.textContent = (data.success ? '✅ ' : '❌ ') + data.message;
                    codeOut.textContent = data.generated_code || '';
                } catch(e) {
                    status.className = 'status error';
                    status.textContent = '❌ ' + e.message;
                }
            }
            
            async function newPart() {
                const name = prompt('Part name:', 'NewPart');
                if (!name) return;
                await fetch('/api/new-part', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({name})
                });
            }
            
            // Enter key handler
            document.getElementById('prompt').addEventListener('keydown', (e) => {
                if (e.ctrlKey && e.key === 'Enter') generateModel();
            });
        </script>
    </body>
    </html>
    """


@app.post("/api/generate")
async def generate_model(request: ModelRequest):
    try:
        if request.create_new_part:
            bridge.create_new_part(request.part_name)
        
        code = generator.generate_code(request.prompt)
        success, message, error = executor.execute(code)
        
        result = {
            "success": success,
            "message": message,
            "generated_code": code,
        }
        
        if not success and error:
            fixed = generator.refine_code(code, error)
            s2, m2, e2 = executor.execute(fixed)
            result["auto_fix"] = {"success": s2, "message": m2, "code": fixed}
        
        return result
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/add-feature")
async def add_feature(request: ModelRequest):
    try:
        code = generator.generate_code(f"Add to existing part: {request.prompt}")
        success, message, error = executor.execute(code)
        return {"success": success, "message": message, "generated_code": code}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/new-part")
async def new_part(request: dict):
    name = request.get("name", "NewPart")
    bridge.create_new_part(name)
    return {"success": True, "message": f"Created: {name}"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)