# main_cli.py
"""
Standalone CLI application - the simplest way to use the system.
No MCP client needed - just run this script directly.
"""

import sys
import json
import logging
from catia_bridge import CATIABridge, get_bridge
from ollama_generator import OllamaGenerator, create_generator
from code_executor import CodeExecutor

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(name)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger("Main")

# ─── ANSI Colors ───
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def print_banner():
    print(f"""{CYAN}{BOLD}
╔══════════════════════════════════════════════════╗
║   🏭 CATIA 3D Model Generator                    ║
║   Powered by Ollama + Python COM Automation      ║
║                                                  ║
║   Type a description → Get a 3D model in CATIA   ║
╚══════════════════════════════════════════════════╝{RESET}
""")


def print_help():
    print(f"""
{BOLD}Commands:{RESET}
  {CYAN}Just type a description{RESET}  → Creates a NEW part with the described model
  {CYAN}/add <description>{RESET}      → Add feature to current part  
  {CYAN}/code{RESET}                   → Show last generated code
  {CYAN}/run <code>{RESET}             → Execute custom CATIA code
  {CYAN}/save <path>{RESET}            → Save current part
  {CYAN}/info{RESET}                   → Show current part info
  {CYAN}/model <name>{RESET}           → Switch Ollama model
  {CYAN}/new <name>{RESET}             → Create new empty part
  {CYAN}/retry{RESET}                  → Retry last failed generation
  {CYAN}/clear{RESET}                  → Clear conversation history
  {CYAN}/help{RESET}                   → Show this help
  {CYAN}/quit{RESET}                   → Exit

{BOLD}Example prompts:{RESET}
  • Create a cylinder with radius 30mm and height 100mm
  • Make a rectangular plate 200x100x10mm with 4 corner holes of 8mm diameter
  • Build a simple bracket: L-shape, 5mm thick, 100mm tall, 60mm base
  • Create a hex nut M12
""")


