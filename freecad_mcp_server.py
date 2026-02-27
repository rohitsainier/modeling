#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
FreeCAD MCP Bridge Server
=========================
Connects to the FreeCAD addon socket and exposes MCP tools.

Claude Desktop config (~/.config/claude/claude_desktop_config.json):
{
  "mcpServers": {
    "freecad": {
      "command": "python",
      "args": ["/absolute/path/to/freecad_mcp_server.py"]
    }
  }
}
"""

import socket
import json
import logging
import sys
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    stream=sys.stderr,          # MCP uses stdout for protocol
)
logger = logging.getLogger("freecad-mcp")

try:
    from mcp.server.fastmcp import FastMCP
except ImportError:
    print(
        "ERROR: 'mcp' package not installed.\n"
        "  pip install mcp\n",
        file=sys.stderr,
    )
    sys.exit(1)


# ═══════════════════════════════════════════════════
# FREECAD SOCKET CLIENT
# ═══════════════════════════════════════════════════

class FreeCADConnection:
    """
    Connects to the FreeCADMCP addon's TCP socket server.
    Sends JSON commands and receives JSON responses.
    """

    def __init__(self, host: str = "localhost", port: int = 9876):
        self.host = host
        self.port = port
        self.sock = None

    def connect(self):
        if self.sock:
            self.disconnect()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        self.sock.settimeout(60)
        logger.info(f"Connected to FreeCAD on {self.host}:{self.port}")

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except Exception:
                pass
            self.sock = None

    def _ensure(self):
        if self.sock is None:
            self.connect()

    def send_command(self, cmd_type: str, **params) -> dict:
        """Send a command to FreeCAD and return the parsed response."""
        self._ensure()
        payload = json.dumps({"type": cmd_type, "params": params})

        try:
            self.sock.sendall(payload.encode("utf-8"))
            return self._recv_json()
        except (ConnectionError, BrokenPipeError, OSError) as e:
            logger.warning(f"Connection lost ({e}), reconnecting…")
            self.connect()
            self.sock.sendall(payload.encode("utf-8"))
            return self._recv_json()

    def _recv_json(self) -> dict:
        buf = b""
        while True:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("FreeCAD closed connection")
            buf += chunk
            try:
                return json.loads(buf.decode("utf-8"))
            except json.JSONDecodeError:
                continue      # partial — keep reading


# ═══════════════════════════════════════════════════
# HELPER
# ═══════════════════════════════════════════════════

fc = FreeCADConnection()


def _call(cmd: str, **params) -> str:
    """Call FreeCAD, return pretty-printed JSON result."""
    resp = fc.send_command(cmd, **params)
    return json.dumps(resp, indent=2)


def _strip_none(**kw) -> dict:
    """Remove None-valued keys so FreeCAD gets clean params."""
    return {k: v for k, v in kw.items() if v is not None}


# ═══════════════════════════════════════════════════
# MCP SERVER + TOOLS
# ═══════════════════════════════════════════════════

mcp = FastMCP(
    "freecad-mcp"
)


# ── Scene ──────────────────────────────────────────

@mcp.tool()
def get_scene_info() -> str:
    """
    Return the active FreeCAD document name and a list of every
    object with its type, position, dimensions, and visibility.
    """
    return _call("get_scene_info")


@mcp.tool()
def get_object_info(name: str) -> str:
    """
    Detailed info for one object: dimensions, volume, surface area,
    bounding box, number of faces/edges/vertices, and all properties.

    Args:
        name: Object name or label.
    """
    return _call("get_object_info", name=name)


# ── Create ─────────────────────────────────────────

@mcp.tool()
def create_object(
    type: str,
    name: str = None,
    location: list = None,
    rotation: list = None,
    length: float = None,
    width: float = None,
    height: float = None,
    radius: float = None,
    radius1: float = None,
    radius2: float = None,
) -> str:
    """
    Create a 3D primitive in FreeCAD.

    Args:
        type:     BOX | CYLINDER | SPHERE | CONE | TORUS
        name:     Label for the object.
        location: [x, y, z] in mm.
        rotation: [ax, ay, az, angle_deg] or [yaw, pitch, roll].
        length:   Box length (mm).
        width:    Box width (mm).
        height:   Box/Cylinder/Cone height (mm).
        radius:   Cylinder/Sphere radius (mm).
        radius1:  Cone bottom / Torus major radius (mm).
        radius2:  Cone top / Torus minor radius (mm).
    """
    p = _strip_none(
        type=type, name=name, location=location, rotation=rotation,
        length=length, width=width, height=height,
        radius=radius, radius1=radius1, radius2=radius2,
    )
    return _call("create_object", **p)


# ── Modify ─────────────────────────────────────────

@mcp.tool()
def modify_object(
    name: str,
    location: list = None,
    rotation: list = None,
    visible: bool = None,
    label: str = None,
    length: float = None,
    width: float = None,
    height: float = None,
    radius: float = None,
    radius1: float = None,
    radius2: float = None,
) -> str:
    """
    Modify an existing object's placement, dimensions, or visibility.

    Args:
        name:   Object name or label to modify.
        (other args same as create_object)
    """
    p = _strip_none(
        name=name, location=location, rotation=rotation,
        visible=visible, label=label,
        length=length, width=width, height=height,
        radius=radius, radius1=radius1, radius2=radius2,
    )
    return _call("modify_object", **p)


# ── Delete ─────────────────────────────────────────

@mcp.tool()
def delete_object(name: str) -> str:
    """
    Delete an object from the document.

    Args:
        name: Object name or label.
    """
    return _call("delete_object", name=name)


# ── Execute Code ──────────────────────────────────

@mcp.tool()
def execute_code(code: str) -> str:
    """
    Execute arbitrary Python code inside FreeCAD.

    Pre-defined variables in the execution namespace:
      FreeCAD, App, Part, doc, Vector, Placement, Rotation, math

    IMPORTANT:
      - Do NOT import FreeCAD or Part (already available).
      - Do NOT create a document — `doc` is the active document.
      - Call doc.recompute() at the end.
      - All measurements in mm.

    Example:
        box = doc.addObject("Part::Box", "Plate")
        box.Length = 200
        box.Width = 100
        box.Height = 10
        doc.recompute()

    Args:
        code: Python source code to execute.
    """
    return _call("execute_code", code=code)


# ── Boolean Ops ────────────────────────────────────

@mcp.tool()
def boolean_operation(
    operation: str,
    base: str,
    tool: str,
    name: str = None,
) -> str:
    """
    Boolean operation between two objects.

    Args:
        operation: cut | fuse | common
        base:      Base object name/label.
        tool:      Tool object name/label.
        name:      Label for the result.
    """
    p = _strip_none(operation=operation, base=base, tool=tool, name=name)
    return _call("boolean_operation", **p)


# ── Fillet / Chamfer ───────────────────────────────

@mcp.tool()
def fillet_edges(name: str, radius: float = 1.0) -> str:
    """
    Fillet (round) ALL edges of an object.

    Args:
        name:   Object name/label.
        radius: Fillet radius in mm.
    """
    return _call("fillet_edges", name=name, radius=radius)


@mcp.tool()
def chamfer_edges(name: str, size: float = 1.0) -> str:
    """
    Chamfer ALL edges of an object.

    Args:
        name: Object name/label.
        size: Chamfer size in mm.
    """
    return _call("chamfer_edges", name=name, size=size)


# ── Color ──────────────────────────────────────────

@mcp.tool()
def set_color(name: str, color: list = None) -> str:
    """
    Set the display color of an object.

    Args:
        name:  Object name/label.
        color: [r, g, b] 0-1 floats or 0-255 ints.
               Optional 4th value = transparency.
    """
    return _call("set_color", name=name, color=color or [0.5, 0.5, 0.5])


# ── Export ─────────────────────────────────────────

@mcp.tool()
def export_model(filepath: str, format: str = None) -> str:
    """
    Export visible objects to a file.

    Args:
        filepath: Output path (e.g. /tmp/part.step).
        format:   step | stl | iges | fcstd | brep
                  (auto-detected from extension if omitted).
    """
    p = _strip_none(filepath=filepath, format=format)
    return _call("export_model", **p)


# ── View ───────────────────────────────────────────

@mcp.tool()
def fit_view() -> str:
    """Zoom the 3D view to fit all objects."""
    return _call("fit_view")


@mcp.tool()
def capture_view(
    filepath: str = None,
    width: int = 800,
    height: int = 600,
) -> str:
    """
    Save a screenshot of the current 3D view.

    Args:
        filepath: Output PNG path (default: temp file).
        width:    Image width px.
        height:   Image height px.
    """
    p = _strip_none(filepath=filepath, width=width, height=height)
    return _call("capture_view", **p)


# ── Document ──────────────────────────────────────

@mcp.tool()
def new_document(name: str = "MCP_Model") -> str:
    """Create a new empty FreeCAD document."""
    return _call("new_document", name=name)


@mcp.tool()
def clear_document() -> str:
    """Remove ALL objects from the active document."""
    return _call("clear_document")


# ═══════════════════════════════════════════════════
# MCP RESOURCES (context the LLM can read)
# ═══════════════════════════════════════════════════

@mcp.resource("freecad://scene")
def scene_resource() -> str:
    """Live snapshot of the current FreeCAD scene."""
    try:
        return _call("get_scene_info")
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.resource("freecad://examples")
def examples_resource() -> str:
    """Example prompts for 3D model creation."""
    return json.dumps([
        {"prompt": "Create a box 50×30×10 mm",
         "tool": "create_object", "type": "BOX"},
        {"prompt": "Cylinder radius 25 mm, height 80 mm",
         "tool": "create_object", "type": "CYLINDER"},
        {"prompt": "Plate 200×100×10 with 4 corner holes Ø8",
         "tool": "execute_code"},
        {"prompt": "Subtract a sphere from a cube",
         "tools": ["create_object", "boolean_operation"]},
        {"prompt": "L-bracket with fillets",
         "tools": ["execute_code", "fillet_edges"]},
        {"prompt": "Export the model as STEP",
         "tool": "export_model"},
    ], indent=2)


# ═══════════════════════════════════════════════════
# MCP PROMPTS (reusable templates)
# ═══════════════════════════════════════════════════

@mcp.prompt()
def mechanical_part(description: str) -> str:
    """Guided prompt for creating a mechanical part."""
    return (
        f"Create a mechanical part in FreeCAD:\n\n"
        f"{description}\n\n"
        "Guidelines:\n"
        "- All dimensions in mm\n"
        "- Add 2-3 mm fillets on sharp edges where practical\n"
        "- Center the part on the origin\n"
        "- Hide intermediate boolean shapes\n"
        "- Use descriptive labels for every object\n"
        "Use the available FreeCAD MCP tools."
    )


@mcp.prompt()
def from_scratch(description: str) -> str:
    """Generate a complete model from a text description."""
    return (
        f"Build the following 3D model step-by-step:\n\n"
        f"{description}\n\n"
        "Use create_object for primitives, boolean_operation for "
        "cuts/joins, fillet_edges for rounds, and set_color for "
        "appearance. If the geometry is complex, use execute_code "
        "with raw FreeCAD Python."
    )


# ═══════════════════════════════════════════════════
# ENTRY POINT
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info("Starting FreeCAD MCP bridge server…")
    logger.info("Make sure FreeCADMCP.FCMacro is running inside FreeCAD")
    mcp.run(transport="stdio")