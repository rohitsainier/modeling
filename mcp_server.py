# mcp_server.py
"""
MCP (Model Context Protocol) Server that orchestrates:
  - Receiving user prompts
  - Generating code via Ollama
  - Executing code in CATIA
  - Returning results
"""

from mcp.server.fastmcp import FastMCP
import logging
import json
from typing import Optional

from cad_bridge import CADBridge, get_bridge
from ollama_generator_mac import OllamaGenerator, create_generator
from code_executor import CodeExecutor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MCPServer")

# Initialize MCP Server
mcp = FastMCP(
    "catia-3d-modeler",
    description="Generate 3D models in CATIA V5 using natural language prompts"
)

# Global state
bridge: Optional[CATIABridge] = None
generator: Optional[OllamaGenerator] = None
executor: Optional[CodeExecutor] = None


def ensure_initialized():
    """Ensure all components are initialized."""
    global bridge, generator, executor
    
    if bridge is None:
        bridge = get_bridge()
        if not bridge.connect():
            raise RuntimeError("Cannot connect to CATIA. Is it running?")
    
    if generator is None:
        generator = create_generator("qwen3-coder:480b-cloud")
    
    if executor is None:
        executor = CodeExecutor(bridge)


# ═══════════════════════════════════════════
# MCP TOOLS
# ═══════════════════════════════════════════

@mcp.tool()
def create_3d_model(prompt: str) -> str:
    """
    Create a 3D model in CATIA from a natural language description.
    
    This tool takes a description of a 3D part or feature and generates
    the appropriate CATIA automation code, then executes it.
    
    Args:
        prompt: Natural language description of the 3D model to create.
                Examples:
                - "Create a cylinder with radius 30mm and height 100mm"
                - "Make a rectangular plate 200x100x10mm with 4 corner holes"
                - "Build a simple gear with 20 teeth"
    
    Returns:
        JSON string with status, generated code, and any messages.
    """
    ensure_initialized()
    
    # Create a new part for the model
    bridge.create_new_part("AI_Generated_Part")
    
    # Generate code
    code = generator.generate_code(prompt)
    
    # Execute
    success, message, error = executor.execute(code)
    
    result = {
        "success": success,
        "message": message,
        "generated_code": code,
    }
    
    # If failed, try to self-heal once
    if not success and error:
        logger.info("🔄 Attempting auto-fix...")
        fixed_code = generator.refine_code(code, error)
        success2, message2, error2 = executor.execute(fixed_code)
        
        result["auto_fix_attempted"] = True
        result["fixed_code"] = fixed_code
        result["fix_success"] = success2
        result["fix_message"] = message2
    
    return json.dumps(result, indent=2)


@mcp.tool()
def add_feature(prompt: str) -> str:
    """
    Add a feature to the current CATIA part.
    
    Unlike create_3d_model, this does NOT create a new part.
    It adds features to whatever part is currently active.
    
    Args:
        prompt: Description of the feature to add.
                Examples:
                - "Add a 5mm fillet to all edges"
                - "Cut a 20mm diameter hole through the center"
                - "Add a 10mm chamfer to the top edges"
    
    Returns:
        JSON string with status and details.
    """
    ensure_initialized()
    
    if bridge.part is None:
        return json.dumps({
            "success": False,
            "message": "No active part. Use create_3d_model first."
        })
    
    # Generate code (with context that a part already exists)
    enhanced_prompt = (
        f"The part already exists with features. "
        f"Add the following to the EXISTING part: {prompt}"
    )
    code = generator.generate_code(enhanced_prompt)
    
    success, message, error = executor.execute(code)
    
    return json.dumps({
        "success": success,
        "message": message,
        "generated_code": code,
    }, indent=2)


@mcp.tool()
def execute_catia_code(code: str) -> str:
    """
    Directly execute Python code in the CATIA context.
    
    For advanced users who want to run their own CATIA automation code.
    The code has access to: catia, part, sf, hsf, origin_planes, etc.
    
    Args:
        code: Python code to execute in the CATIA context.
    
    Returns:
        JSON string with execution results.
    """
    ensure_initialized()
    
    success, message, error = executor.execute(code)
    
    return json.dumps({
        "success": success,
        "message": message,
        "error": error,
    }, indent=2)


