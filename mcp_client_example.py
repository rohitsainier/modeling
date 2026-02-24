# mcp_client_example.py
"""
Example MCP client that connects to the CATIA MCP server.
Use this if you want to integrate with your own application.
"""

import asyncio
import json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_params = StdioServerParameters(
        command="python",
        args=["mcp_server.py"],
    )
    
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            
            # List available tools
            tools = await session.list_tools()
            print("Available tools:")
            for tool in tools.tools:
                print(f"  - {tool.name}: {tool.description[:80]}")
            
            # Create a 3D model!
            result = await session.call_tool(
                "create_3d_model",
                arguments={
                    "prompt": "Create a cylinder with radius 25mm and height 80mm"
                }
            )
            
            print("\nResult:")
            print(json.loads(result.content[0].text))
            
            # Add a feature
            result2 = await session.call_tool(
                "add_feature",
                arguments={
                    "prompt": "Add a 5mm fillet on all top edges"
                }
            )
            print("\nFeature added:")
            print(json.loads(result2.content[0].text))


if __name__ == "__main__":
    asyncio.run(main())