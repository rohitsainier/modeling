

```markdown
# 🏭 AI 3D Model Generator

> Type a prompt → Get a 3D model.** Powered by Ollama (local LLM) + FreeCAD.

Generate 3D CAD models from natural language descriptions using a locally-running AI model. No cloud APIs, no subscriptions — everything runs on your machine.

![Platform](https://img.shields.io/badge/Platform-macOS%20|%20Linux%20|%20Windows-blue)
![Python](https://img.shields.io/badge/Python-3.9+-green)
![License](https://img.shields.io/badge/License-MIT-yellow)
![LLM](https://img.shields.io/badge/LLM-Ollama%20(Local)-purple)
![CAD](https://img.shields.io/badge/CAD-FreeCAD-orange)

---

## 🎬 What It Does

```
You type:  "Create a plate 200x100x10mm with 4 corner holes of 8mm diameter"

AI generates FreeCAD Python code automatically:

    plate = doc.addObject("Part::Box", "Plate")
    plate.Length = 200; plate.Width = 100; plate.Height = 10
    ...

Model appears in FreeCAD → Ready to export as STEP, STL, etc.
```

---

## 📐 Architecture

```
┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│                  │     │                  │     │                  │
│   User Prompt    │────▶│   Ollama LLM     │────▶│   FreeCAD        │
│                  │     │  (Local, Free)   │     │   (3D Engine)    │
│  "Create a gear" │     │                  │     │                  │
│                  │     │  Generates Python │     │  Executes code   │
│                  │     │  code for FreeCAD │     │  Creates 3D model│
│                  │     │                  │     │                  │
└──────────────────┘     └──────────────────┘     └──────────────────┘

                    Three ways to use it:

    ┌─────────────┐   ┌──────────────────┐   ┌─────────────┐
    │  CLI Mode   │   │  FreeCAD Plugin  │   │  Web UI     │
    │  (Terminal) │   │  (Inside FreeCAD)│   │  (Browser)  │
    └─────────────┘   └──────────────────┘   └─────────────┘
```

---

## ✅ Prerequisites

| Requirement | Version | Purpose |
|-------------|---------|---------|
| **Python** | 3.9+ | Runtime |
| **Ollama** | Latest | Local LLM inference |
| **FreeCAD** | 0.21+ | 3D CAD engine |
| **A coding model** | Any | Code generation (see below) |

### Recommended Ollama Models

| Model | Size | Quality | Speed | Command |
|-------|------|---------|-------|---------|
| `qwen2.5-coder:14b` | 9 GB | ⭐⭐⭐⭐⭐ | Medium | `ollama pull qwen2.5-coder:14b` |
| `qwen2.5-coder:7b` | 4.5 GB | ⭐⭐⭐⭐ | Fast | `ollama pull qwen2.5-coder:7b` |
| `deepseek-coder-v2:16b` | 10 GB | ⭐⭐⭐⭐⭐ | Medium | `ollama pull deepseek-coder-v2:16b` |
| `codellama:13b` | 7 GB | ⭐⭐⭐⭐ | Medium | `ollama pull codellama:13b` |
| `codellama:7b` | 4 GB | ⭐⭐⭐ | Fast | `ollama pull codellama:7b` |
| `qwen3-coder` | Cloud | ⭐⭐⭐⭐⭐ | Fast | `ollama pull qwen3-coder:480b-cloud` |

> **Tip:** For complex mechanical parts use 14B+ models. For simple shapes 7B works fine.

---

## 🚀 Installation

### 1. Install Ollama

```bash
# macOS
brew install ollama

# Or download from https://ollama.com

# Linux
curl -fsSL https://ollama.com/install.sh | sh
```

### 2. Pull a Coding Model

```bash
# Start Ollama
ollama serve

# In another terminal, pull a model
ollama pull qwen2.5-coder:7b

# Or if you have more RAM/VRAM
ollama pull qwen2.5-coder:14b
```

### 3. Install FreeCAD

```bash
# macOS
brew install --cask freecad

# Or download from https://www.freecad.org/downloads.php