@mcp.tool()
def save_current_model(filepath: str) -> str:
    """
    Save the current CATIA model to a file.
    
    Args:
        filepath: Full path where to save the file (e.g., "C:/Models/part1.CATPart")
    
    Returns:
        Status message.
    """
    ensure_initialized()
    
    try:
        bridge.save_part(filepath)
        return json.dumps({"success": True, "message": f"Saved to {filepath}"})
    except Exception as e:
        return json.dumps({"success": False, "message": str(e)})


@mcp.tool()
def new_part(name: str = "NewPart") -> str:
    """
    Create a new empty CATIA part document.
    
    Args:
        name: Name for the new part.
    
    Returns:
        Status message.
    """
    ensure_initialized()
    
    success = bridge.create_new_part(name)
    return json.dumps({
        "success": success,
        "message": f"Created new part: {name}" if success else "Failed to create part"
    })


@mcp.tool()
def get_model_info() -> str:
    """
    Get information about the current CATIA model.
    
    Returns:
        JSON with current model details (features, bodies, etc.)
    """
    ensure_initialized()
    
    if bridge.part is None:
        return json.dumps({"message": "No active part"})
    
    try:
        part = bridge.part
        bodies = part.Bodies
        
        info = {
            "part_name": part.Name,
            "num_bodies": bodies.Count,
            "bodies": []
        }
        
        for i in range(1, bodies.Count + 1):
            body = bodies.Item(i)
            body_info = {
                "name": body.Name,
                "num_shapes": body.Shapes.Count if hasattr(body, 'Shapes') else 0,
            }
            
            # List features/shapes
            if hasattr(body, 'Shapes'):
                shapes = []
                for j in range(1, body.Shapes.Count + 1):
                    shape = body.Shapes.Item(j)
                    shapes.append(shape.Name)
                body_info["shapes"] = shapes
            
            info["bodies"].append(body_info)
        
        return json.dumps(info, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ═══════════════════════════════════════════
# MCP RESOURCES
# ═══════════════════════════════════════════

@mcp.resource("catia://status")
def get_catia_status() -> str:
    """Get current CATIA connection status."""
    try:
        if bridge and bridge.catia:
            return json.dumps({
                "connected": True,
                "visible": bridge.catia.Visible,
                "documents_count": bridge.documents.Count if bridge.documents else 0,
            })
    except:
        pass
    
    return json.dumps({"connected": False})


@mcp.resource("catia://examples")
def get_examples() -> str:
    """Get example prompts for creating 3D models."""
    examples = [
        {
            "prompt": "Create a simple cube with 50mm sides",
            "description": "Basic box/cube shape"
        },
        {
            "prompt": "Create a cylinder with radius 25mm and height 80mm",
            "description": "Basic cylinder"
        },
        {
            "prompt": "Create a rectangular plate 200x100x10mm with a centered 30mm diameter through-hole",
            "description": "Plate with hole"
        },
        {
            "prompt": "Create an L-bracket: vertical plate 100x80x10mm, horizontal plate extending 60mm, with 5mm fillets at the junction",
            "description": "L-shaped bracket with fillets"
        },
        {
            "prompt": "Create a hollow cylinder (pipe): outer diameter 50mm, inner diameter 40mm, length 100mm",
            "description": "Hollow pipe shape"
        },
        {
            "prompt": "Create a flanged bolt: M10 hex head (17mm across flats, 7mm tall) with 40mm long shank",
            "description": "Complex bolt shape"
        },
    ]
    return json.dumps(examples, indent=2)


# ═══════════════════════════════════════════
# MCP PROMPTS (Templates)
# ═══════════════════════════════════════════

@mcp.prompt()
def mechanical_part(description: str) -> str:
    """Template prompt for creating mechanical parts."""
    return f"""Create a mechanical part with the following specifications:

{description}

Requirements:
- Use standard mechanical engineering practices
- Add appropriate fillets (2-3mm) on sharp edges
- Ensure the part is manufacturable
- Use reasonable tolerances
- Center the part on the origin"""


@mcp.prompt()
def parametric_shape(
    shape_type: str,
    dimensions: str,
    features: str = "none"
) -> str:
    """Template for parametric shapes with specific dimensions."""
    return f"""Create a {shape_type} with the following dimensions:
{dimensions}

Additional features: {features}

Make the geometry parametric where possible."""


# ═══════════════════════════════════════════
# SERVER ENTRY POINT
# ═══════════════════════════════════════════

if __name__ == "__main__":
    logger.info("🚀 Starting CATIA 3D Modeler MCP Server...")
    mcp.run(transport="stdio")