def main():
    print_banner()
    
    # ─── Initialize Components ───
    print(f"{YELLOW}Initializing...{RESET}")
    
    # 1. Connect to CATIA
    bridge = get_bridge()
    if not bridge.connect():
        print(f"{RED}ERROR: Cannot connect to CATIA V5!{RESET}")
        print("Please make sure CATIA V5 is running and try again.")
        sys.exit(1)
    
    # 2. Initialize Ollama generator
    try:
        model_name = "qwen2.5-coder:14b"  # Change this to your preferred model
        generator = create_generator(model_name)
    except Exception as e:
        print(f"{RED}ERROR: Cannot connect to Ollama: {e}{RESET}")
        print("Make sure Ollama is running (ollama serve)")
        sys.exit(1)
    
    # 3. Create executor
    executor = CodeExecutor(bridge)
    
    print(f"{GREEN}✅ All systems ready!{RESET}")
    print_help()
    
    last_code = ""
    last_prompt = ""
    
    # ─── Main Loop ───
    while True:
        try:
            user_input = input(f"\n{BOLD}{CYAN}🏭 Describe your model ▶ {RESET}").strip()
            
            if not user_input:
                continue
            
            # ─── Command Handling ───
            if user_input.startswith("/"):
                cmd_parts = user_input.split(maxsplit=1)
                cmd = cmd_parts[0].lower()
                arg = cmd_parts[1] if len(cmd_parts) > 1 else ""
                
                if cmd in ("/quit", "/exit", "/q"):
                    print(f"{YELLOW}Goodbye! 👋{RESET}")
                    bridge.disconnect()
                    break
                
                elif cmd == "/help":
                    print_help()
                
                elif cmd == "/code":
                    if last_code:
                        print(f"\n{BOLD}Last generated code:{RESET}")
                        print(f"{CYAN}{last_code}{RESET}")
                    else:
                        print("No code generated yet.")
                
                elif cmd == "/new":
                    name = arg or "NewPart"
                    bridge.create_new_part(name)
                    print(f"{GREEN}Created new part: {name}{RESET}")
                
                elif cmd == "/save":
                    if arg:
                        bridge.save_part(arg)
                    else:
                        print("Usage: /save C:/path/to/file.CATPart")
                
                elif cmd == "/info":
                    if bridge.part:
                        try:
                            part = bridge.part
                            bodies = part.Bodies
                            print(f"\n{BOLD}Part: {part.Name}{RESET}")
                            for i in range(1, bodies.Count + 1):
                                body = bodies.Item(i)
                                print(f"  Body: {body.Name}")
                                if hasattr(body, 'Shapes'):
                                    for j in range(1, body.Shapes.Count + 1):
                                        print(f"    └─ {body.Shapes.Item(j).Name}")
                        except Exception as e:
                            print(f"Error getting info: {e}")
                    else:
                        print("No active part.")
                
                elif cmd == "/add":
                    if not arg:
                        print("Usage: /add <feature description>")
                        continue
                    
                    if bridge.part is None:
                        print(f"{RED}No active part. Create one first!{RESET}")
                        continue
                    
                    enhanced = f"Add to the EXISTING part: {arg}"
                    print(f"{YELLOW}🤖 Generating code...{RESET}")
                    code = generator.generate_code(enhanced)
                    last_code = code
                    
                    print(f"{YELLOW}▶️ Executing...{RESET}")
                    success, msg, error = executor.execute(code)
                    
                    if success:
                        print(f"{GREEN}{msg}{RESET}")
                    else:
                        print(f"{RED}{msg}{RESET}")
                        _try_autofix(generator, executor, code, error)
                
                elif cmd == "/model":
                    if arg:
                        try:
                            generator = create_generator(arg)
                            print(f"{GREEN}Switched to model: {arg}{RESET}")
                        except Exception as e:
                            print(f"{RED}Failed to switch model: {e}{RESET}")
                    else:
                        print(f"Current model: {generator.model}")
                        print("Usage: /model <model_name>")
                
                elif cmd == "/retry":
                    if last_prompt:
                        user_input = last_prompt
                        # Fall through to normal processing
                    else:
                        print("Nothing to retry.")
                        continue
                
                elif cmd == "/clear":
                    generator.clear_history()
                    print(f"{GREEN}History cleared.{RESET}")
                
                elif cmd == "/run":
                    if arg:
                        success, msg, error = executor.execute(arg)
                        print(f"{GREEN if success else RED}{msg}{RESET}")
                    else:
                        print("Usage: /run <python code>")
                
                else:
                    print(f"Unknown command: {cmd}. Type /help for help.")
                
                if cmd != "/retry":
                    continue
            
            # ─── Normal Model Generation ───
            last_prompt = user_input
            
            # Create new part
            print(f"{YELLOW}📐 Creating new part...{RESET}")
            bridge.create_new_part("AI_Model")
            
            # Generate code
            print(f"{YELLOW}🤖 Generating CATIA code with Ollama...{RESET}")
            code = generator.generate_code(user_input)
            last_code = code
            
            # Show generated code
            print(f"\n{BOLD}Generated Code:{RESET}")
            print(f"{CYAN}{'─' * 50}")
            for i, line in enumerate(code.split('\n'), 1):
                print(f"  {i:3d} │ {line}")
            print(f"{'─' * 50}{RESET}")
            
            # Confirm execution
            confirm = input(f"\n{YELLOW}Execute this code? [Y/n/edit]: {RESET}").strip().lower()
            
            if confirm in ('n', 'no'):
                print("Cancelled.")
                continue
            
            # Execute
            print(f"\n{YELLOW}▶️ Executing in CATIA...{RESET}")
            success, message, error = executor.execute(code)
            
            if success:
                print(f"\n{GREEN}{BOLD}🎉 {message}{RESET}")
                print(f"{GREEN}Check CATIA to see your 3D model!{RESET}")
            else:
                print(f"\n{RED}{message}{RESET}")
                
                # Auto-fix attempt
                fix = input(f"{YELLOW}Attempt auto-fix? [Y/n]: {RESET}").strip().lower()
                if fix not in ('n', 'no'):
                    _try_autofix(generator, executor, code, error)
        
        except KeyboardInterrupt:
            print(f"\n{YELLOW}Use /quit to exit.{RESET}")
        except Exception as e:
            print(f"{RED}Unexpected error: {e}{RESET}")
            logger.exception("Unexpected error in main loop")


def _try_autofix(generator, executor, original_code, error):
    """Attempt to fix failed code using the LLM."""
    print(f"{YELLOW}🔄 Asking Ollama to fix the code...{RESET}")
    fixed_code = generator.refine_code(original_code, error)
    
    print(f"\n{BOLD}Fixed Code:{RESET}")
    print(f"{CYAN}{fixed_code[:500]}...{RESET}")
    
    success, msg, err = executor.execute(fixed_code)
    if success:
        print(f"{GREEN}🎉 Auto-fix successful!{RESET}")
    else:
        print(f"{RED}Auto-fix also failed: {msg}{RESET}")
        print("Try rephrasing your description or use /code to see what was generated.")


if __name__ == "__main__":
    main()