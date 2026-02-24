# ollama_generator.py
"""
Uses Ollama to generate CATIA V5 automation Python code from natural language prompts.
Handles model verification, code extraction, conversation history, and error recovery.
"""

import re
import json
import logging
import time
from typing import Optional, List, Dict, Any

try:
    import ollama
except ImportError:
    raise ImportError(
        "ollama package not installed. Run: pip install ollama"
    )

logger = logging.getLogger("OllamaGenerator")

# ═══════════════════════════════════════════════════════════════════
# CATIA V5 SYSTEM PROMPT — This is the "brain" that teaches the LLM
# ═══════════════════════════════════════════════════════════════════

CATIA_SYSTEM_PROMPT = r"""You are an expert CATIA V5 automation engineer. You write Python code that controls CATIA V5 through its COM/Automation API using pywin32.

## CRITICAL RULES:
1. Output ONLY a single Python code block. No explanations before or after.
2. Do NOT import win32com, pythoncom, or connect to CATIA — it is already done.
3. Do NOT redefine any of the pre-defined variables listed below.
4. Always call `update()` at the very end of your code.
5. All measurements are in **millimeters (mm)**.
6. Angles are in **degrees**.
7. Wrap risky operations in try/except when appropriate.
8. Give every feature a meaningful `.Name` property.
9. The code must be complete and runnable as-is within the provided context.
10. Use only the variables and helpers listed below.

## PRE-DEFINED VARIABLES (already exist — do NOT create them):

| Variable | Type | Description |
|---|---|---|
| `catia` | Application | The CATIA Application COM object |
| `part_document` | PartDocument | The active part document |
| `part` | Part | The Part object inside the document |
| `sf` | ShapeFactory | For solid features (Pad, Pocket, Shaft, Groove, Fillet, Chamfer) |
| `hsf` | HybridShapeFactory | For wireframe/surface geometry (points, lines, planes) |
| `origin_planes` | dict | `{"xy": PlaneXY, "yz": PlaneYZ, "zx": PlaneZX}` |
| `bodies` | Bodies collection | `part.Bodies` |
| `main_body` | Body | `part.Bodies.Item(1)` — the main (first) body |
| `create_sketch(plane)` | function | Creates a Sketch on `"xy"`, `"yz"`, or `"zx"` plane |
| `update()` | function | Rebuilds / updates the part |
| `create_reference(obj)` | function | Shortcut for `part.CreateReferenceFromObject(obj)` |

## CATIA V5 AUTOMATION PATTERNS:

### Pattern 1 — Pad (extruded solid from a sketch):
```python
# Step 1: Create sketch on a plane
sketch1 = create_sketch("xy")
factory2D = sketch1.OpenEdition()

# Step 2: Draw closed 2D geometry
# Rectangle (4 lines forming a closed loop):
line1 = factory2D.CreateLine(-50.0, -25.0, 50.0, -25.0)
line2 = factory2D.CreateLine(50.0, -25.0, 50.0, 25.0)
line3 = factory2D.CreateLine(50.0, 25.0, -50.0, 25.0)
line4 = factory2D.CreateLine(-50.0, 25.0, -50.0, -25.0)

# OR a circle:
# circle1 = factory2D.CreateClosedCircle(0.0, 0.0, 25.0)

# Step 3: Close sketch edition
sketch1.CloseEdition()

# Step 4: Create Pad from sketch
pad1 = sf.AddNewPad(sketch1, 50.0)   # 50mm height
pad1.Name = "BasePad"

# Step 5: Update
update()
Pattern 2 — Pocket (cut / hole through solid):
Python

sketch2 = create_sketch("xy")
f2d = sketch2.OpenEdition()
circle = f2d.CreateClosedCircle(0.0, 0.0, 10.0)   # radius 10mm
sketch2.CloseEdition()

pocket1 = sf.AddNewPocket(sketch2, 20.0)   # depth 20mm
pocket1.Name = "CenterHole"
# For through-all:  pocket1.DirectionType = 1
update()
Pattern 3 — Pocket as a through-all cut:
Python

sketch_hole = create_sketch("xy")
f2d_hole = sketch_hole.OpenEdition()
f2d_hole.CreateClosedCircle(30.0, 0.0, 5.0)
sketch_hole.CloseEdition()

pocket_through = sf.AddNewPocket(sketch_hole, 1.0)
pocket_through.DirectionType = 1   # catUpToLast — goes all the way through
pocket_through.Name = "ThroughHole"
update()
Pattern 4 — Multiple holes using a loop:
Python

import math

hole_positions = [
    (40.0, 0.0),
    (0.0, 40.0),
    (-40.0, 0.0),
    (0.0, -40.0),
]

for i, (hx, hy) in enumerate(hole_positions):
    sk = create_sketch("xy")
    f = sk.OpenEdition()
    f.CreateClosedCircle(hx, hy, 5.0)
    sk.CloseEdition()
    p = sf.AddNewPocket(sk, 1.0)
    p.DirectionType = 1
    p.Name = "BoltHole_" + str(i + 1)

update()
Pattern 5 — Shaft (solid of revolution):
Python

sketch_rev = create_sketch("yz")
f2d_rev = sketch_rev.OpenEdition()

# Draw a closed profile on one side of the axis
# Profile for a simple cylinder via revolution
f2d_rev.CreateLine(0.0, 0.0, 20.0, 0.0)    # bottom radius line
f2d_rev.CreateLine(20.0, 0.0, 20.0, 50.0)  # side
f2d_rev.CreateLine(20.0, 50.0, 0.0, 50.0)  # top radius line
f2d_rev.CreateLine(0.0, 50.0, 0.0, 0.0)    # axis (center line)

sketch_rev.CloseEdition()

shaft1 = sf.AddNewShaft(sketch_rev)
shaft1.Name = "RevolvedBody"
update()
Pattern 6 — Fillet (round edges):
Python

# After creating a Pad named pad1:
# Fillet all edges of pad1
ref_pad = create_reference(pad1)
fillet1 = sf.AddNewSolidEdgeFilletWithConstantRadius(ref_pad, 1, 3.0)  # 3mm radius
fillet1.Name = "EdgeFillet"
update()
Pattern 7 — Chamfer:
Python

ref_for_chamfer = create_reference(pad1)
chamfer1 = sf.AddNewSolidChamferWithConstantLength(ref_for_chamfer, 1, 2.0, 45.0)
chamfer1.Name = "Chamfer_45deg"
update()
Pattern 8 — Creating a second body and adding geometry:
Python

new_body = bodies.Add()
new_body.Name = "SecondBody"
part.InWorkObject = new_body

# Now sketches/pads created go into new_body
sk_new = create_sketch("xy")
f_new = sk_new.OpenEdition()
f_new.CreateClosedCircle(0.0, 0.0, 15.0)
sk_new.CloseEdition()
pad_new = sf.AddNewPad(sk_new, 30.0)
pad_new.Name = "CylinderInBody2"

# Switch back to main body if needed
part.InWorkObject = main_body
update()
IMPORTANT NOTES:
factory2D.CreateLine(x1, y1, x2, y2) — all floats
factory2D.CreateClosedCircle(cx, cy, radius) — all floats
Always make geometry CLOSED (loops must connect end-to-end for pads/pockets)
Sketch must be closed with sketch.CloseEdition() before creating features
Use sf.AddNewPad(sketch, height) NOT sf.AddNewPad(sketch_reference, height)
update() must be the LAST call
Do NOT call part.Update() directly — use the update() helper
"""
class OllamaGenerator:
    """
    Generates CATIA V5 automation Python code using a local Ollama LLM.

    text

    Workflow:
        1. User provides natural language prompt
        2. System prompt teaches the LLM the CATIA COM API
        3. LLM generates executable Python code
        4. Code is extracted from markdown fences
        5. Conversation history is maintained for follow-up requests
    """

