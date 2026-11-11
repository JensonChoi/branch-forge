"""Prepare checked runtime assets and reproducible host bundles before uv build."""

import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(["npm", "ci"], cwd=ROOT / "dashboard", check=True)
subprocess.run(["npm", "run", "build"], cwd=ROOT / "dashboard", check=True)
shutil.copytree(ROOT / "dashboard/dist", ROOT / "src/branchforge/web", dirs_exist_ok=True)
for host in ("codex", "claude"):
    dest = ROOT / "plugins" / host
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ROOT / "plugins/shared/skills", dest / "skills", dirs_exist_ok=True)
    manifest = {
        "name": "branchforge",
        "version": "0.1.0",
        "description": "Bounded local Python solution search",
        "author": {"name": "BranchForge"},
    }
    mcp = {
        "mcpServers": {
            "branchforge": {
                "command": "branchforge",
                "args": ["mcp", "--expected-version", "0.1.0"],
            }
        }
    }
    if host == "codex":
        manifest["$schema"] = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
        mcp["$schema"] = "https://agent-plugins.org/schemas/1.0.0/mcp.schema.json"
        mcp["mcpServers"]["branchforge"]["type"] = "stdio"
        (dest / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (dest / "mcp.json").write_text(json.dumps(mcp, indent=2) + "\n")
    else:
        (dest / ".claude-plugin").mkdir(exist_ok=True)
        (dest / ".claude-plugin/plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
        (dest / ".mcp.json").write_text(json.dumps(mcp, indent=2) + "\n")
