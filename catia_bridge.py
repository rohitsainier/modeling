# catia_bridge.py
"""
Bridge module that connects Python to CATIA V5 via COM automation.
Provides safe execution of generated code inside CATIA.
"""

import win32com.client
import pythoncom
import time
import logging
from typing import Optional, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("CATIABridge")


class CATIABridge:
    """Manages the connection to CATIA V5 and provides helper methods."""
    
    def __init__(self):
        self.catia = None
        self.documents = None
        self.active_document = None
        self.part = None
        self.part_document = None
        self.hybrid_shape_factory = None
        self.shape_factory = None
        
    def connect(self) -> bool:
        """Connect to a running CATIA V5 instance."""
        try:
            pythoncom.CoInitialize()
            self.catia = win32com.client.Dispatch("CATIA.Application")
            self.catia.Visible = True
            self.documents = self.catia.Documents
            logger.info("✅ Connected to CATIA V5")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to connect to CATIA: {e}")
            logger.info("Make sure CATIA V5 is running!")
            return False
    
    def create_new_part(self, name: str = "GeneratedPart") -> bool:
        """Create a new Part document in CATIA."""
        try:
            self.part_document = self.documents.Add("Part")
            self.part = self.part_document.Part
            self.part.Name = name
            
            # Get factories for creating geometry
            self.hybrid_shape_factory = self.part.HybridShapeFactory
            self.shape_factory = self.part.ShapeFactory
            
            logger.info(f"✅ Created new part: {name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create part: {e}")
            return False
    
    def create_new_product(self, name: str = "GeneratedProduct") -> bool:
        """Create a new Product (assembly) document."""
        try:
            self.active_document = self.documents.Add("Product")
            product = self.active_document.Product
            product.PartNumber = name
            logger.info(f"✅ Created new product: {name}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to create product: {e}")
            return False
    
    def get_origin_planes(self) -> Dict[str, Any]:
        """Get the three origin planes (XY, YZ, ZX)."""
        origin_elements = self.part.OriginElements
        return {
            "xy": origin_elements.PlaneXY,
            "yz": origin_elements.PlaneYZ,
            "zx": origin_elements.PlaneZX
        }
    
    def create_sketch_on_plane(self, plane_name: str = "xy"):
        """Create a sketch on a reference plane."""
        planes = self.get_origin_planes()
        plane = planes.get(plane_name, planes["xy"])
        
        bodies = self.part.Bodies
        body = bodies.Item(1)  # Main body
        
        sketches = body.Sketches
        reference = self.part.CreateReferenceFromObject(plane)
        sketch = sketches.Add(reference)
        
        return sketch
    
    def update_part(self):
        """Update/rebuild the part."""
        try:
            self.part.Update()
            logger.info("✅ Part updated successfully")
        except Exception as e:
            logger.error(f"⚠️ Update warning: {e}")
    
    def save_part(self, filepath: str):
        """Save the part document."""
        try:
            self.part_document.SaveAs(filepath)
            logger.info(f"✅ Saved to: {filepath}")
        except Exception as e:
            logger.error(f"❌ Save failed: {e}")
    
    def get_execution_context(self) -> Dict[str, Any]:
        """
        Returns a dictionary of objects that generated code can use.
        This is the 'sandbox' environment for executing LLM-generated code.
        """
        context = {
            "catia": self.catia,
            "documents": self.documents,
            "part_document": self.part_document,
            "part": self.part,
            "hybrid_shape_factory": self.hybrid_shape_factory,
            "shape_factory": self.shape_factory,
            "origin_planes": self.get_origin_planes() if self.part else None,
            # Helper functions
            "create_sketch": self.create_sketch_on_plane,
            "update": self.update_part,
            "save": self.save_part,
            # Utility
            "create_reference": self.part.CreateReferenceFromObject if self.part else None,
        }
        return context
    
    def disconnect(self):
        """Clean up COM connection."""
        try:
            pythoncom.CoUninitialize()
            logger.info("Disconnected from CATIA")
        except:
            pass


# Singleton instance
_bridge = None

def get_bridge() -> CATIABridge:
    global _bridge
    if _bridge is None:
        _bridge = CATIABridge()
    return _bridge