def __init__(self, model: str = "qwen2.5-coder:14b"):
    """
    Initialize the generator with a specific Ollama model.

    Args:
        model: Ollama model name (e.g., "qwen2.5-coder:14b",
               "deepseek-coder:6.7b", "codellama:13b")
    """
    self.model = model
    self.conversation_history: List[Dict[str, str]] = []
    self.last_raw_response: str = ""
    self.last_generated_code: str = ""
    self.generation_count: int = 0
    self._verify_model()

# ──────────────────────────────────────────────
# Model Management
# ──────────────────────────────────────────────

def _verify_model(self) -> None:
    """Check that the requested model exists in Ollama. Pull if missing."""
    try:
        response = ollama.list()
        
        # Handle different response formats from ollama package versions
        if hasattr(response, "models"):
            available = [m.model for m in response.models]
        elif isinstance(response, dict) and "models" in response:
            available = [
                m.get("model", m.get("name", ""))
                for m in response["models"]
            ]
        else:
            available = []

        # Check if our model (or its base name) is available
        base_name = self.model.split(":")[0]
        found = any(
            self.model in name or base_name in name
            for name in available
        )

        if found:
            logger.info(f"✅ Ollama model ready: {self.model}")
        else:
            logger.warning(
                f"Model '{self.model}' not found locally. "
                f"Available: {available}"
            )
            logger.info(f"⏬ Pulling model '{self.model}' (this may take a while)...")
            ollama.pull(self.model)
            logger.info(f"✅ Model '{self.model}' pulled successfully.")

    except ConnectionError:
        raise ConnectionError(
            "Cannot connect to Ollama. "
            "Make sure Ollama is running: `ollama serve`"
        )
    except Exception as e:
        logger.error(f"Ollama verification error: {e}")
        raise RuntimeError(
            f"Failed to verify Ollama model '{self.model}': {e}\n"
            f"Make sure Ollama is installed and running."
        )

