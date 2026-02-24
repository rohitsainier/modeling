# ai_model_generator.py
# ═══════════════════════════════════════════════════════════════
# 🏭 AI 3D Model Generator for Blender — Streaming Edition
# ═══════════════════════════════════════════════════════════════
#
# Install:  Edit → Preferences → Add-ons → Install… → pick this .py
# Or:       Open in Blender Text Editor → Run Script
#
# Requires: Ollama running locally  (ollama serve)
#           A coding model pulled    (ollama pull qwen2.5-coder:14b)
#
# After enabling, look for the "AI Gen" tab in the 3-D Viewport
# sidebar (press N to toggle the sidebar).
# ═══════════════════════════════════════════════════════════════

bl_info = {
    "name": "AI 3D Model Generator",
    "author": "AI-Assisted CAD Generator",
    "version": (2, 0, 0),
    "blender": (3, 0, 0),
    "location": "View3D → Sidebar → AI Gen",
    "description": (
        "Type a prompt, stream code from a local Ollama LLM, "
        "and watch the 3-D model build itself in real time."
    ),
    "category": "3D View",
}

# ═══════════════════════════════════════════════════
# IMPORTS
# ═══════════════════════════════════════════════════

import bpy
import bmesh
import mathutils
import math
import json
import re
import ast
import time
import traceback
import threading
import builtins
from collections import deque

try:
    import queue
except ImportError:
    import Queue as queue  # Python 2 fallback (unlikely)

from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

# ═══════════════════════════════════════════════════
# CONFIGURATION DEFAULTS
# ═══════════════════════════════════════════════════

DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5-coder:14b"

EXEC_INTERVAL = 0.35          # seconds between progressive exec attempts
CODE_TEXT_NAME = "AI_Generated_Code"   # Text datablock for output
LOG_TEXT_NAME = "AI_Gen_Log"           # Text datablock for log

# ═══════════════════════════════════════════════════
# SYSTEM PROMPT  — teaches the LLM Blender's Python API
# ═══════════════════════════════════════════════════

