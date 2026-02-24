### `code_executor.py` (Updated for FreeCAD + Mac)

# code_executor.py
"""
Safely validates and executes LLM-generated Python code within the FreeCAD context.
Works on macOS, Linux, and Windows.
"""

import ast
import sys
import re
import traceback
import logging
import time
from datetime import datetime
from typing import Tuple, Optional, Dict, Any, List

from cad_bridge import CADBridge

logger = logging.getLogger("CodeExecutor")

# ═══════════════════════════════════════════════════
# Security
# ═══════════════════════════════════════════════════

BLOCKED_MODULES = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib",
    "platform", "signal",
    "socket", "http", "urllib", "requests",
    "ftplib", "smtplib", "telnetlib",
    "pickle", "shelve", "marshal",
    "ctypes", "cffi", "mmap",
    "code", "codeop", "importlib",
    "glob", "tempfile",
    "inspect", "dis",
})

BLOCKED_BUILTINS = frozenset({
    "exec", "eval", "compile", "__import__",
    "globals", "locals", "breakpoint",
    "exit", "quit", "input",
    "open", "delattr", "setattr",
})

MAX_CODE_LENGTH = 100_000


# ═══════════════════════════════════════════════════
# Validator
# ═══════════════════════════════════════════════════

class CodeValidator:
    """AST-based code safety validator."""

    def validate(self, code: str) -> Tuple[bool, str]:
        """
        Check code for syntax and safety.
        Returns (is_valid, message).
        """
        if len(code) > MAX_CODE_LENGTH:
            return False, f"Code too long: {len(code)} chars (max {MAX_CODE_LENGTH})"

        if not code.strip():
            return False, "Empty code"

        # Syntax
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            return False, f"Syntax error at line {e.lineno}: {e.msg}"

        # Safety
        for node in ast.walk(tree):
            result = self._check_node(node)
            if result is not None:
                return False, result

        return True, "OK"

    def _check_node(self, node: ast.AST) -> Optional[str]:
        """Check a single AST node. Returns error message or None."""

        if isinstance(node, ast.Import):
            for alias in node.names:
                base = alias.name.split(".")[0]
                if base in BLOCKED_MODULES:
                    return f"Blocked import: '{alias.name}'"

        elif isinstance(node, ast.ImportFrom):
            if node.module:
                base = node.module.split(".")[0]
                if base in BLOCKED_MODULES:
                    return f"Blocked import: 'from {node.module}'"

        elif isinstance(node, ast.Call):
            name = self._get_call_name(node)
            if name and name in BLOCKED_BUILTINS:
                return f"Blocked function: '{name}()'"

        elif isinstance(node, ast.Attribute):
            if (node.attr.startswith("__") and node.attr.endswith("__")
                    and node.attr not in {"__name__", "__class__", "__doc__"}):
                return f"Blocked dunder: '.{node.attr}'"

        return None

    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        if isinstance(node.func, ast.Name):
            return node.func.id
        if isinstance(node.func, ast.Attribute):
            return node.func.attr
        return None


# ═══════════════════════════════════════════════════
# Execution Record
# ═══════════════════════════════════════════════════

class ExecutionRecord:
    """Record of one code execution attempt."""

    def __init__(self, code: str, success: bool, message: str,
                 error_traceback: Optional[str] = None, duration: float = 0.0):
        self.timestamp = datetime.now()
        self.code = code
        self.success = success
        self.message = message
        self.error_traceback = error_traceback
        self.duration = duration

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "success": self.success,
            "message": self.message,
            "duration_s": round(self.duration, 2),
            "code_lines": self.code.count("\n") + 1,
            "error": self.error_traceback,
        }


# ═══════════════════════════════════════════════════
# Executor
# ═══════════════════════════════════════════════════