# Linux (Ubuntu/Debian)
sudo apt install freecad

# Linux (Snap)
sudo snap install freecad
```

### 4. Clone This Project

```bash
git clone https://github.com/yourusername/ai-3d-model-generator.git
cd ai-3d-model-generator
```

### 5. Install Python Dependencies

```bash
# Create virtual environment (recommended)
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

### 6. Install FreeCAD Plugin (Optional — for in-FreeCAD usage)

```bash
# Find your FreeCAD macro folder
# macOS: ~/Library/Application Support/FreeCAD/Macro/
# Linux: ~/.local/share/FreeCAD/Macro/

# Copy the plugin
cp AI_ModelGenerator.FCMacro ~/Library/Application\ Support/FreeCAD/Macro/
```

---

## 📖 Usage

### Method 1: FreeCAD Plugin (Recommended)

The best experience — a GUI dialog right inside FreeCAD.

```bash
# 1. Make sure Ollama is running
ollama serve

# 2. Open FreeCAD
open -a FreeCAD    # macOS
freecad            # Linux

# 3. In FreeCAD: Macro → Macros → AI_ModelGenerator → Execute
```

**What you get:**

```
┌──────────────────────────────────────┐
│ 🏭 AI 3D Model Generator            │
│                                      │
│ ✅ Ollama connected                  │
│                                      │
│ Model: [qwen2.5-coder:14b     ▼] 🔄│
│                                      │
│ Describe your 3D model:             │
│ ┌──────────────────────────────────┐ │
│ │ Create a plate 200x100x10mm    │ │
│ │ with 4 corner bolt holes       │ │
│ └──────────────────────────────────┘ │
│                                      │
│ [📦 Cube] [🔵 Cyl] [🕳️ Plate+Holes]│
│                                      │
│     [🚀 Generate Model]             │
│     [➕ Add Feature]                │
│                                      │
│ Generated Code:                      │
│ ┌──────────────────────────────────┐ │
│ │  1 │ plate = doc.addObject(...)  │ │
│ │  2 │ plate.Length = 200          │ │
│ │  3 │ ...                        │ │
│ └──────────────────────────────────┘ │
│                                      │
│ Log:                                 │
│ ✅ Model created successfully!       │
└──────────────────────────────────────┘
```

**Features:**
- 🚀 One-click model generation
- ➕ Add features to existing models (conversation memory)
- 🔄 Auto-fix: If code fails, LLM tries to fix it automatically
- 📦 Quick prompt buttons for common shapes
- ⌨️ Ctrl+Enter keyboard shortcut
- 🔄 Model selector with refresh

---

### Method 2: Command Line Interface (CLI)

For terminal lovers — generate models and save as macro files.

```bash
# Make sure Ollama is running in another terminal
ollama serve

# Run the CLI
python main_cli.py
```

**Session example:**

```
╔══════════════════════════════════════════════════╗
║   🏭  3D Model Generator                        ║
║   Ollama → FreeCAD                               ║
╚══════════════════════════════════════════════════╝

✅ Ollama ready: qwen2.5-coder:14b
✅ Output: ~/FreeCAD_Generated

🏭 Describe ▶ Create a cube with 50mm sides

🤖 Generating FreeCAD code...

Generated Code:
──────────────────────────────────────────────────
    1 │ cube = doc.addObject("Part::Box", "SimpleCube")
    2 │ cube.Length = 50.0
    3 │ cube.Width = 50.0
    4 │ cube.Height = 50.0
    5 │ cube.Label = "Simple Cube"
    6 │ doc.recompute()
──────────────────────────────────────────────────

══════════════════════════════════════════════════
🎉 MODEL GENERATED!
══════════════════════════════════════════════════

Files:
  📄 Macro:  ~/FreeCAD_Generated/cube_50mm.FCMacro
  📄 Script: ~/FreeCAD_Generated/cube_50mm.py

[1] Open in FreeCAD  [2] Copy code  [3] Continue
```

**CLI Commands:**

