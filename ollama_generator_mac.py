# ollama_generator.py
"""
Uses Ollama to generate FreeCAD Python code from natural language prompts.
Works on macOS, Linux, and Windows.
"""

import re
import time
import logging
from typing import Optional, List, Dict, Any

try:
    import ollama
except ImportError:
    raise ImportError("ollama package not installed. Run: pip install ollama")

logger = logging.getLogger("OllamaGenerator")

# ═══════════════════════════════════════════════════════════════════
# SYSTEM PROMPT — Teaches the LLM the FreeCAD Python API
# ═══════════════════════════════════════════════════════════════════

CAD_SYSTEM_PROMPT = r"""You are an expert CAD automation engineer. You write Python code that creates 3D models using FreeCAD's Python API.

## CRITICAL RULES:
1. Output ONLY a single Python code block. No explanations before or after.
2. Do NOT import FreeCAD or Part — they are already imported and available.
3. Do NOT create a new document — `doc` is already the active document.
4. Always call `update()` at the very end.
5. All measurements are in **millimeters (mm)**.
6. The code must be complete and runnable as-is.
7. Give every object a meaningful name using `obj.Label = "name"`.

## PRE-DEFINED VARIABLES (already exist — do NOT create them):

| Variable | Description |
|---|---|
| `FreeCAD` or `App` | The FreeCAD application module |
| `Part` | The Part module for creating shapes |
| `doc` or `document` | The active FreeCAD document |
| `Vector(x,y,z)` | Shortcut for `FreeCAD.Vector` |
| `Placement(pos, rot)` | Shortcut for `FreeCAD.Placement` |
| `Rotation(axis, angle)` | Shortcut for `FreeCAD.Rotation` |
| `update()` | Recomputes the document |
| `save(filepath)` | Saves the document |

## FreeCAD PYTHON API PATTERNS:

### Pattern 1 — Box (Rectangular Block):
```python
# Create a box: length=100, width=50, height=30 (mm)
box = doc.addObject("Part::Box", "MyBox")
box.Length = 100.0
box.Width = 50.0
box.Height = 30.0
box.Label = "Base Plate"
update()
Pattern 2 — Cylinder:
Python

cylinder = doc.addObject("Part::Cylinder", "MyCylinder")
cylinder.Radius = 25.0
cylinder.Height = 80.0
cylinder.Label = "Main Cylinder"
# Optional: position it
cylinder.Placement = Placement(Vector(0, 0, 30), Rotation(Vector(0, 0, 1), 0))
update()
Pattern 3 — Sphere:
Python

sphere = doc.addObject("Part::Sphere", "MySphere")
sphere.Radius = 20.0
sphere.Label = "Ball"
sphere.Placement.Base = Vector(50, 0, 0)
update()
Pattern 4 — Cone:
Python

cone = doc.addObject("Part::Cone", "MyCone")
cone.Radius1 = 30.0    # bottom radius
cone.Radius2 = 10.0    # top radius (0 for pointed cone)
cone.Height = 50.0
cone.Label = "Tapered Section"
update()
Pattern 5 — Torus:
Python

torus = doc.addObject("Part::Torus", "MyTorus")
torus.Radius1 = 40.0   # major radius
torus.Radius2 = 10.0   # minor radius (tube radius)
torus.Label = "O-Ring"
update()
Pattern 6 — Boolean Fusion (Join/Add):
Python

# Create two shapes first
box = doc.addObject("Part::Box", "Box")
box.Length = 100; box.Width = 50; box.Height = 20

cyl = doc.addObject("Part::Cylinder", "Cyl")
cyl.Radius = 15; cyl.Height = 40
cyl.Placement.Base = Vector(50, 25, 0)

# Fuse (boolean union)
fusion = doc.addObject("Part::Fuse", "FusedShape")
fusion.Shape1 = box
fusion.Shape2 = cyl
fusion.Label = "Combined Shape"

# Hide originals
box.Visibility = False
cyl.Visibility = False
update()
Pattern 7 — Boolean Cut (Subtract / Hole):
Python

# Base shape
base = doc.addObject("Part::Box", "Base")
base.Length = 100; base.Width = 100; base.Height = 20

# Tool shape (will be subtracted)
hole = doc.addObject("Part::Cylinder", "HoleTool")
hole.Radius = 15; hole.Height = 30
hole.Placement.Base = Vector(50, 50, -5)  # go through the base

# Boolean cut
cut = doc.addObject("Part::Cut", "PlateWithHole")
cut.Base = base
cut.Tool = hole
cut.Label = "Plate With Hole"

base.Visibility = False
hole.Visibility = False
update()
Pattern 8 — Multiple Holes with Loop:
Python

import math

# Base plate
plate = doc.addObject("Part::Box", "Plate")
plate.Length = 200; plate.Width = 100; plate.Height = 10

# Create holes
result = plate  # start with the plate

hole_positions = [
    (15, 15), (185, 15), (185, 85), (15, 85)  # 4 corners
]

for i, (x, y) in enumerate(hole_positions):
    hole = doc.addObject("Part::Cylinder", f"Hole_{i}")
    hole.Radius = 5.0
    hole.Height = 20.0
    hole.Placement.Base = Vector(x, y, -5)

    cut = doc.addObject("Part::Cut", f"Cut_{i}")
    cut.Base = result
    cut.Tool = hole

    result.Visibility = False
    hole.Visibility = False
    result = cut

result.Label = "Plate With Corner Holes"
update()
Pattern 9 — Extrude (Pad) from a Wire/Sketch:
Python

import Part as PartModule

# Create a 2D wire (profile)
points = [
    Vector(0, 0, 0),
    Vector(50, 0, 0),
    Vector(50, 30, 0),
    Vector(25, 50, 0),
    Vector(0, 30, 0),
    Vector(0, 0, 0),  # close the loop
]
wire = PartModule.makePolygon(points)
face = PartModule.Face(wire)
solid = face.extrude(Vector(0, 0, 20))  # extrude 20mm in Z

obj = doc.addObject("Part::Feature", "ExtrudedProfile")
obj.Shape = solid
obj.Label = "Custom Profile"
update()
Pattern 10 — Revolve (Shaft):
Python

import Part as PartModule

# Create profile to revolve (half cross-section)
points = [
    Vector(10, 0, 0),
    Vector(30, 0, 0),
    Vector(30, 0, 50),
    Vector(10, 0, 50),
    Vector(10, 0, 0),
]
wire = PartModule.makePolygon(points)
face = PartModule.Face(wire)

# Revolve around Z axis
solid = face.revolve(Vector(0, 0, 0), Vector(0, 0, 1), 360)

obj = doc.addObject("Part::Feature", "RevolvedShape")
obj.Shape = solid
obj.Label = "Revolved Body"
update()
Pattern 11 — Fillet (Round Edges):
Python

import Part as PartModule

# Create a box
box_shape = PartModule.makeBox(50, 50, 50)

# Fillet all edges (radius 3mm)
edges = box_shape.Edges
fillet = box_shape.makeFillet(3.0, edges)

obj = doc.addObject("Part::Feature", "FilletedBox")
obj.Shape = fillet
obj.Label = "Rounded Box"
update()
Pattern 12 — Chamfer:
Python

import Part as PartModule

box_shape = PartModule.makeBox(50, 50, 50)
edges = box_shape.Edges
chamfer = box_shape.makeChamfer(2.0, edges)  # 2mm chamfer

obj = doc.addObject("Part::Feature", "ChamferedBox")
obj.Shape = chamfer
obj.Label = "Chamfered Box"
update()
Pattern 13 — Positioning with Placement:
Python

cyl = doc.addObject("Part::Cylinder", "Cyl")
cyl.Radius = 10; cyl.Height = 50

# Move to position (x=100, y=50, z=0)
cyl.Placement.Base = Vector(100, 50, 0)

# Rotate 90 degrees around X axis (makes cylinder horizontal)
cyl.Placement = Placement(
    Vector(100, 50, 0),
    Rotation(Vector(1, 0, 0), 90)
)
update()
IMPORTANT NOTES:
Use doc.addObject("Part::Box", "name") for parametric primitives
Use Part.makeBox(L, W, H) for raw shapes (non-parametric)
Boolean operations need TWO shapes: .Base and .Tool (for Cut) or .Shape1/.Shape2 (for Fuse)
Hide intermediate shapes: obj.Visibility = False
Always close wire loops for extrusion
update() must be the LAST call
"""
class OllamaGenerator:
    """
    Generates FreeCAD automation Python code using a local Ollama LLM.
    """

    # text

    def __init__(self, model: str = "qwen3-coder:480b-cloud"):
        self.model = model
        self.conversation_history: List[Dict[str, str]] = []
        self.last_raw_response: str = ""
        self.last_generated_code: str = ""
        self.generation_count: int = 0
        self._verify_model()

    # ──────────────────────────────────────────
    # Model Management
    # ──────────────────────────────────────────

    def _verify_model(self) -> None:
        """Check that the model exists in Ollama. Pull if missing."""
        try:
            response = ollama.list()

            if hasattr(response, "models"):
                available = [m.model for m in response.models]
            elif isinstance(response, dict) and "models" in response:
                available = [
                    m.get("model", m.get("name", ""))
                    for m in response["models"]
                ]
            else:
                available = []

            base_name = self.model.split(":")[0]
            found = any(
                self.model in name or base_name in name
                for name in available
            )

            if found:
                logger.info(f"✅ Ollama model ready: {self.model}")
            else:
                logger.warning(f"Model '{self.model}' not found. Available: {available}")
                logger.info(f"⏬ Pulling '{self.model}'...")
                ollama.pull(self.model)
                logger.info(f"✅ Pulled '{self.model}'")

        except ConnectionError:
            raise ConnectionError(
                "Cannot connect to Ollama. Run: ollama serve"
            )
        except Exception as e:
            raise RuntimeError(f"Ollama error: {e}\nMake sure Ollama is running.")

    def switch_model(self, new_model: str) -> None:
        """Switch to a different Ollama model."""
        old = self.model
        self.model = new_model
        try:
            self._verify_model()
            logger.info(f"Switched: {old} → {new_model}")
        except Exception:
            self.model = old
            raise

    def get_available_models(self) -> List[str]:
        """List all locally available Ollama models."""
        try:
            response = ollama.list()
            if hasattr(response, "models"):
                return [m.model for m in response.models]
            elif isinstance(response, dict) and "models" in response:
                return [m.get("model", m.get("name", "")) for m in response["models"]]
            return []
        except Exception:
            return []

    # ──────────────────────────────────────────
    # Code Generation
    # ──────────────────────────────────────────

    def generate_code(self, user_prompt: str) -> str:
        """
        Generate FreeCAD Python code from a natural language prompt.

        Args:
            user_prompt: e.g. "Create a cylinder with radius 30mm and height 100mm"

        Returns:
            Clean Python code ready for execution.
        """
        messages = self._build_messages(user_prompt)

        logger.info(f"🤖 Generating code for: {user_prompt[:80]}{'...' if len(user_prompt) > 80 else ''}")

        start = time.time()

        try:
            response = ollama.chat(
                model=self.model,
                messages=messages,
                options={
                    "temperature": 0.15,
                    "top_p": 0.9,
                    "num_predict": 4096,
                    "repeat_penalty": 1.1,
                },
            )
        except Exception as e:
            raise RuntimeError(f"Ollama generation failed: {e}")

        elapsed = time.time() - start

        # Extract response text
        if hasattr(response, "message"):
            raw = response.message.content
        elif isinstance(response, dict):
            raw = response.get("message", {}).get("content", "")
        else:
            raw = str(response)

        self.last_raw_response = raw

        # Extract and clean code
        code = self._extract_code(raw)
        code = self._postprocess_code(code)

        self.last_generated_code = code
        self.generation_count += 1

        # Update history
        self.conversation_history.append({"role": "user", "content": user_prompt})
        self.conversation_history.append({"role": "assistant", "content": raw})

        # Trim history
        if len(self.conversation_history) > 20:
            self.conversation_history = self.conversation_history[-20:]

        logger.info(f"✅ Generated: {len(code)} chars, {code.count(chr(10))+1} lines, {elapsed:.1f}s")
        return code

    def refine_code(self, original_code: str, error_message: str) -> str:
        """Ask LLM to fix code that produced an error."""
        fix_prompt = (
            f"The following FreeCAD Python code produced an error. "
            f"Fix it and return the COMPLETE corrected code.\n\n"
            f"## ORIGINAL CODE:\n```python\n{original_code}\n```\n\n"
            f"## ERROR:\n```\n{error_message}\n```\n\n"
            f"Return ONLY the fixed Python code."
        )
        logger.info("🔄 Requesting code fix...")
        return self.generate_code(fix_prompt)

    def modify_existing(self, modification_prompt: str) -> str:
        """Generate code to modify an existing part."""
        enhanced = (
            f"A document already exists with some objects. "
            f"Do NOT recreate the base shape. Only add:\n\n"
            f"{modification_prompt}"
        )
        return self.generate_code(enhanced)

    # ──────────────────────────────────────────
    # Internal Helpers
    # ──────────────────────────────────────────

    def _build_messages(self, user_prompt: str) -> List[Dict[str, str]]:
        """Build message list for Ollama API."""
        messages = [{"role": "system", "content": CAD_SYSTEM_PROMPT}]
        messages.extend(self.conversation_history)
        messages.append({
            "role": "user",
            "content": (
                f"Generate FreeCAD Python code for:\n\n"
                f"{user_prompt}\n\n"
                f"Output ONLY a Python code block. No explanations."
            ),
        })
        return messages

    def _extract_code(self, response_text: str) -> str:
        """Extract Python code from LLM response."""
        if not response_text or not response_text.strip():
            return "# Empty response\nupdate()"

        text = response_text.strip()

        # Strategy 1: ```python ... ```
        matches = re.findall(r"```python\s*\n(.*?)```", text, re.DOTALL)
        if matches:
            return "\n\n".join(m.strip() for m in matches)

        # Strategy 2: ``` ... ```
        matches = re.findall(r"```\s*\n(.*?)```", text, re.DOTALL)
        if matches:
            return "\n\n".join(m.strip() for m in matches)

        # Strategy 3: inline ```python...```
        matches = re.findall(r"```python(.*?)```", text, re.DOTALL)
        if matches:
            return "\n\n".join(m.strip() for m in matches)

        # Strategy 4: raw code detection
        lines = text.split("\n")
        code_lines = []
        in_code = False

        for line in lines:
            stripped = line.strip()
            if not in_code and not stripped:
                continue
            if not in_code and self._looks_like_code(stripped):
                in_code = True
            if in_code:
                code_lines.append(line)

        if code_lines:
            return "\n".join(code_lines)

        return text

    def _looks_like_code(self, line: str) -> bool:
        """Heuristic: does this line look like Python code?"""
        if not line:
            return False
        indicators = [
            line.startswith("#"), line.startswith("import "),
            line.startswith("from "), line.startswith("def "),
            line.startswith("for "), line.startswith("while "),
            line.startswith("if "), line.startswith("try:"),
            line.startswith("    "), line.startswith("\t"),
            "=" in line and not line.startswith("="),
            line.startswith("doc."), line.startswith("Part."),
            line.startswith("box"), line.startswith("cyl"),
            line.startswith("update"), line.startswith("Vector"),
        ]
        return any(indicators)

    def _postprocess_code(self, code: str) -> str:
        """Clean up generated code."""
        if not code.strip():
            return "# No code generated\nupdate()"

        lines = code.split("\n")
        processed = []

        for line in lines:
            lower = line.strip().lower()

            # Remove lines that re-import/re-create things we provide
            skip_patterns = [
                "import freecad",
                "import part",
                "from freecad",
                "sys.path",
                "app.newdocument",
                "freecad.newdocument",
                "doc = app",
                "doc = freecad",
                "doc=app",
                "document = app",
            ]

            if any(pat in lower for pat in skip_patterns):
                processed.append(f"# REMOVED (handled by bridge): {line}")
                continue

            processed.append(line)

        code = "\n".join(processed)

        # Ensure update() at end
        stripped_lines = [l.strip() for l in code.strip().split("\n") if l.strip()]
        if stripped_lines:
            last_few = stripped_lines[-3:]
            if not any("update()" in l for l in last_few):
                code = code.rstrip() + "\n\nupdate()\n"

        return code

    # ──────────────────────────────────────────
    # History
    # ──────────────────────────────────────────

    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history.clear()
        logger.info("🗑️ History cleared")

    def get_stats(self) -> Dict[str, Any]:
        return {
            "model": self.model,
            "generations": self.generation_count,
            "history_length": len(self.conversation_history),
            "last_code_length": len(self.last_generated_code),
        }


def create_generator(model: str = "qwen3-coder:480b-cloud") -> OllamaGenerator:
    """Factory function."""
    return OllamaGenerator(model=model)

#── Standalone Test ──
if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] %(message)s")

    print("=" * 60)
    print("  Ollama Generator — Test")
    print("=" * 60)

    try:
        gen = create_generator("qwen3-coder:480b-cloud")
        print(f"\n✅ Model: {gen.model}")
        print(f"Available: {gen.get_available_models()}")

        code = gen.generate_code("Create a simple cube with 50mm sides")

        print("\n" + "=" * 60)
        print("GENERATED CODE:")
        print("=" * 60)
        for i, line in enumerate(code.split("\n"), 1):
            print(f"  {i:3d} │ {line}")
        print("=" * 60)
        print("✅ Test passed!")

    except Exception as e:
        print(f"❌ Failed: {e}")
        import traceback
        traceback.print_exc()