def switch_model(self, new_model: str) -> None:
    """Switch to a different Ollama model."""
    old_model = self.model
    self.model = new_model
    try:
        self._verify_model()
        logger.info(f"Switched model: {old_model} → {new_model}")
    except Exception:
        self.model = old_model
        raise

def get_available_models(self) -> List[str]:
    """List all models available in Ollama."""
    try:
        response = ollama.list()
        if hasattr(response, "models"):
            return [m.model for m in response.models]
        elif isinstance(response, dict) and "models" in response:
            return [
                m.get("model", m.get("name", ""))
                for m in response["models"]
            ]
        return []
    except Exception as e:
        logger.error(f"Failed to list models: {e}")
        return []

# ──────────────────────────────────────────────
# Code Generation
# ──────────────────────────────────────────────

def generate_code(self, user_prompt: str) -> str:
    """
    Generate CATIA V5 automation Python code from a natural language prompt.

    Args:
        user_prompt: What the user wants to build (e.g.,
                     "Create a cylinder with radius 30mm and height 100mm")

    Returns:
        Clean Python code string ready for execution in the CATIA context.

    Raises:
        RuntimeError: If Ollama fails to generate a response.
    """
    # Build the messages list
    messages = self._build_messages(user_prompt)

    logger.info(
        f"🤖 Generating code for: "
        f"{user_prompt[:80]}{'...' if len(user_prompt) > 80 else ''}"
    )
    logger.info(f"   Model: {self.model}")

    start_time = time.time()

    try:
        response = ollama.chat(
            model=self.model,
            messages=messages,
            options={
                "temperature": 0.15,       # Low = more deterministic code
                "top_p": 0.9,
                "num_predict": 4096,        # Max tokens to generate
                "repeat_penalty": 1.1,
                "stop": ["```\n\n", "---"],  # Stop sequences
            },
        )
    except Exception as e:
        raise RuntimeError(
            f"Ollama generation failed: {e}\n"
            f"Is Ollama running? Try: ollama serve"
        )

    elapsed = time.time() - start_time

    # Extract the response text
    if hasattr(response, "message"):
        raw_text = response.message.content
    elif isinstance(response, dict):
        raw_text = response.get("message", {}).get("content", "")
    else:
        raw_text = str(response)

    self.last_raw_response = raw_text

    # Extract clean Python code from the response
    code = self._extract_code(raw_text)

    # Post-process the code
    code = self._postprocess_code(code)

    self.last_generated_code = code
    self.generation_count += 1

    # Update conversation history
    self.conversation_history.append({
        "role": "user",
        "content": user_prompt,
    })
    self.conversation_history.append({
        "role": "assistant",
        "content": raw_text,
    })

    # Keep history manageable (last 10 exchanges = 20 messages)
    max_history = 20
    if len(self.conversation_history) > max_history:
        self.conversation_history = self.conversation_history[-max_history:]

    logger.info(
        f"✅ Code generated: {len(code)} chars, "
        f"{code.count(chr(10)) + 1} lines, "
        f"{elapsed:.1f}s"
    )

    return code

def refine_code(self, original_code: str, error_message: str) -> str:
    """
    Ask the LLM to fix code that produced a runtime error.

    Args:
        original_code: The code that failed.
        error_message: The error/traceback string.

    Returns:
        Corrected Python code string.
    """
    fix_prompt = (
        f"The following CATIA V5 automation code produced an error. "
        f"Please fix it and return the COMPLETE corrected code.\n\n"
        f"## ORIGINAL CODE:\n"
        f"```python\n{original_code}\n```\n\n"
        f"## ERROR MESSAGE:\n"
        f"```\n{error_message}\n```\n\n"
        f"Return ONLY the fixed Python code in a single code block. "
        f"Make sure to fix the root cause, not just suppress the error."
    )

    logger.info("🔄 Requesting code fix from Ollama...")
    return self.generate_code(fix_prompt)