SYSTEM_PROMPT = r"""You are an expert Blender Python automation engineer.
You write bpy scripts that create 3D models inside an existing Blender scene.

## CRITICAL RULES
1. Output ONLY a single Python code block.  No explanations, no markdown outside the fence.
2. `bpy`, `bmesh`, `mathutils`, `math` are already imported.
3. A clean scene is already prepared — do NOT call `bpy.ops.wm.read_factory_settings()`.
4. Measurements: use **metres** (Blender default).  1 unit = 1 m.
5. Give every new object a descriptive `.name`.
6. ALWAYS end with: `bpy.context.view_layer.update()`

## AVAILABLE IN NAMESPACE
- `bpy`             – full Blender Python API
- `bmesh`           – BMesh mesh-editing toolkit
- `mathutils`       – Vector, Matrix, Euler, Quaternion, Color
- `Vector`          – shortcut for mathutils.Vector
- `Matrix`          – shortcut for mathutils.Matrix
- `Euler`           – shortcut for mathutils.Euler
- `Quaternion`      – shortcut for mathutils.Quaternion
- `math`            – Python math module
- `pi`              – math.pi
- `radians`         – math.radians
- `degrees`         – math.degrees
- `collection`      – bpy.context.collection  (link new objects here)

## COMMON PATTERNS

### Cube
```python
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
cube = bpy.context.active_object
cube.name = "MyCube"
cube.scale = (2, 1, 0.5)
bpy.context.view_layer.update()
Cylinder
Python

bpy.ops.mesh.primitive_cylinder_add(radius=0.5, depth=2, location=(0, 0, 1))
cyl = bpy.context.active_object
cyl.name = "MyCylinder"
bpy.context.view_layer.update()
UV Sphere
Python

bpy.ops.mesh.primitive_uv_sphere_add(radius=0.5, segments=32, ring_count=16, location=(0, 0, 0.5))
sphere = bpy.context.active_object
sphere.name = "MySphere"
bpy.context.view_layer.update()
Cone
Python

bpy.ops.mesh.primitive_cone_add(radius1=0.5, radius2=0, depth=1, location=(0, 0, 0.5))
cone = bpy.context.active_object
cone.name = "MyCone"
bpy.context.view_layer.update()
Torus
Python

bpy.ops.mesh.primitive_torus_add(major_radius=1, minor_radius=0.25, location=(0, 0, 0.25))
torus = bpy.context.active_object
torus.name = "MyTorus"
bpy.context.view_layer.update()
Plane / Plate
Python

bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, 0))
plate = bpy.context.active_object
plate.name = "BasePlate"
# Solidify to give it thickness
mod = plate.modifiers.new("Solidify", 'SOLIDIFY')
mod.thickness = 0.05
bpy.context.view_layer.update()
Boolean Difference (hole)
Python

# Base
bpy.ops.mesh.primitive_cube_add(size=2, location=(0, 0, 1))
base = bpy.context.active_object
base.name = "Base"

# Cutter
bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=3, location=(0, 0, 1))
cutter = bpy.context.active_object
cutter.name = "Cutter"

# Boolean
mod = base.modifiers.new("Bool", 'BOOLEAN')
mod.operation = 'DIFFERENCE'
mod.object = cutter
bpy.context.view_layer.objects.active = base
bpy.ops.object.modifier_apply(modifier="Bool")

# Hide/delete cutter
cutter.hide_set(True)
cutter.hide_render = True
bpy.context.view_layer.update()
Boolean Union
Python

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
a = bpy.context.active_object; a.name = "PartA"
bpy.ops.mesh.primitive_cylinder_add(radius=0.3, depth=1.5, location=(0, 0, 0.75))
b = bpy.context.active_object; b.name = "PartB"

mod = a.modifiers.new("Union", 'BOOLEAN')
mod.operation = 'UNION'
mod.object = b
bpy.context.view_layer.objects.active = a
bpy.ops.object.modifier_apply(modifier="Union")
b.hide_set(True); b.hide_render = True
bpy.context.view_layer.update()
Multiple holes in a loop
Python

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.025))
plate = bpy.context.active_object
plate.name = "HolePlate"
plate.scale = (2, 1, 0.05)
bpy.ops.object.transform_apply(scale=True)

positions = [(-0.7, -0.3, 0), (0.7, -0.3, 0), (0.7, 0.3, 0), (-0.7, 0.3, 0)]
for i, pos in enumerate(positions):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.08, depth=0.2, location=pos)
    cutter = bpy.context.active_object
    cutter.name = f"Hole_{i}"
    mod = plate.modifiers.new(f"Hole_{i}", 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.object = cutter
    bpy.context.view_layer.objects.active = plate
    bpy.ops.object.modifier_apply(modifier=f"Hole_{i}")
    cutter.hide_set(True); cutter.hide_render = True

bpy.context.view_layer.update()
Subdivision Surface
Python

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
obj = bpy.context.active_object
obj.name = "Smooth"
mod = obj.modifiers.new("Subsurf", 'SUBSURF')
mod.levels = 2; mod.render_levels = 3
bpy.context.view_layer.update()
Bevel modifier
Python

bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0.5))
obj = bpy.context.active_object
obj.name = "Beveled"
mod = obj.modifiers.new("Bevel", 'BEVEL')
mod.width = 0.05; mod.segments = 3
bpy.context.view_layer.update()
Mirror modifier
Python

bpy.ops.mesh.primitive_cube_add(size=0.5, location=(0.5, 0, 0.25))
obj = bpy.context.active_object
obj.name = "Mirrored"
mod = obj.modifiers.new("Mirror", 'MIRROR')
mod.use_axis = (True, True, False)
bpy.context.view_layer.update()
Material (simple color)
Python

mat = bpy.data.materials.new("Red")
mat.use_nodes = True
bsdf = mat.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.8, 0.1, 0.1, 1)
    bsdf.inputs["Roughness"].default_value = 0.4
obj.data.materials.append(mat)
bpy.context.view_layer.update()
Rotation
Python

import math
obj.rotation_euler = (math.radians(45), 0, math.radians(30))
bpy.context.view_layer.update()
Array modifier
Python

bpy.ops.mesh.primitive_cube_add(size=0.2, location=(0, 0, 0.1))
obj = bpy.context.active_object
obj.name = "Arrayed"
mod = obj.modifiers.new("Array", 'ARRAY')
mod.count = 10
mod.relative_offset_displace = (1.5, 0, 0)
bpy.context.view_layer.update()
Extrude a profile (BMesh)
Python

mesh = bpy.data.meshes.new("ProfileMesh")
obj = bpy.data.objects.new("Profile", mesh)
bpy.context.collection.objects.link(obj)
bm = bmesh.new()
verts = [bm.verts.new(v) for v in [
    (0,0,0),(1,0,0),(1,0.5,0),(0.5,0.5,0),(0.5,1,0),(0,1,0)
]]
bm.faces.new(verts)
bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
for v in bm.verts:
    if v.co.z == 0 and v.select:
        pass
bmesh.ops.translate(bm, vec=(0,0,0.3), verts=[v for v in bm.verts if v.select])
bm.to_mesh(mesh)
bm.free()
bpy.context.view_layer.update()
STRICT RULES
Use bpy.ops.mesh.primitive_* for simple shapes.
Use bpy.context.active_object right after primitive ops to get the object.
Boolean: set .object, apply modifier, hide cutter.
Deselect all before new primitive if needed: bpy.ops.object.select_all(action='DESELECT')
bpy.context.view_layer.update() MUST be the last call.
Output ONLY code. No explanations.
"""

# ═══════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════

def _extract_code(raw_text):
    """Extract Python from the complete raw LLM output."""
    if not raw_text:
        return "bpy.context.view_layer.update()"
    text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
    for pat in [r"```python\s*\n(.*?)```", r"```\s*\n(.*?)```"]:
        m = re.search(pat, text, re.DOTALL)
        if m:
            return m.group(1).strip()
    return text.strip()