| Command | Description |
|---------|-------------|
| `<description>` | Generate a new 3D model |
| `/add <desc>` | Add feature to current model |
| `/code` | Show last generated code |
| `/open` | Open last macro in FreeCAD |
| `/paste` | Show paste-ready code for FreeCAD console |
| `/dir` | Open output folder |
| `/model <name>` | Switch Ollama model |
| `/models` | List available models |
| `/retry` | Retry last prompt |
| `/clear` | Clear conversation history |
| `/help` | Show help |
| `/quit` | Exit |

---

### Method 3: Web UI

Browser-based interface with a modern dark theme.

```bash
# Start the web server
python web_ui.py

# Open in browser
open http://localhost:8000
```

---

## 📁 Project Structure

```
modeling/
│
├── AI_ModelGenerator.FCMacro    # 🎯 FreeCAD plugin (main attraction)
│                                #    Self-contained — no dependencies
│                                #    Uses urllib to talk to Ollama
│                                #    Full GUI with Qt widgets
│
├── main_cli.py                  # 💻 Command-line interface
│                                #    Generates macros + opens FreeCAD
│
├── ollama_generator_mac.py      # 🤖 Ollama code generation engine
│                                #    System prompt with FreeCAD API patterns
│                                #    Code extraction from LLM responses
│                                #    Conversation history management
│
├── code_executor.py             # 🔒 Safe code execution
│                                #    AST-based security validation
│                                #    Blocks dangerous imports/calls
│                                #    Sandboxed namespace
│
├── cad_bridge.py                # 🌉 FreeCAD Python bridge
│                                #    Connects Python to FreeCAD engine
│                                #    Document management
│                                #    Export (FCStd, STEP, STL)
│
├── mcp_server.py                # 🔌 MCP (Model Context Protocol) server
│                                #    For integration with Claude Desktop
│                                #    or other MCP-compatible clients
│
├── mcp_client_example.py        # 📡 Example MCP client
│
├── web_ui.py                    # 🌐 Web interface (FastAPI)
│
├── requirements.txt             # 📦 Python dependencies
│
└── README.md                    # 📖 This file
```

### File Dependency Map

```
AI_ModelGenerator.FCMacro     ← Standalone (no project dependencies)
                                 Uses urllib + Qt (bundled with FreeCAD)

main_cli.py
  ├── ollama_generator_mac.py  ← Uses ollama pip package
  ├── cad_bridge.py            ← FreeCAD Python API
  └── code_executor.py         ← AST validation + safe exec

web_ui.py
  ├── ollama_generator_mac.py
  ├── cad_bridge.py
  └── code_executor.py

mcp_server.py
  ├── ollama_generator_mac.py
  ├── cad_bridge.py
  └── code_executor.py
```

---

## 🧪 Testing

### Test Ollama Connection (no FreeCAD needed)

```bash
python ollama_generator_mac.py
```

Expected output:
```
✅ Model: qwen2.5-coder:14b
GENERATED CODE:
  1 │ cube = doc.addObject("Part::Box", "SimpleCube")
  2 │ cube.Length = 50.0
  ...
✅ Test passed!
```

### Test Code Validator (no FreeCAD needed)

```bash
python code_executor.py
```

Expected output:
```
  ✅ PASS | Valid FreeCAD code (should pass)
  ✅ PASS | Blocked: import os (should block)
  ✅ PASS | Blocked: subprocess (should block)
  ...
  Results: 9/9 passed
```

### Test Inside FreeCAD

Open FreeCAD's Python Console (View → Panels → Python Console) and paste:

```python
import FreeCAD, Part
doc = FreeCAD.newDocument("Test")
box = doc.addObject("Part::Box", "TestBox")
box.Length = 50; box.Width = 50; box.Height = 50
doc.recompute()
```

If a cube appears → FreeCAD is working correctly.

---

## 💡 Example Prompts

### Basic Shapes

```
Create a cube with 50mm sides
Create a cylinder with radius 25mm and height 80mm
Create a sphere with radius 30mm
Make a cone with bottom radius 40mm, top radius 10mm, height 60mm
Create a torus with major radius 50mm and tube radius 10mm
```