def modify_existing(self, modification_prompt: str) -> str:
    """
    Generate code to modify/add features to an already-existing part.
    Adds context so the LLM knows a part already exists.

    Args:
        modification_prompt: What to add or change.

    Returns:
        Python code that modifies the current part.
    """
    enhanced_prompt = (
        f"A part already exists in CATIA with some features. "
        f"Do NOT create a new sketch for the base shape — it already exists. "
        f"Only add the following modification to the EXISTING part:\n\n"
        f"{modification_prompt}\n\n"
        f"The variables `part`, `sf`, `hsf`, `main_body`, etc. are already "
        f"pointing to the active part."
    )
    return self.generate_code(enhanced_prompt)

# ──────────────────────────────────────────────
# Internal Helpers
# ──────────────────────────────────────────────

def _build_messages(self, user_prompt: str) -> List[Dict[str, str]]:
    """Build the full message list for the Ollama API call."""
    messages = [
        {"role": "system", "content": CATIA_SYSTEM_PROMPT},
    ]

    # Add conversation history for context continuity
    messages.extend(self.conversation_history)

    # Add the current user request
    messages.append({
        "role": "user",
        "content": (
            f"Generate CATIA V5 Python automation code for:\n\n"
            f"{user_prompt}\n\n"
            f"Output ONLY a Python code block. No explanations."
        ),
    })

    return messages

def _extract_code(self, response_text: str) -> str:
    """
    Extract Python code from the LLM response.
    Handles multiple formats: ```python```, ````, or raw code.
    """
    if not response_text or not response_text.strip():
        logger.warning("Empty response from LLM")
        return "# Empty response from LLM — try rephrasing your prompt\nupdate()"

    text = response_text.strip()

    # ── Strategy 1: Find ```python ... ``` blocks ──
    pattern_python = r"```python\s*\n(.*?)```"
    matches = re.findall(pattern_python, text, re.DOTALL)
    if matches:
        # If multiple blocks, join them (some LLMs split code into blocks)
        code = "\n\n".join(m.strip() for m in matches)
        logger.debug("Extracted code from ```python``` block(s)")
        return code

    # ── Strategy 2: Find generic ``` ... ``` blocks ──
    pattern_generic = r"```\s*\n(.*?)```"
    matches = re.findall(pattern_generic, text, re.DOTALL)
    if matches:
        code = "\n\n".join(m.strip() for m in matches)
        logger.debug("Extracted code from generic ``` block(s)")
        return code

    # ── Strategy 3: Find ``` on same line as python ──
    pattern_inline = r"```python(.*?)```"
    matches = re.findall(pattern_inline, text, re.DOTALL)
    if matches:
        code = "\n\n".join(m.strip() for m in matches)
        logger.debug("Extracted code from inline ```python block")
        return code

    # ── Strategy 4: Entire response is code (no fences) ──
    # Remove obvious non-code lines at the beginning/end
    lines = text.split("\n")
    code_lines = []
    in_code = False

    for line in lines:
        stripped = line.strip()

        # Skip empty lines at the start
        if not in_code and not stripped:
            continue

        # Detect start of code
        if not in_code:
            if self._looks_like_code(stripped):
                in_code = True
                code_lines.append(line)
            # else skip non-code preamble
        else:
            code_lines.append(line)

    if code_lines:
        # Remove trailing non-code lines
        while code_lines and not self._looks_like_code(
            code_lines[-1].strip()
        ):
            removed = code_lines.pop()
            if removed.strip():  # If we removed actual content, put it back
                if any(
                    kw in removed
                    for kw in ["update", "part", "sf.", "hsf."]
                ):
                    code_lines.append(removed)
                    break

        code = "\n".join(code_lines)
        logger.debug("Extracted code from raw response (no fences)")
        return code

    # ── Fallback: return everything ──
    logger.warning("Could not extract code — returning full response")
    return text

