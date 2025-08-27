#!/usr/bin/env python3
"""
Master build script for Metagen ecosystem
Handles API stub generation, CLI building, and Mac app packaging
"""

import argparse
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


class MetagenBuilder:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.root = Path(__file__).parent.absolute()
        self.platform = platform.system().lower()

    def log(self, message: str, level: str = "info"):
        """Log messages with emoji prefixes"""
        prefixes = {
            "info": "ℹ️ ",
            "success": "✅",
            "warning": "⚠️ ",
            "error": "❌",
            "build": "🔨",
            "package": "📦",
        }
        print(f"{prefixes.get(level, '')} {message}")

    def run_command(
        self, cmd: list, cwd: Optional[Path] = None, check: bool = True
    ) -> subprocess.CompletedProcess:
        """Run a command and return the result"""
        if self.verbose:
            self.log(f"Running: {' '.join(cmd)}", "info")

        return subprocess.run(
            cmd, cwd=cwd or self.root, capture_output=not self.verbose, text=True, check=check
        )

    def check_backend_running(self) -> bool:
        """Check if backend server is running"""
        import urllib.request

        try:
            with urllib.request.urlopen("http://localhost:8985/health", timeout=1) as response:
                return response.status == 200
        except Exception:
            return False

    def generate_api_stubs(self, force: bool = False):
        """Generate TypeScript and Swift API stubs"""
        self.log("Generating API stubs...", "build")

        # Check if backend is running
        if not self.check_backend_running():
            self.log("Backend not running. Start it with: uv run python main.py", "error")
            return False

        # Run stub generation
        cmd = ["uv", "run", "python", "generate_stubs.py"]
        if force:
            # generate_stubs.py doesn't have --force flag
            pass

        result = self.run_command(cmd, check=False)
        if result.returncode != 0:
            self.log("Failed to generate API stubs", "error")
            return False

        self.log("API stubs generated", "success")
        return True

    def build_typescript_api(self):
        """Build TypeScript API package"""
        self.log("Building TypeScript API...", "build")

        api_dir = self.root / "api" / "ts"
        if not api_dir.exists():
            self.log("TypeScript API directory not found", "error")
            return False

        # Install dependencies
        self.run_command(["npm", "install"], cwd=api_dir)

        # Build
        self.run_command(["npm", "run", "build"], cwd=api_dir)

        self.log("TypeScript API built", "success")
        return True

    def build_swift_api(self):
        """Build Swift API package"""
        if self.platform != "darwin":
            self.log("Swift API can only be built on macOS", "warning")
            return True

        self.log("Building Swift API...", "build")

        api_dir = self.root / "api" / "swift"
        if not api_dir.exists():
            self.log("Swift API directory not found", "error")
            return False

        # Build
        self.run_command(["swift", "build"], cwd=api_dir)

        self.log("Swift API built", "success")
        return True

    def build_cli(self):
        """Build CLI application"""
        self.log("Building CLI...", "build")

        cli_dir = self.root / "cli"
        if not cli_dir.exists():
            self.log("CLI directory not found", "error")
            return False

        # Install dependencies
        self.run_command(["npm", "install"], cwd=cli_dir)

        # Build
        self.run_command(["npm", "run", "build"], cwd=cli_dir)

        self.log("CLI built", "success")
        return True

    def build_backend_executable(self):
        """Build Python backend as standalone executable"""
        self.log("Building backend executable...", "build")

        # Create build script if it doesn't exist
        build_script = self.root / "backend" / "build.sh"
        if not build_script.exists():
            self.create_backend_build_script()

        # Run PyInstaller
        cmd = ["bash", str(build_script)]
        result = self.run_command(cmd, cwd=self.root / "backend", check=False)

        if result.returncode != 0:
            self.log("Failed to build backend executable", "error")
            return False

        self.log("Backend executable built", "success")
        return True

    def create_backend_build_script(self):
        """Create PyInstaller build script for backend"""
        script_path = self.root / "backend" / "build.sh"
        script_content = """#!/bin/bash
set -e

echo "Building Python backend with PyInstaller..."

# Activate virtual environment
source ../.venv/bin/activate

# Install PyInstaller if needed
pip install pyinstaller

# Build executable
pyinstaller \
    --name ambient-backend \
    --onedir \
    --add-data "api:api" \
    --add-data "tools:tools" \
    --add-data "integrations:integrations" \
    --hidden-import "uvicorn" \
    --hidden-import "fastapi" \
    --hidden-import "whisper" \
    --collect-all "anthropic" \
    --collect-all "openai" \
    ../main.py

echo "✅ Backend executable built at dist/ambient-backend/"
"""
        script_path.write_text(script_content)
        script_path.chmod(0o755)
        self.log("Created backend build script", "info")

    def build_mac_app(self):
        """Build macOS application"""
        if self.platform != "darwin":
            self.log("Mac app can only be built on macOS", "warning")
            return True

        self.log("Building Mac app...", "build")

        app_dir = self.root / "macapp"
        if not app_dir.exists():
            self.log("Mac app directory not found", "error")
            return False

        # Check if XcodeGen is installed
        xcodegen_check = self.run_command(["which", "xcodegen"], check=False)
        if xcodegen_check.returncode != 0:
            self.log("XcodeGen not found. Install it with: brew install xcodegen", "error")
            return False

        # Generate Xcode project if needed (or if source files have changed)
        xcodeproj_path = app_dir / "Ambient.xcodeproj"
        project_yml_path = app_dir / "project.yml"

        # Check if any Swift files are newer than the project
        needs_regeneration = not xcodeproj_path.exists()
        if xcodeproj_path.exists():
            project_mtime = xcodeproj_path.stat().st_mtime
            # Check project.yml
            if project_yml_path.stat().st_mtime > project_mtime:
                needs_regeneration = True
                self.log("project.yml has been modified", "info")

            # Check Swift source files - count ALL swift files
            current_swift_files = set()
            for swift_file in app_dir.rglob("*.swift"):
                # Skip build directory
                if "build/" not in str(swift_file):
                    current_swift_files.add(str(swift_file.relative_to(app_dir)))

            # Check if any file is newer OR if file count changed
            new_or_modified_files = []
            for swift_file in app_dir.rglob("*.swift"):
                if "build/" not in str(swift_file):
                    if swift_file.stat().st_mtime > project_mtime:
                        new_or_modified_files.append(swift_file.name)
                        needs_regeneration = True

            # Also check if we have any new files not tracked before
            # (XcodeGen needs to know about all files)
            if len(current_swift_files) > 0:
                # Force regeneration to ensure all files are included
                if new_or_modified_files:
                    needs_regeneration = True
                    files_preview = ", ".join(new_or_modified_files[:3])
                    if len(new_or_modified_files) > 3:
                        files_preview += " ..."
                    msg = f"Detected {len(new_or_modified_files)} new/modified file(s): "
                    self.log(msg + files_preview, "info")

        if needs_regeneration:
            # Clean ALL build artifacts before regenerating to avoid stale cache issues
            build_dir = app_dir / "build"
            if build_dir.exists():
                self.log("Cleaning build artifacts...", "info")
                shutil.rmtree(build_dir, ignore_errors=True)

            # Also remove the xcodeproj to force complete regeneration
            if xcodeproj_path.exists():
                self.log("Removing old Xcode project for clean regeneration...", "info")
                shutil.rmtree(xcodeproj_path, ignore_errors=True)

            self.log("Regenerating Xcode project with XcodeGen...", "info")
            result = self.run_command(
                ["xcodegen", "generate", "--spec", "project.yml"], cwd=app_dir, check=False
            )
            if result.returncode != 0:
                self.log("Failed to generate Xcode project", "error")
                if result.stderr:
                    self.log(f"XcodeGen error: {result.stderr[:500]}", "error")
                return False
            self.log("Xcode project regenerated", "success")

            # Sleep briefly to ensure filesystem syncs
            time.sleep(0.5)
        else:
            self.log("Xcode project is up to date", "info")

        # Build with xcodebuild (skip plugin validation to avoid security prompts)
        cmd = [
            "xcodebuild",
            "-scheme",
            "Ambient",
            "-configuration",
            "Release",
            "-derivedDataPath",
            "build",
            "-skipPackagePluginValidation",
        ]

        result = self.run_command(cmd, cwd=app_dir, check=False)

        if result.returncode != 0:
            self.log("Failed to build Mac app", "error")
            # Try to extract specific error messages
            if result.stderr:
                error_lines = result.stderr.split("\n")
                for line in error_lines:
                    if "error:" in line.lower():
                        self.log(f"  {line.strip()}", "error")
            return False

        self.log("Mac app built", "success")
        return True

    def package_mac_app(self):
        """Package Mac app as DMG"""
        if self.platform != "darwin":
            self.log("Mac app can only be packaged on macOS", "warning")
            return True

        self.log("Packaging Mac app...", "package")

        app_path = self.root / "macapp" / "build" / "Build" / "Products" / "Release" / "Ambient.app"
        if not app_path.exists():
            self.log("Built app not found. Build it first with --mac-app", "error")
            return False

        # Copy backend executable into app bundle
        backend_exe = self.root / "backend" / "dist" / "ambient-backend"
        if backend_exe.exists():
            app_backend = app_path / "Contents" / "Resources" / "backend"
            shutil.copytree(backend_exe, app_backend, dirs_exist_ok=True)
            self.log("Embedded backend in app bundle", "info")

        # Create DMG
        dmg_name = "Ambient.dmg"
        dmg_path = self.root / "dist" / dmg_name
        dmg_path.parent.mkdir(exist_ok=True)

        cmd = [
            "hdiutil",
            "create",
            "-volname",
            "Ambient",
            "-srcfolder",
            str(app_path),
            "-ov",
            "-format",
            "UDZO",
            str(dmg_path),
        ]

        self.run_command(cmd)

        self.log(f"DMG created at {dmg_path}", "success")
        return True

    def build_all(self):
        """Build everything"""
        self.log("Building all components...", "build")

        # Generate API stubs first
        if not self.generate_api_stubs():
            return False

        # Build API packages
        if not self.build_typescript_api():
            return False

        if self.platform == "darwin" and not self.build_swift_api():
            return False

        # Build CLI
        if not self.build_cli():
            return False

        # Build backend executable
        if not self.build_backend_executable():
            return False

        # Build Mac app on macOS
        if self.platform == "darwin":
            if not self.build_mac_app():
                return False
            if not self.package_mac_app():
                return False

        self.log("All components built successfully!", "success")
        return True

    def clean(self):
        """Clean all build artifacts"""
        self.log("Cleaning build artifacts...", "info")

        # Directories to clean
        clean_dirs = [
            self.root / "dist",
            self.root / "build",
            self.root / "api" / "ts" / "dist",
            self.root / "api" / "swift" / ".build",
            self.root / "cli" / "dist",
            self.root / "backend" / "dist",
            self.root / "backend" / "build",
            self.root / "macapp" / "build",
        ]

        for dir_path in clean_dirs:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                self.log(f"Removed {dir_path.relative_to(self.root)}", "info")

        self.log("Clean complete", "success")
        return True


