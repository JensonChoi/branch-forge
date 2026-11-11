from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        # Editable installs use the source tree and must work before Node builds it.
        if version == "editable":
            return
        assets = Path(self.root) / "src/branchforge/web"
        if not (assets / "index.html").is_file():
            raise RuntimeError(
                "Missing dashboard assets: run python scripts/prepare_release.py first"
            )
        destination = "branchforge/web" if self.target_name == "wheel" else "src/branchforge/web"
        build_data["force_include"][str(assets)] = destination