def _looks_like_code(self, line: str) -> bool:
    """Heuristic: does this line look like Python code?"""
    if not line:
        return False

    code_indicators = [
        line.startswith("#"),
        line.startswith("import "),
        line.startswith("from "),
        line.startswith("def "),
        line.startswith("class "),
        line.startswith("for "),
        line.startswith("while "),
        line.startswith("if "),
        line.startswith("elif "),
        line.startswith("else:"),
        line.startswith("try:"),
        line.startswith("except"),
        line.startswith("with "),
        line.startswith("return"),
        "=" in line and not line.startswith("="),
        line.startswith("sketch"),
        line.startswith("pad"),
        line.startswith("pocket"),
        line.startswith("fillet"),
        line.startswith("sf."),
        line.startswith("hsf."),
        line.startswith("update"),
        line.startswith("create_"),
        line.startswith("factory"),
        line.startswith("    "),  # indented
        line.startswith("\t"),    # tab indented
    ]
    return any(code_indicators)

def _postprocess_code(self, code: str) -> str:
    """
    Clean up and validate the generated code.
    Fixes common LLM mistakes.
    """
    if not code.strip():
        return "# No code generated\nupdate()"

    lines = code.split("\n")
    processed_lines = []

    for line in lines:
        # Remove lines that try to import win32com or connect to CATIA
        lower = line.strip().lower()
        if any(skip in lower for skip in [
            "import win32com",
            "import pythoncom",
            "dispatch(",
            "catia = ",
            "catia=",
            "coinitialize",
            "couninitialize",
            'documents.add',
        ]):
            processed_lines.append(f"# REMOVED (handled by bridge): {line}")
            continue

        # Remove lines redefining our bridge variables
        if any(lower.startswith(prefix) for prefix in [
            "part_document =",
            "part_document=",
            "part = catia",
            "part =catia",
        ]):
            processed_lines.append(f"# REMOVED (pre-defined): {line}")
            continue

        processed_lines.append(line)

    code = "\n".join(processed_lines)

    # Ensure update() is called at the end
    stripped_lines = [
        l.strip() for l in code.strip().split("\n") if l.strip()
    ]
    if stripped_lines and "update()" not in stripped_lines[-1]:
        # Check if update() appears anywhere in the last 3 lines
        last_few = stripped_lines[-3:] if len(stripped_lines) >= 3 else stripped_lines
        has_update = any("update()" in l for l in last_few)
        if not has_update:
            code = code.rstrip() + "\n\n# Ensure part is updated\nupdate()\n"

    return code

# ──────────────────────────────────────────────
# History & State
# ──────────────────────────────────────────────

def clear_history(self) -> None:
    """Clear the conversation history."""
    self.conversation_history.clear()
    logger.info("🗑️ Conversation history cleared")

def get_history_summary(self) -> List[Dict[str, str]]:
    """Get a summary of the conversation history."""
    summary = []
    for msg in self.conversation_history:
        content = msg["content"]
        if len(content) > 100:
            content = content[:100] + "..."
        summary.append({
            "role": msg["role"],
            "preview": content,
        })
    return summary

def get_stats(self) -> Dict[str, Any]:
    """Get generator statistics."""
    return {
        "model": self.model,
        "generations": self.generation_count,
        "history_length": len(self.conversation_history),
        "last_code_length": len(self.last_generated_code),
    }
# ═══════════════════════════════════════════════════════════════════
# Factory / Convenience Functions
# ═══════════════════════════════════════════════════════════════════
def create_generator(model: str = "qwen2.5-coder:14b") -> OllamaGenerator:
    """
    Create and return an OllamaGenerator instance.

    text

    Args:
        model: Ollama model name to use.

    Returns:
        Initialized OllamaGenerator.
    """
    return OllamaGenerator(model=model)
# ═══════════════════════════════════════════════════════════════════
# Standalone Test
# ═══════════════════════════════════════════════════════════════════
if name == "main":
    """Quick test — run this file directly to verify Ollama connection."""
    logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

# text

print("=" * 60)
print("  Ollama Generator — Standalone Test")
print("=" * 60)

try:
    gen = create_generator("qwen2.5-coder:14b")
    print(f"\n✅ Generator created with model: {gen.model}")
    print(f"Available models: {gen.get_available_models()}")

    test_prompt = "Create a simple cube with 50mm sides"
    print(f"\n📝 Test prompt: {test_prompt}")
    print("Generating code...\n")

    code = gen.generate_code(test_prompt)

    print("═" * 60)
    print("GENERATED CODE:")
    print("═" * 60)
    for i, line in enumerate(code.split("\n"), 1):
        print(f"  {i:3d} │ {line}")
    print("═" * 60)

    print(f"\n📊 Stats: {gen.get_stats()}")
    print("\n✅ Test completed successfully!")

except Exception as e:
    print(f"\n❌ Test failed: {e}")
    import traceback
    traceback.print_exc()