### Plates & Brackets

```
Create a rectangular plate 200x100x10mm with 4 corner holes of 8mm diameter, 15mm from edges
Make an L-bracket: vertical plate 100x80x10mm, horizontal base 60mm, with 5mm fillets
Create a T-bracket with mounting holes
Build a flat washer with OD=24mm, ID=13mm, thickness=2.5mm
```

### Mechanical Parts

```
Create a flanged pipe: OD 60mm, ID 50mm, length 150mm, flange diameter 100mm, flange thickness 10mm
Make a simple pulley with 80mm outer diameter, 20mm bore, 15mm wide groove
Create a hex nut shape: M12 (19mm across flats, 10mm thick, 13mm hole)
Build a shaft step: 30mm diameter x 50mm, then 20mm diameter x 40mm
```

### Complex Shapes

```
Create a hollow box: outer 100x80x60mm, wall thickness 5mm, open top
Make a mounting plate with 6 holes arranged in a circle of 60mm diameter
Build a simple heat sink: base plate 80x60x5mm with 6 vertical fins 40mm tall, 2mm thick, spaced 10mm apart
Create a cable clamp: semicircular channel 10mm radius with flat mounting base and 2 screw holes
```

### Modifying Existing Models

After generating a model, use `/add` or the ➕ button:

```
/add Cut a 20mm hole through the center
/add Add 3mm fillets to all edges
/add Add a cylindrical boss 15mm diameter, 20mm tall on the top face
/add Create a slot 40x10mm through the side wall
```

---

## ⚙️ Configuration

### Changing the Ollama Model

**In FreeCAD Plugin:**
Use the model dropdown at the top of the dialog.

**In CLI:**
```
🏭 Describe ▶ /model qwen2.5-coder:14b
```

**In `AI_ModelGenerator.FCMacro`:**
Edit line 21:
```python
OLLAMA_MODEL = "qwen2.5-coder:14b"   # ← Change this
```

**In `ollama_generator_mac.py`:**
Edit the model name in `create_generator()` or `__init__`.

### Changing Ollama URL

If Ollama runs on a different machine or port:

```python
OLLAMA_URL = "http://192.168.1.100:11434"  # Remote machine
```

### Output Directory

CLI saves files to `~/FreeCAD_Generated/` by default.
Change in `main_cli.py`:

```python
OUTPUT_DIR = os.path.expanduser("~/my_custom_folder")
```

---

## 🔒 Security

The code executor includes multiple safety layers:

### Blocked Imports
```
os, sys, subprocess, shutil, socket, http, urllib,
requests, pickle, ctypes, importlib, glob, tempfile...
```

### Blocked Functions
```
exec, eval, compile, __import__, open, exit, quit,
globals, locals, breakpoint, input, setattr, delattr...
```

### AST Validation
Every generated code snippet is parsed into an Abstract Syntax Tree and checked **before execution**. If any dangerous pattern is detected, the code is rejected.

### Sandboxed Namespace
Generated code runs in a controlled namespace with only safe built-ins and FreeCAD objects available.

---

## 🐛 Troubleshooting

### "Cannot connect to Ollama"

```bash
# Check if Ollama is running
curl http://127.0.0.1:11434/api/tags

# If not, start it
ollama serve

# Check if a model is pulled
ollama list
```

### "FreeCAD not found" (macOS)

```bash
# Install FreeCAD
brew install --cask freecad

# Set path (add to ~/.zshrc)
export FREECAD_PATH="/Applications/FreeCAD.app/Contents/Resources/lib"
```

### "Model not found in Ollama"

```bash
# List available models
ollama list

# Pull the model you need
ollama pull qwen2.5-coder:7b
```

### FreeCAD Macro folder not found

```
macOS:   ~/Library/Application Support/FreeCAD/Macro/
Linux:   ~/.local/share/FreeCAD/Macro/
         ~/.FreeCAD/Macro/
Windows: %APPDATA%/FreeCAD/Macro/
```

