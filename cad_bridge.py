# cad_bridge.py
"""
CAD Bridge — connects Python to FreeCAD for 3D model generation.
Works on macOS, Linux, and Windows.

Replaces the Windows-only CATIA COM bridge with FreeCAD's Python API.
"""

import sys
import logging
import os
from typing import Optional, Dict, Any

logger = logging.getLogger("CADBridge")

# ── Find and import FreeCAD ──
FREECAD_PATHS = [
    # macOS (Homebrew)
    "/Applications/FreeCAD.app/Contents/Resources/lib",
    "/Applications/FreeCAD.app/Contents/Resources/lib/python3.11/site-packages",
    "/opt/homebrew/lib/python3.11/site-packages",
    # macOS (official DMG)
    "/Applications/FreeCAD.app/Contents/lib",
    # Linux
    "/usr/lib/freecad/lib",
    "/usr/lib/freecad-python3/lib",
    "/usr/share/freecad/lib",
    "/usr/lib/freecad/Mod",
    "/snap/freecad/current/usr/lib/freecad/lib",
    # Windows
    "C:/Program Files/FreeCAD 0.21/bin",
    "C:/Program Files/FreeCAD 0.21/lib",
]


def _find_freecad():
    """Locate FreeCAD's Python modules and add to sys.path."""
    # Check if already importable
    try:
        import FreeCAD
        return True
    except ImportError:
        pass

    # Search common paths
    for path in FREECAD_PATHS:
        if os.path.exists(path) and path not in sys.path:
            sys.path.append(path)

    # Also check FREECAD_PATH environment variable
    env_path = os.environ.get("FREECAD_PATH")
    if env_path and os.path.exists(env_path):
        if env_path not in sys.path:
            sys.path.append(env_path)
        lib_path = os.path.join(env_path, "lib")
        if os.path.exists(lib_path) and lib_path not in sys.path:
            sys.path.append(lib_path)

    try:
        import FreeCAD
        return True
    except ImportError:
        return False


class CADBridge:
    """
    Manages connection to FreeCAD and provides helper methods
    for creating 3D geometry programmatically.
    """

    def __init__(self):
        self.FreeCAD = None
        self.Part = None
        self.document = None
        self.active_body = None
        self._connected = False

    def connect(self) -> bool:
        """Initialize FreeCAD Python environment."""
        try:
            if not _find_freecad():
                logger.error(
                    "❌ Cannot find FreeCAD. Set FREECAD_PATH environment variable.\n"
                    "   Example: export FREECAD_PATH=/Applications/FreeCAD.app/Contents/Resources"
                )
                return False

            import FreeCAD
            import Part

            self.FreeCAD = FreeCAD
            self.Part = Part

            self._connected = True
            logger.info(f"✅ Connected to FreeCAD {FreeCAD.Version()[0]}.{FreeCAD.Version()[1]}")
            return True

        except ImportError as e:
            logger.error(f"❌ FreeCAD import failed: {e}")
            logger.error(
                "Install FreeCAD: brew install --cask freecad\n"
                "Or set: export FREECAD_PATH=/path/to/freecad/lib"
            )
            return False
        except Exception as e:
            logger.error(f"❌ FreeCAD connection error: {e}")
            return False

    def create_new_part(self, name: str = "GeneratedPart") -> bool:
        """Create a new FreeCAD document with a Part."""
        try:
            # Close existing doc if any
            if self.document:
                try:
                    self.FreeCAD.closeDocument(self.document.Name)
                except Exception:
                    pass

            self.document = self.FreeCAD.newDocument(name)
            logger.info(f"✅ Created new document: {name}")
            return True

        except Exception as e:
            logger.error(f"❌ Failed to create document: {e}")
            return False

    def update_part(self):
        """Recompute the document."""
        try:
            if self.document:
                self.document.recompute()
                logger.info("✅ Document recomputed")
        except Exception as e:
            logger.error(f"⚠️ Recompute warning: {e}")

    def save_part(self, filepath: str):
        """Save the document to a file."""
        try:
            if self.document:
                # Determine format from extension
                ext = os.path.splitext(filepath)[1].lower()

                if ext == ".fcstd":
                    self.document.saveAs(filepath)
                elif ext in (".step", ".stp"):
                    self._export_step(filepath)
                elif ext in (".stl",):
                    self._export_stl(filepath)
                elif ext in (".obj",):
                    self._export_obj(filepath)
                else:
                    # Default to FreeCAD native format
                    if not filepath.endswith(".FCStd"):
                        filepath += ".FCStd"
                    self.document.saveAs(filepath)

                logger.info(f"✅ Saved to: {filepath}")
            else:
                logger.error("No document to save")
        except Exception as e:
            logger.error(f"❌ Save failed: {e}")

    def _export_step(self, filepath: str):
        """Export as STEP file."""
        shapes = []
        for obj in self.document.Objects:
            if hasattr(obj, "Shape"):
                shapes.append(obj.Shape)
        if shapes:
            import Part
            compound = Part.makeCompound(shapes)
            compound.exportStep(filepath)

    def _export_stl(self, filepath: str):
        """Export as STL file."""
        import Mesh
        meshes = []
        for obj in self.document.Objects:
            if hasattr(obj, "Shape"):
                mesh = Mesh.Mesh(obj.Shape.tessellate(0.1))
                meshes.append(mesh)
        if meshes:
            combined = meshes[0]
            for m in meshes[1:]:
                combined.addMesh(m)
            combined.write(filepath)

    def _export_obj(self, filepath: str):
        """Export as OBJ file."""
        self._export_stl(filepath.replace(".obj", ".stl"))

    def get_execution_context(self) -> Dict[str, Any]:
        """
        Returns the namespace that generated code runs in.
        Maps CATIA-like concepts to FreeCAD equivalents.
        """
        import FreeCAD
        import Part

        context = {
            # Core FreeCAD modules
            "FreeCAD": FreeCAD,
            "App": FreeCAD,
            "Part": Part,
            "doc": self.document,
            "document": self.document,

            # Helper functions
            "update": self.update_part,
            "save": self.save_part,
            "recompute": self.update_part,

            # Part module shortcuts for creating shapes
            "makeBox": Part.makeBox,
            "makeCylinder": Part.makeCylinder,
            "makeCone": Part.makeCone,
            "makeSphere": Part.makeSphere,
            "makeTorus": Part.makeTorus,

            # Vector helper
            "Vector": FreeCAD.Vector,
            "Placement": FreeCAD.Placement,
            "Rotation": FreeCAD.Rotation,
        }

        return context

    def disconnect(self):
        """Clean up."""
        logger.info("Disconnected from FreeCAD")

    @property
    def is_connected(self) -> bool:
        return self._connected


# ── Singleton ──
_bridge = None


def get_bridge() -> CADBridge:
    global _bridge
    if _bridge is None:
        _bridge = CADBridge()
    return _bridge