def _extract_code_streaming(raw_text):
    """
    Extract code from a partial (still-growing) raw text.
    Returns (code_so_far, is_complete).
    """
    if not raw_text:
        return "", False

    text = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)

    # Still inside <think>
    if "<think>" in text and "</think>" not in text:
        return "", False
    text = re.sub(r"<think>.*$", "", text, flags=re.DOTALL)

    # Complete ```python … ```
    m = re.search(r"```python\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip(), True

    # Incomplete ```python … (still streaming)
    m = re.search(r"```python\s*\n(.*?)$", text, re.DOTALL)
    if m:
        return m.group(1), False

    # Complete ``` … ```
    m = re.search(r"```\s*\n(.*?)```", text, re.DOTALL)
    if m:
        return m.group(1).strip(), True

    # Incomplete ``` …
    m = re.search(r"```\s*\n(.*?)$", text, re.DOTALL)
    if m:
        return m.group(1), False

    return text.strip(), False

def _clean_code(code):
    """Remove / comment-out lines that clash with our setup."""
    if not code:
        return code
    skip_markers = ["bpy.ops.wm.read_factory_settings", "bpy.ops.wm.open_mainfile", "bpy.ops.wm.save_mainfile", "bpy.ops.wm.quit_blender"]
    out = []
    for line in code.split("\n"):
        low = line.strip().lower()
        if any(s in low for s in skip_markers):
            out.append(f"# [removed]: {line}")
        else:
            out.append(line)
    return "\n".join(out)

def _get_text_block(name):
    """Get or create a Text datablock."""
    tb = bpy.data.texts.get(name)
    if tb is None:
        tb = bpy.data.texts.new(name)
    return tb

def _tag_redraw():
    """Ask every 3-D viewport to repaint."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()

def _fit_view_all():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        try:
                            override = {
                                'window': window,
                                'screen': window.screen,
                                'area': area,
                                'region': region,
                            }

                            if hasattr(bpy.context, "temp_override"):
                                with bpy.context.temp_override(**override):
                                    bpy.ops.view3d.view_all()
                            else:
                                bpy.ops.view3d.view_all(override)

                        except Exception:
                            pass
                        return

def _clear_scene(): 
    """Remove all mesh objects (keep cameras, lights)."""
    bpy.ops.object.select_all(action='DESELECT')
    for obj in list(bpy.data.objects):
        if obj.type == 'MESH':
            bpy.data.objects.remove(obj, do_unlink=True)
    # Purge orphan data
    for block in list(bpy.data.meshes):
        if block.users == 0:
            bpy.data.meshes.remove(block)

# ═══════════════════════════════════════════════════
# STREAM THREAD (background networking)
# ═══════════════════════════════════════════════════

class _StreamThread(threading.Thread):
    """
    Reads the Ollama streaming response line-by-line in a
    background thread and pushes ('token', str) /
    ('done',) / ('error', str) messages into out_queue.
    """
    def __init__(self, base_url, model, messages, out_queue):
        super().__init__(daemon=True)
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.messages = messages
        self.q = out_queue
        self.abort_flag = False
        self._resp = None

    def abort(self):
        self.abort_flag = True
        resp = self._resp
        if resp:
            try:
                resp.close()
            except Exception:
                pass

    def run(self):
        payload = json.dumps({
            "model": self.model,
            "messages": self.messages,
            "stream": True,
            "options": {
                "temperature": 0.15,
                "top_p": 0.9,
                "num_predict": 4096,
            },
        }).encode("utf-8")

        req = Request(
            f"{self.base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            self._resp = urlopen(req, timeout=600)
            while not self.abort_flag:
                line = self._resp.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                tok = data.get("message", {}).get("content", "")
                if tok:
                    self.q.put(("token", tok))
                if data.get("done", False):
                    break

            if not self.abort_flag:
                self.q.put(("done",))
        except Exception as exc:
            if not self.abort_flag:
                self.q.put(("error", str(exc)))
        finally:
            resp = self._resp
            self._resp = None
            if resp:
                try:
                    resp.close()
                except Exception:
                    pass

# ═══════════════════════════════════════════════════
# PROGRESSIVE EXECUTOR
# ═══════════════════════════════════════════════════

class _ProgressiveExecutor:
    """
    Execute Blender Python code statement-by-statement as it
    streams in, using ast.parse to discover complete top-level
    statements. After each batch it calls
    bpy.context.view_layer.update() so objects appear instantly.
    """
    def __init__(self):
        self.executed_count = 0
        self.errors = []
        self.namespace = {
            # Blender
            "bpy": bpy,
            "bmesh": bmesh,
            "mathutils": mathutils,
            "Vector": mathutils.Vector,
            "Matrix": mathutils.Matrix,
            "Euler": mathutils.Euler,
            "Quaternion": mathutils.Quaternion,
            "Color": mathutils.Color,
            "collection": bpy.context.collection,
            # Math
            "math": math,
            "pi": math.pi,
            "radians": math.radians,
            "degrees": math.degrees,
            # Builtins
            "__builtins__": builtins,
        }
        try:
            import random
            self.namespace["random"] = random
        except ImportError:
            pass

    def try_execute_new(self, code):
        """Run any newly-complete top-level statements.
        Returns the number of statements executed this call."""
        tree = self._parse_max(code)
        if tree is None:
            return 0
        total = len(tree.body)
        if total <= self.executed_count:
            return 0

        lines = code.split("\n")
        ran = 0
        for i in range(self.executed_count, total):
            node = tree.body[i]
            nxt = tree.body[i + 1] if i + 1 < total else None
            src = self._node_source(node, lines, nxt)
            try:
                exec(compile(src, "<stream>", "exec"), self.namespace)
                ran += 1
            except Exception as exc:
                self.errors.append(
                    f"stmt {i+1} (line {node.lineno}): {exc}"
                )
                break

        self.executed_count += ran
        if ran > 0:
            try:
                bpy.context.view_layer.update()
            except Exception:
                pass
        return ran

    def execute_remaining(self, code):
        """Execute everything that hasn't run yet.
        Returns ``(success, message)``."""
        try:
            tree = ast.parse(code)
        except SyntaxError as exc:
            return False, f"SyntaxError: {exc}"

        lines = code.split("\n")
        total = len(tree.body)

        for i in range(self.executed_count, total):
            node = tree.body[i]
            nxt = tree.body[i + 1] if i + 1 < total else None
            src = self._node_source(node, lines, nxt)
            try:
                exec(compile(src, "<stream>", "exec"), self.namespace)
                self.executed_count += 1
            except Exception as exc:
                return False, (
                    f"{type(exc).__name__} at line {node.lineno}: "
                    f"{exc}\n\n{traceback.format_exc()}"
                )

        try:
            bpy.context.view_layer.update()
        except Exception:
            pass
        return True, "Model created successfully!"

    @staticmethod
    def _node_source(node, lines, next_node=None):
        start = node.lineno - 1
        end = getattr(node, "end_lineno", None)
        if end is not None:
            return "\n".join(lines[start:end])
        if next_node is not None:
            end = next_node.lineno - 1
        else:
            end = len(lines)
        return "\n".join(lines[start:end])

    @staticmethod
    def _parse_max(code):
        """Parse the longest valid prefix."""
        try:
            return ast.parse(code)
        except SyntaxError:
            lines = code.split("\n")
            for n in range(len(lines), 0, -1):
                try:
                    return ast.parse("\n".join(lines[:n]))
                except SyntaxError:
                    continue
            return None

# ═══════════════════════════════════════════════════
# GLOBAL RUNTIME STATE
# ═══════════════════════════════════════════════════

class _State:
    """Singleton holding data that lives across operator calls."""
    history = []  # conversation history
    model_list = []  # available Ollama models
    thread = None
    msg_queue = None
    executor = None
    raw_text = ""
    current_code = ""
    last_exec_check = ""
    token_count = 0
    start_time = 0.0
    prompt = ""
    mode = "idle"           # idle | generating | fixing
    should_stop = False

_S = _State()

# ═══════════════════════════════════════════════════
# OLLAMA HELPERS (run on main thread — quick calls)
# ═══════════════════════════════════════════════════

def _ollama_reachable(url):
    try:
        urlopen(Request(f"{url.rstrip('/')}/api/tags"), timeout=3)
        return True
    except Exception:
        return False

def _ollama_models(url):
    try:
        resp = urlopen(Request(f"{url.rstrip('/')}/api/tags"), timeout=5)
        data = json.loads(resp.read().decode())
        return [m.get("name", m.get("model", "")) for m in data.get("models", [])]
    except Exception:
        return []

def _build_generate_messages(prompt, history):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history)
    msgs.append({
        "role": "user",
        "content": (
            "Generate Blender Python code for:\n\n"
            f"{prompt}\n\n"
            "Output ONLY Python code inside a single ```python block."
        ),
    })
    return msgs

def _build_fix_messages(code, error):
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.append({
        "role": "user",
        "content": (
            "This Blender Python code produced an error. "
            "Fix it completely.\n\n"
            f"CODE:\n```python\n{code}\n```\n\n\n"
            f"ERROR:\n\n{error}\n\n\n"
            "Return ONLY the corrected Python code."
        ),
    })
    return msgs

# ═══════════════════════════════════════════════════
# BLENDER PROPERTY GROUP
# ═══════════════════════════════════════════════════

def _get_model_items(self, context):
    """Return model list as EnumProperty items"""
    items = []
    
    # Add default option
    default_model = getattr(context.scene.ai_gen, 'model_name', DEFAULT_OLLAMA_MODEL)
    
    # Add models from the global state if available
    if hasattr(_S, 'model_list') and _S.model_list:
        for model in _S.model_list:
            items.append((model, model, f"Ollama model: {model}"))
    else:
        # Fallback to just the default
        items.append((DEFAULT_OLLAMA_MODEL, DEFAULT_OLLAMA_MODEL, "Default model"))
    
    return items

class AIGEN_OT_SetModelFromList(bpy.types.Operator):
    bl_idname = "aigen.set_model_from_list"
    bl_label = "Select Model"
    bl_description = "Choose from available models"
    
    model: bpy.props.EnumProperty(
        name="Models",
        items=lambda self, context: [
            (m, m, "") for m in getattr(_S, 'model_list', [])
        ] if getattr(_S, 'model_list', []) else [("", "No models found", "")]
    )
    
    def execute(self, context):
        if self.model:
            context.scene.ai_gen.model_name = self.model
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "model", expand=False)

class AIGEN_PG_Props(bpy.types.PropertyGroup):
    """Addon preferences stored on each Scene."""
    ollama_url: bpy.props.StringProperty(
        name="Ollama URL",
        default=DEFAULT_OLLAMA_URL,
        description="Base URL for the Ollama REST API",
    )
    model_name: bpy.props.StringProperty(
        name="Model",
        default=DEFAULT_OLLAMA_MODEL,
        description="Ollama model to use (type model name or select from list)",
    )
    prompt: bpy.props.StringProperty(
        name="Prompt",
        description="Describe the 3D model you want",
        default="",
    )
    status: bpy.props.StringProperty(
        name="Status",
        default="Ready",
    )
    progress: bpy.props.StringProperty(
        name="Progress",
        default="",
    )
    autofix: bpy.props.BoolProperty(
        name="Auto-fix errors",
        default=True,
        description="If execution fails, ask the LLM to fix the code automatically",
    )
    is_streaming: bpy.props.BoolProperty(
        name="Streaming",
        default=False,
    )
    show_advanced: bpy.props.BoolProperty(
        name="Show Advanced",
        default=False,
    )
    available_models: bpy.props.StringProperty(
        name="Available",
        default="",
    )

# ═══════════════════════════════════════════════════
# OPERATORS
# ═══════════════════════════════════════════════════

# ── Check Ollama connection ──────────────────────

class AIGEN_OT_CheckConnection(bpy.types.Operator):
    bl_idname = "aigen.check_connection"
    bl_label = "Check Connection"
    bl_description = "Test whether Ollama is reachable"

    def execute(self, context):
        props = context.scene.ai_gen
        if _ollama_reachable(props.ollama_url):
            props.status = "✅ Ollama connected"
            self.report({'INFO'}, "Ollama is reachable")
        else:
            props.status = "❌ Ollama not found — run: ollama serve"
            self.report({'WARNING'}, "Cannot reach Ollama")
        _tag_redraw()
        return {'FINISHED'}

# ── Refresh model list ──────────────────────────

class AIGEN_OT_RefreshModels(bpy.types.Operator):
    bl_idname = "aigen.refresh_models"
    bl_label = "Refresh Models"
    bl_description = "Fetch available models from Ollama"

    def execute(self, context):
        props = context.scene.ai_gen
        models = _ollama_models(props.ollama_url)
        _S.model_list = models
        if models:
            props.available_models = ", ".join(models)
            self.report({'INFO'}, f"Found {len(models)} model(s)")
        else:
            props.available_models = "(none found)"
            self.report({'WARNING'}, "No models found")
        _tag_redraw()
        return {'FINISHED'}

# ── Quick prompt ─────────────────────────────────

class AIGEN_OT_QuickPrompt(bpy.types.Operator):
    bl_idname = "aigen.quick_prompt"
    bl_label = "Quick Prompt"
    bl_description = "Set prompt to a preset example"

    text: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.ai_gen.prompt = self.text
        _tag_redraw()
        return {'FINISHED'}

# ── Clear history ────────────────────────────────

class AIGEN_OT_ClearHistory(bpy.types.Operator):
    bl_idname = "aigen.clear_history"
    bl_label = "Clear History"
    bl_description = "Clear LLM conversation history"

    def execute(self, context):
        _S.history.clear()
        context.scene.ai_gen.status = "🗑️ History cleared"
        self.report({'INFO'}, "Conversation history cleared")
        _tag_redraw()
        return {'FINISHED'}

# ── Clear scene ──────────────────────────────────

class AIGEN_OT_ClearScene(bpy.types.Operator):
    bl_idname = "aigen.clear_scene"
    bl_label = "Clear Scene"
    bl_description = "Remove all mesh objects from the scene"

    def execute(self, context):
        _clear_scene()
        context.scene.ai_gen.status = "🧹 Scene cleared"
        _tag_redraw()
        return {'FINISHED'}

# ── View generated code in Text Editor ──────────

class AIGEN_OT_ViewCode(bpy.types.Operator):
    bl_idname = "aigen.view_code"
    bl_label = "View Generated Code"
    bl_description = "Open the generated code in a Text Editor area"

    def execute(self, context):
        tb = bpy.data.texts.get(CODE_TEXT_NAME)
        if tb is None:
            self.report({'WARNING'}, "No code generated yet")
            return {'CANCELLED'}

        # Find or create a TEXT_EDITOR area
        for area in context.screen.areas:
            if area.type == 'TEXT_EDITOR':
                area.spaces.active.text = tb
                _tag_redraw()
                return {'FINISHED'}

        # If no text editor is open, change the smallest area
        smallest = None
        for area in context.screen.areas:
            if area.type not in {'VIEW_3D', 'PROPERTIES', 'OUTLINER'}:
                if smallest is None or area.width * area.height < smallest.width * smallest.height:
                    smallest = area
        if smallest:
            smallest.type = 'TEXT_EDITOR'
            smallest.spaces.active.text = tb
            _tag_redraw()
            return {'FINISHED'}

        self.report({'INFO'},
                     f"Code saved to Text block '{CODE_TEXT_NAME}'. "
                     "Open a Text Editor to view it.")
        return {'FINISHED'}

# ── STOP ─────────────────────────────────────────

class AIGEN_OT_Stop(bpy.types.Operator):
    bl_idname = "aigen.stop"
    bl_label = "Stop Generation"
    bl_description = "Abort the current generation"

    @classmethod
    def poll(cls, context):
        return _S.mode != "idle"

    def execute(self, context):
        _S.should_stop = True
        if _S.thread:
            _S.thread.abort()
        context.scene.ai_gen.status = "⏹ Stopping…"
        _tag_redraw()
        return {'FINISHED'}

# ── GENERATE (modal operator) ────────────────────

class AIGEN_OT_Generate(bpy.types.Operator):
    """
    Core modal operator. Launches a background thread that streams
    tokens from Ollama. A timer polls the message queue, updates
    the code display, and progressively executes statements.
    """
    bl_idname = "aigen.generate"
    bl_label = "Generate Model"
    bl_description = "Generate a 3D model from your text prompt"
    bl_options = {'REGISTER'}

    modify_only: bpy.props.BoolProperty(
        name="Modify Only",
        default=False,
        description="If True, don't clear the scene first",
    )

    _timer = None

    @classmethod
    def poll(cls, context):
        return _S.mode == "idle"

    def invoke(self, context, event):
        props = context.scene.ai_gen
        prompt = props.prompt.strip()
        if not prompt:
            self.report({'WARNING'}, "Enter a prompt first")
            return {'CANCELLED'}

        if not _ollama_reachable(props.ollama_url):
            props.status = "❌ Ollama not reachable"
            self.report({'ERROR'}, "Cannot reach Ollama")
            return {'CANCELLED'}

        # ── prepare scene ──
        if not self.modify_only:
            _clear_scene()

        # ── prepare state ──
        _S.mode = "generating"
        _S.should_stop = False
        _S.raw_text = ""
        _S.current_code = ""
        _S.last_exec_check = ""
        _S.token_count = 0
        _S.start_time = time.time()
        _S.prompt = prompt
        _S.msg_queue = queue.Queue()
        _S.executor = _ProgressiveExecutor()

        props.is_streaming = True
        props.status = "🤖 Starting stream…"
        props.progress = ""

        # ── build messages ──
        if self.modify_only:
            full_prompt = (
                "The scene already contains objects. "
                "Do NOT recreate them. Only add:\n" + prompt
            )
        else:
            full_prompt = prompt

        msgs = _build_generate_messages(full_prompt, _S.history)

        # ── code text block ──
        tb = _get_text_block(CODE_TEXT_NAME)
        tb.clear()
        tb.write("# Streaming from Ollama…\n")

        # ── launch thread ──
        _S.thread = _StreamThread(
            props.ollama_url,
            props.model_name,
            msgs,
            _S.msg_queue,
        )
        _S.thread.start()

        # ── start timer ──
        self._timer = context.window_manager.event_timer_add(
            0.1, window=context.window
        )
        context.window_manager.modal_handler_add(self)

        _tag_redraw()
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        props = context.scene.ai_gen

        # ── user abort ──
        if _S.should_stop:
            self._finalise(context, aborted=True)
            return {'CANCELLED'}

        if event.type == 'ESC':
            _S.should_stop = True
            if _S.thread:
                _S.thread.abort()
            self._finalise(context, aborted=True)
            return {'CANCELLED'}

        if event.type != 'TIMER':
            return {'PASS_THROUGH'}

        # ── drain queue ──
        finished = False
        error_msg = None

        try:
            while True:
                msg = _S.msg_queue.get_nowait()
                kind = msg[0]
                if kind == "token":
                    self._on_token(context, msg[1])
                elif kind == "done":
                    finished = True
                elif kind == "error":
                    error_msg = msg[1]
        except queue.Empty:
            pass

        # ── progressive execution ──
        code = _S.current_code
        if code and code != _S.last_exec_check and _S.executor:
            _S.last_exec_check = code
            ran = _S.executor.try_execute_new(code)
            if ran > 0:
                stmts = _S.executor.executed_count
                props.progress = (
                    f"⚡ {stmts} stmts executed  |  "
                    f"{code.count(chr(10))+1} lines"
                )
                _tag_redraw()

        # ── stream ended ──
        if error_msg is not None:
            self._on_error(context, error_msg)
            return {'FINISHED'}

        if finished:
            self._on_done(context)
            return {'FINISHED'}

        return {'PASS_THROUGH'}

    def _on_token(self, context, token):
        _S.raw_text += token
        _S.token_count += 1
        elapsed = time.time() - _S.start_time
        props = context.scene.ai_gen

        # Still thinking?
        if "<think>" in _S.raw_text and "</think>" not in _S.raw_text:
            props.status = (
                f"🧠 Thinking… ({elapsed:.1f}s, "
                f"{_S.token_count} tok)"
            )
            _tag_redraw()
            return

        code, _ = _extract_code_streaming(_S.raw_text)
        if code:
            code = _clean_code(code)
            _S.current_code = code
            # Update text block
            tb = _get_text_block(CODE_TEXT_NAME)
            tb.clear()
            tb.write(code)

            lines = code.count("\n") + 1
            stmts = _S.executor.executed_count if _S.executor else 0
            props.status = (
                f"📝 Streaming… {lines} lines, "
                f"{stmts} exec  ({elapsed:.1f}s)"
            )
        else:
            props.status = (
                f"🤖 Streaming… ({elapsed:.1f}s, "
                f"{_S.token_count} tok)"
            )
        _tag_redraw()

    def _on_done(self, context):
        props = context.scene.ai_gen
        elapsed = time.time() - _S.start_time

        # Final code extraction
        code = _extract_code(_S.raw_text)
        code = _clean_code(code)
        _S.current_code = code

        tb = _get_text_block(CODE_TEXT_NAME)
        tb.clear()
        # Write with line numbers
        for i, line in enumerate(code.split("\n"), 1):
            tb.write(f"{i:4d} │ {line}\n")

        # Execute remaining statements
        if _S.executor:
            ok, msg = _S.executor.execute_remaining(code)
        else:
            ok, msg = False, "No executor"

        if ok:
            label = ("🎉 Model created!" if _S.mode == "generating"
                     else "🎉 Auto-fix worked!")
            props.status = label
            props.progress = (
                f"✅ Done — {code.count(chr(10))+1} lines "
                f"in {elapsed:.1f}s"
            )
            self.report({'INFO'}, label)
            _fit_view_all()
            # Save to history
            _S.history.append({"role": "user", "content": _S.prompt})
            _S.history.append(
                {"role": "assistant", "content": _S.raw_text}
            )
            if len(_S.history) > 20:
                _S.history = _S.history[-20:]
            self._finalise(context)
        else:
            props.progress = f"❌ {msg[:120]}"
            self.report({'ERROR'}, f"Execution failed: {msg[:200]}")

            # ── auto-fix ──
            if _S.mode == "generating" and props.autofix:
                props.status = "🔄 Auto-fixing…"
                _tag_redraw()
                _clear_scene()
                self._start_fix_stream(context, code, msg)
                # Stay modal — the fix stream reuses this timer
                return
            else:
                props.status = "❌ Execution failed"
                self._finalise(context)

    def _on_error(self, context, error_text):
        props = context.scene.ai_gen
        elapsed = time.time() - _S.start_time
        props.status = f"❌ Stream error ({elapsed:.1f}s)"
        props.progress = error_text[:160]
        self.report({'ERROR'}, f"Stream error: {error_text[:200]}")

        # Salvage partial code
        if _S.current_code and _S.executor:
            ok, msg = _S.executor.execute_remaining(_S.current_code)
            if ok:
                props.status = "⚠ Partial model (stream interrupted)"
                _fit_view_all()

        self._finalise(context)

    def _start_fix_stream(self, context, bad_code, error_msg):
        """Kick off a new streaming thread for the auto-fix attempt."""
        props = context.scene.ai_gen

        _S.mode = "fixing"
        _S.raw_text = ""
        _S.current_code = ""
        _S.last_exec_check = ""
        _S.token_count = 0
        _S.start_time = time.time()
        _S.msg_queue = queue.Queue()
        _S.executor = _ProgressiveExecutor()

        msgs = _build_fix_messages(bad_code, error_msg)
        _S.thread = _StreamThread(
            props.ollama_url,
            props.model_name,
            msgs,
            _S.msg_queue,
        )
        _S.thread.start()
        _tag_redraw()

    def _finalise(self, context, aborted=False):
        props = context.scene.ai_gen
        props.is_streaming = False
        _S.mode = "idle"

        if self._timer:
            context.window_manager.event_timer_remove(self._timer)
            self._timer = None

        if _S.thread and _S.thread.is_alive():
            _S.thread.abort()
            _S.thread.join(timeout=2)
        _S.thread = None

        if aborted:
            # Try to execute whatever we got
            if _S.current_code and _S.executor:
                _S.executor.try_execute_new(_S.current_code)
            props.status = "⏹ Stopped by user"
            props.progress = ""
            _fit_view_all()

        _tag_redraw()

# ═══════════════════════════════════════════════════
# PANEL
# ═══════════════════════════════════════════════════

class AIGEN_PT_MainPanel(bpy.types.Panel):
    bl_idname = "AIGEN_PT_main"
    bl_label = "AI 3D Model Generator"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "AI Gen"

    def draw(self, context):
        layout = self.layout
        props = context.scene.ai_gen
        streaming = _S.mode != "idle"

        # ── status ──
        status_icon = 'INFO'
        st = props.status
        if "✅" in st or "🎉" in st:
            status_icon = 'CHECKMARK'
        elif "❌" in st:
            status_icon = 'ERROR'
        elif "🤖" in st or "📝" in st or "🧠" in st or "🔄" in st:
            status_icon = 'SORTTIME'

        box = layout.box()
        box.label(text=props.status, icon=status_icon)
        if props.progress:
            box.label(text=props.progress)

        layout.separator()

        # ── connection settings ──
        conn_box = layout.box()
        conn_box.label(text="Connection", icon='URL')

        row = conn_box.row(align=True)
        row.prop(props, "ollama_url", text="")
        row.operator("aigen.check_connection", text="", icon='VIEWZOOM')

        # Model selection as simple text input
        row = conn_box.row(align=True)
        row.prop(props, "model_name", text="")

        # Add a dropdown button to show available models
        if hasattr(_S, 'model_list') and _S.model_list:
            sub = row.row(align=True)
            sub.scale_x = 0.8
            sub.operator_menu_enum(
                "aigen.set_model_from_list", 
                "model", 
                text="", 
                icon='DOWNARROW_HLT'
            )

        row.operator("aigen.refresh_models", text="", icon='FILE_REFRESH')

        if props.available_models:
            conn_box.label(text=f"Available: {props.available_models}",
                        icon='OUTLINER_OB_FONT')

        layout.separator()

        # ── prompt ──
        prompt_box = layout.box()
        prompt_box.label(text="Prompt", icon='TEXT')

        row = prompt_box.row()
        row.enabled = not streaming
        row.prop(props, "prompt", text="")

        # Quick prompts
        qrow = prompt_box.row(align=True)
        qrow.enabled = not streaming
        qrow.scale_y = 0.8
        for label, text in [
            ("Cube", "Create a cube with 0.5m sides"),
            ("Cylinder", "Cylinder radius 0.25m height 0.8m"),
            ("Plate+Holes",
             "Plate 2x1x0.1m with 4 corner bolt holes diameter 0.08m"),
            ("L-Bracket",
             "L-bracket 1x0.8x0.1m with beveled edges"),
        ]:
            op = qrow.operator("aigen.quick_prompt", text=label)
            op.text = text

        layout.separator()

        # ── action buttons ──
        if streaming:
            row = layout.row(align=True)
            row.scale_y = 1.8
            row.operator("aigen.stop", text="⏹  STOP",
                         icon='CANCEL')
        else:
            row = layout.row(align=True)
            row.scale_y = 1.8
            op = row.operator("aigen.generate", text="🚀  Generate",
                              icon='PLAY')
            op.modify_only = False

            op = row.operator("aigen.generate", text="➕  Modify",
                              icon='ADD')
            op.modify_only = True

        layout.separator()

        # ── options ──
        row = layout.row()
        row.prop(props, "autofix", text="Auto-fix errors",
                 icon='TOOL_SETTINGS')

        row = layout.row(align=True)
        row.operator("aigen.clear_scene", text="Clear Scene",
                     icon='TRASH')
        row.operator("aigen.clear_history", text="Clear History",
                     icon='X')

        layout.separator()

        # ── code viewer ──
        row = layout.row()
        row.operator("aigen.view_code", text="View Generated Code",
                     icon='TEXT')

        # Show last few lines of code
        tb = bpy.data.texts.get(CODE_TEXT_NAME)
        if tb:
            code_str = tb.as_string()
            if code_str.strip():
                code_box = layout.box()
                code_box.scale_y = 0.6
                lines = code_str.split("\n")
                # Show last 12 lines
                display_lines = lines[-12:] if len(lines) > 12 else lines
                if len(lines) > 12:
                    code_box.label(text=f"  … ({len(lines) - 12} more lines above)")
                for line in display_lines:
                    # Truncate long lines
                    disp = line[:72] + "…" if len(line) > 72 else line
                    code_box.label(text=disp)

# ═══════════════════════════════════════════════════
# REGISTRATION
# ═══════════════════════════════════════════════════

_classes = [
    AIGEN_PG_Props,
    AIGEN_OT_CheckConnection,
    AIGEN_OT_RefreshModels,
    AIGEN_OT_QuickPrompt,
    AIGEN_OT_ClearHistory,
    AIGEN_OT_ClearScene,
    AIGEN_OT_ViewCode,
    AIGEN_OT_Stop,
    AIGEN_OT_Generate,
    AIGEN_OT_SetModelFromList,
    AIGEN_PT_MainPanel,
]

def register():
    for cls in _classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ai_gen = bpy.props.PointerProperty(type=AIGEN_PG_Props)
    print("[AI-Gen] AI 3D Model Generator registered ✅")
    print("[AI-Gen] Look for 'AI Gen' tab in the 3D Viewport sidebar (N)")

def unregister():
    if _S.thread and _S.thread.is_alive():
        _S.thread.abort()
        _S.thread.join(timeout=2)
    _S.mode = "idle"

    del bpy.types.Scene.ai_gen
    for cls in reversed(_classes):
        bpy.utils.unregister_class(cls)
    print("[AI-Gen] AI 3D Model Generator unregistered")

# Allow running as a script from the Text Editor
if __name__ == "__main__":
    try:
        unregister()
    except Exception:
        pass
    register()