Or check inside FreeCAD: `Macro → Macros → "User macros location"`

### Generated code doesn't work

1. **Try a different prompt** — be more specific about dimensions
2. **Use a larger model** — `14b` produces better code than `7b`
3. **Enable auto-fix** — the LLM will try to fix its own errors
4. **Use `/retry`** — regenerates with the same prompt
5. **Check FreeCAD console** — View → Panels → Python Console for errors

### "pywin32 not found" error

You're on macOS/Linux. `pywin32` is Windows-only.
This project uses FreeCAD (cross-platform) instead of CATIA (Windows-only).

```bash
# Make sure requirements.txt does NOT contain pywin32
pip install -r requirements.txt
```

---

## 🔌 MCP Integration (Advanced)

This project includes an MCP (Model Context Protocol) server for integration
with Claude Desktop or other MCP-compatible AI clients.

### Claude Desktop Configuration

Add to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "3d-model-generator": {
      "command": "python",
      "args": ["/path/to/modeling/mcp_server.py"],
      "env": {
        "OLLAMA_HOST": "http://localhost:11434"
      }
    }
  }
}
```

### Available MCP Tools

| Tool | Description |
|------|-------------|
| `create_3d_model` | Generate a complete 3D model from description |
| `add_feature` | Add feature to existing model |
| `execute_catia_code` | Run raw FreeCAD Python code |
| `save_current_model` | Save model to file |
| `new_part` | Create new empty document |
| `get_model_info` | Get info about current model |

---

## 🗺️ Roadmap

- [x] Ollama code generation with system prompt
- [x] FreeCAD Python execution
- [x] CLI interface
- [x] FreeCAD GUI plugin
- [x] Auto-fix (LLM self-corrects errors)
- [x] Conversation memory (add features iteratively)
- [x] Code safety validation
- [x] MCP server
- [ ] STEP/STL auto-export
- [ ] Model preview thumbnails
- [ ] Part library (save & reuse generated parts)
- [ ] Parametric modifications ("make it 20% bigger")
- [ ] Assembly support (multiple parts)
- [ ] FreeCAD Workbench (permanent toolbar button)
- [ ] Voice input ("Hey, make me a bracket")
- [ ] Integration with PartDesign (sketches + constraints)

---

## 🤝 Contributing

Contributions are welcome! Areas where help is needed:

1. **Better system prompts** — More FreeCAD API patterns improve generation quality
2. **FreeCAD Workbench** — Convert the macro into a proper installable workbench
3. **More export formats** — IGES, OBJ, 3MF support
4. **Testing** — More test cases for the code validator
5. **Windows/Linux testing** — Currently developed on macOS

### Development Setup

```bash
git clone https://github.com/yourusername/ai-3d-model-generator.git
cd ai-3d-model-generator
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# Run tests
python code_executor.py          # Validator tests
python ollama_generator_mac.py   # Ollama connection test
```

---

## 📄 License

MIT License — use it however you want.

---

## 🙏 Acknowledgments

- **[Ollama](https://ollama.com)** — Simple local LLM inference
- **[FreeCAD](https://www.freecad.org)** — Open-source parametric 3D CAD
- **[Qwen2.5-Coder](https://huggingface.co/Qwen)** — Excellent coding LLM
- **[MCP](https://modelcontextprotocol.io)** — Model Context Protocol by Anthropic

---

<p align="center">
  <b>Built with 🤖 AI + ❤️ for makers, engineers, and tinkerers</b>
  <br>
  <i>Turn your words into 3D reality</i>
</p>
```

Save this as `README.md` in your project root:

```bash
# Save it
cd ~/Documents/Robot/modeling
# (paste the content into README.md)

# Verify your project structure
ls -la
```

Your final structure:

```
modeling/
├── AI_ModelGenerator.FCMacro     ← FreeCAD plugin
├── cad_bridge.py
├── code_executor.py
├── main_cli.py
├── mcp_client_example.py
├── mcp_server.py
├── ollama_generator_mac.py
├── README.md                     ← This file
├── requirements.txt
└── web_ui.py
```