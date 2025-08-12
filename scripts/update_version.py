#!/usr/bin/env python3
"""
Update version across all files in the Metagen project.
Usage: python scripts/update_version.py <new_version>
"""

import json
import re
import sys
from datetime import datetime
from pathlib import Path


def update_version(new_version: str):
    """Update version in all relevant files"""
    root = Path(__file__).parent.parent

    # Validate version format (semantic versioning)
    if not re.match(r"^\d+\.\d+\.\d+$", new_version):
        print(f"❌ Invalid version format: {new_version}")
        print("   Please use semantic versioning: MAJOR.MINOR.PATCH (e.g., 0.1.0)")
        sys.exit(1)

    # Update version.json
    version_file = root / "version.json"
    with open(version_file, "r") as f:
        data = json.load(f)

    old_version = data["version"]
    data["version"] = new_version
    data["build"] = datetime.now().strftime("%Y.%m.%d.%H%M")
    data["release_date"] = datetime.now().strftime("%Y-%m-%d")

    with open(version_file, "w") as f:
        json.dump(data, f, indent=2)
        f.write("\n")  # Add newline at end of file

    # Update api/__version__.py
    api_version_file = root / "api" / "__version__.py"
    api_version_file.write_text(f'"""API version information"""\n\nAPI_VERSION = "{new_version}"\n')

    # Update pyproject.toml
    pyproject = root / "pyproject.toml"
    if pyproject.exists():
        content = pyproject.read_text()
        content = re.sub(r'version = "[^"]*"', f'version = "{new_version}"', content, count=1)
        pyproject.write_text(content)

    # Update package.json files (main and in api/ts if it exists)
    for pkg_json in [root / "package.json", root / "api" / "ts" / "package.json"]:
        if pkg_json.exists():
            with open(pkg_json, "r") as f:
                pkg_data = json.load(f)
            pkg_data["version"] = new_version
            with open(pkg_json, "w") as f:
                json.dump(pkg_data, f, indent=2)
                f.write("\n")

    print(f"✅ Version updated from {old_version} to {new_version}")
    print(f"   Build: {data['build']}")
    print(f"   Date: {data['release_date']}")
    print("")
    print("📋 Next steps:")
    print("   1. Generate stubs: Copy scripts/generate_stubs_instructions.md to Claude Code")
    print("   2. Run build: ./build.sh")
    print("   3. Commit changes: git add -A && git commit -m 'Bump version to " + new_version + "'")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/update_version.py <new_version>")
        print("Example: python scripts/update_version.py 0.2.0")
        sys.exit(1)

    update_version(sys.argv[1])