def main():
    parser = argparse.ArgumentParser(description="Metagen master build script")
    parser.add_argument("--all", action="store_true", help="Build everything")
    parser.add_argument("--api-stubs", action="store_true", help="Generate API stubs")
    parser.add_argument("--force-stubs", action="store_true", help="Force regenerate API stubs")
    parser.add_argument("--ts-api", action="store_true", help="Build TypeScript API")
    parser.add_argument("--swift-api", action="store_true", help="Build Swift API")
    parser.add_argument("--cli", action="store_true", help="Build CLI")
    parser.add_argument("--backend-exe", action="store_true", help="Build backend executable")
    parser.add_argument("--mac-app", action="store_true", help="Build Mac app")
    parser.add_argument("--package-mac", action="store_true", help="Package Mac app as DMG")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # If no specific build target, show help
    if not any(
        [
            args.all,
            args.api_stubs,
            args.ts_api,
            args.swift_api,
            args.cli,
            args.backend_exe,
            args.mac_app,
            args.package_mac,
            args.clean,
        ]
    ):
        parser.print_help()
        return 1

    builder = MetagenBuilder(verbose=args.verbose)

    try:
        if args.clean:
            return 0 if builder.clean() else 1

        if args.all:
            return 0 if builder.build_all() else 1

        # Individual builds
        success = True

        if args.api_stubs or args.force_stubs:
            success = success and builder.generate_api_stubs(force=args.force_stubs)

        if args.ts_api:
            success = success and builder.build_typescript_api()

        if args.swift_api:
            success = success and builder.build_swift_api()

        if args.cli:
            success = success and builder.build_cli()

        if args.backend_exe:
            success = success and builder.build_backend_executable()

        if args.mac_app:
            success = success and builder.build_mac_app()

        if args.package_mac:
            success = success and builder.package_mac_app()

        return 0 if success else 1

    except KeyboardInterrupt:
        builder.log("Build interrupted", "warning")
        return 1
    except Exception as e:
        builder.log(f"Build failed: {e}", "error")
        return 1


if __name__ == "__main__":
    sys.exit(main())
