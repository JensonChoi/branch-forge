from pathlib import Path
from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        if (
            version != "editable"
            and not (Path(self.root) / "src/branchforge/web/index.html").is_file()
        ):
            raise RuntimeError(
                "Missing dashboard assets: run python scripts/prepare_release.py first"
            )