class CodeExecutor:
    """Executes validated code in the FreeCAD context."""

    def __init__(self, bridge: CADBridge):
        self.bridge = bridge
        self.validator = CodeValidator()
        self.execution_history: List[ExecutionRecord] = []
        self.total_executions = 0
        self.successful_executions = 0
        self.failed_executions = 0

    def execute(
        self,
        code: str,
        skip_validation: bool = False,
        description: str = "",
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Validate and execute code.

        Returns:
            (success, message, error_traceback_or_None)
        """
        self.total_executions += 1

        # Validate
        if not skip_validation:
            valid, vmsg = self.validator.validate(code)
            if not valid:
                msg = f"Validation failed: {vmsg}"
                logger.error(f"❌ {msg}")
                self.execution_history.append(ExecutionRecord(code, False, msg))
                self.failed_executions += 1
                return False, msg, None

        # Build namespace
        try:
            namespace = self._build_namespace()
        except Exception as e:
            msg = f"Failed to build context: {e}"
            tb = traceback.format_exc()
            logger.error(f"❌ {msg}")
            self.execution_history.append(ExecutionRecord(code, False, msg, tb))
            self.failed_executions += 1
            return False, msg, tb

        # Execute
        desc = description or f"Execution #{self.total_executions}"
        logger.info(f"▶️  {desc} ({code.count(chr(10))+1} lines)")

        start = time.time()

        try:
            exec(code, namespace)
            duration = time.time() - start

            msg = f"Code executed successfully in {duration:.1f}s"
            logger.info(f"✅ {msg}")

            self.execution_history.append(ExecutionRecord(code, True, msg, duration=duration))
            self.successful_executions += 1
            return True, msg, None

        except Exception as e:
            duration = time.time() - start
            tb = traceback.format_exc()
            summary = self._format_error(e, tb, code)
            msg = f"Execution error: {summary}"

            logger.error(f"❌ {msg}")
            self.execution_history.append(ExecutionRecord(code, False, msg, tb, duration))
            self.failed_executions += 1
            return False, msg, tb

    def _build_namespace(self) -> Dict[str, Any]:
        """Build sandboxed execution namespace."""
        ctx = self.bridge.get_execution_context()

        namespace: Dict[str, Any] = {}

        # FreeCAD objects from bridge
        namespace.update(ctx)

        # Safe built-ins
        import math

        safe = {
            "int": int, "float": float, "str": str, "bool": bool,
            "list": list, "dict": dict, "tuple": tuple, "set": set,
            "type": type, "bytes": bytes,
            "abs": abs, "round": round, "min": min, "max": max,
            "sum": sum, "pow": pow, "divmod": divmod,
            "range": range, "len": len, "enumerate": enumerate,
            "zip": zip, "map": map, "filter": filter,
            "sorted": sorted, "reversed": reversed,
            "any": any, "all": all,
            "repr": repr, "format": format,
            "chr": chr, "ord": ord,
            "print": print,
            "isinstance": isinstance, "hasattr": hasattr, "getattr": getattr,
            "True": True, "False": False, "None": None,
            "math": math,
        }
        namespace.update(safe)

        # Controlled builtins (allow `import math` and `import Part`)
        real_builtins = __builtins__ if isinstance(__builtins__, dict) else __builtins__.__dict__
        # Keep most dangerous builtins out of the sandbox, but retain
        # '__import__' so that FreeCAD and other libraries can function
        # normally. Explicit calls to '__import__' are still blocked by
        # the AST validator above.
        filtered_builtins = {}
        for k, v in real_builtins.items():
            if k in BLOCKED_BUILTINS and k != "__import__":
                continue
            filtered_builtins[k] = v
        namespace["__builtins__"] = filtered_builtins

        return namespace

    def _format_error(self, exc: Exception, tb: str, code: str) -> str:
        """Create a concise error message with line info."""
        etype = type(exc).__name__
        emsg = str(exc)

        match = re.search(r'File ["\']<string>["\'], line (\d+)', tb)
        if match:
            lineno = int(match.group(1))
            lines = code.split("\n")
            if 1 <= lineno <= len(lines):
                return f"{etype}: {emsg} (line {lineno}: `{lines[lineno-1].strip()}`)"

        return f"{etype}: {emsg}"

    # ── History ──

    def get_last_error(self) -> Optional[ExecutionRecord]:
        for r in reversed(self.execution_history):
            if not r.success:
                return r
        return None

    def get_last_success(self) -> Optional[ExecutionRecord]:
        for r in reversed(self.execution_history):
            if r.success:
                return r
        return None

    def get_history(self, limit: int = 10) -> List[Dict]:
        return [r.to_dict() for r in self.execution_history[-limit:]]

    def get_stats(self) -> Dict[str, Any]:
        total = self.total_executions
        return {
            "total": total,
            "success": self.successful_executions,
            "failed": self.failed_executions,
            "rate": f"{self.successful_executions/total*100:.0f}%" if total else "N/A",
        }

    def clear_history(self):
        self.execution_history.clear()


# ═══════════════════════════════════════════════════
# Standalone Validator Test
# ═══════════════════════════════════════════════════

if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] %(message)s")

    print("=" * 60)
    print("  Code Executor — Validator Test (no FreeCAD needed)")
    print("=" * 60)

    v = CodeValidator()

    tests = [
        ("Valid FreeCAD code", True,
         'box = doc.addObject("Part::Box", "B")\nbox.Length = 50\nupdate()'),

        ("Blocked: import os", False,
         "import os\nos.system('ls')"),

        ("Blocked: subprocess", False,
         "import subprocess\nsubprocess.run(['ls'])"),

        ("Blocked: eval", False,
         "eval('1+1')"),

        ("Blocked: open file", False,
         "f = open('x.txt','w')"),

        ("Safe: import math", True,
         "import math\nx = math.pi\nprint(x)"),

        ("Syntax error", False,
         "def broken(\n    pass"),

        ("Loop code", True,
         'for i in range(4):\n    b = doc.addObject("Part::Box", f"B_{i}")\nupdate()'),

        ("Blocked: network", False,
         "from urllib.request import urlopen"),
    ]

    passed = failed = 0
    for desc, should_pass, code in tests:
        ok, msg = v.validate(code.strip())
        correct = (ok == should_pass)
        icon = "✅" if correct else "❌"
        print(f"  {icon} {desc}: {'PASS' if correct else 'FAIL'}")
        if not correct:
            print(f"      Expected valid={should_pass}, got valid={ok}: {msg}")
            failed += 1
        else:
            if not ok:
                print(f"      Blocked: {msg}")
            passed += 1

    print(f"\n  Results: {passed}/{len(tests)} passed")