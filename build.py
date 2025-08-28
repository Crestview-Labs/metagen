#!/usr/bin/env python3
"""
Enhanced master build script for Metagen ecosystem
Handles all build operations with uv package management
"""

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


class MetagenBuilder:
    def __init__(self, verbose: bool = False, mode: str = "intelligent", backend_port: int = 8080):
        self.verbose = verbose
        self.mode = mode  # intelligent, dev, release
        self.root = Path(__file__).parent.absolute()
        self.platform = platform.system().lower()
        self.backend_port = backend_port

    def log(self, message: str, level: str = "info") -> None:
        """Log messages with emoji prefixes"""
        prefixes = {
            "info": "ℹ️ ",
            "success": "✅",
            "warning": "⚠️ ",
            "error": "❌",
            "build": "🔨",
            "package": "📦",
            "check": "🔍",
            "version": "🏷️ ",
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

    def check_dependencies(self) -> bool:
        """Check if all required dependencies are installed"""
        self.log("Checking dependencies...", "check")

        missing = []

        # Check uv
        if not shutil.which("uv"):
            missing.append("uv (install from https://github.com/astral-sh/uv)")

        # Check Node.js and npm
        if not shutil.which("node"):
            missing.append("node")
        if not shutil.which("npm"):
            missing.append("npm")

        # Check platform-specific dependencies
        if self.platform == "darwin":
            if not shutil.which("xcodebuild"):
                missing.append("Xcode (install from Mac App Store)")
            if not shutil.which("xcodegen"):
                missing.append("xcodegen (install with: brew install xcodegen)")

        if missing:
            self.log(f"Missing dependencies: {', '.join(missing)}", "error")
            return False

        self.log("All dependencies installed", "success")
        return True

    def get_current_version(self) -> str:
        """Get the current version from api/version.json"""
        version_file = self.root / "api" / "version.json"
        if version_file.exists():
            with open(version_file) as f:
                data = json.load(f)
                return str(data.get("version", "0.1.0"))
        return "0.1.0"

    def bump_version(self, level: str) -> bool:
        """Bump version across all components"""
        self.log(f"Bumping {level} version...", "version")

        current = self.get_current_version()
        parts = current.split(".")
        major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])

        if level == "major":
            major += 1
            minor = 0
            patch = 0
        elif level == "minor":
            minor += 1
            patch = 0
        elif level == "patch":
            patch += 1
        else:
            self.log(f"Invalid version level: {level}", "error")
            return False

        new_version = f"{major}.{minor}.{patch}"
        self.log(f"Version: {current} → {new_version}", "version")

        # Update api/version.json
        version_file = self.root / "api" / "version.json"
        data = {
            "version": new_version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "typescript": {
                "version": new_version,
                "generated": datetime.now(timezone.utc).isoformat(),
            },
            "swift": {"version": new_version, "generated": datetime.now(timezone.utc).isoformat()},
        }
        with open(version_file, "w") as f:
            json.dump(data, f, indent=2)

        # Update pyproject.toml
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            content = pyproject.read_text()
            content = re.sub(r'version = "[^"]+?"', f'version = "{new_version}"', content, count=1)
            pyproject.write_text(content)

        # Update TypeScript package.json files
        for package_path in [
            self.root / "api" / "ts" / "package.json",
            self.root / "cli" / "package.json",
        ]:
            if package_path.exists():
                with open(package_path) as f:
                    data = json.load(f)
                data["version"] = new_version
                with open(package_path, "w") as f:
                    json.dump(data, f, indent=2)

        # Update Swift version
        swift_version = self.root / "api" / "swift" / "Sources" / "MetagenAPI" / "Version.swift"
        if swift_version.exists():
            content = f'''// Auto-generated version file
public struct MetagenAPIVersion {{
    public static let version = "{new_version}"
    public static let generatedAt = "{datetime.now(timezone.utc).isoformat()}"
}}
'''
            swift_version.write_text(content)

        self.log(f"Version bumped to {new_version}", "success")
        return True

    def run_type_checks(self) -> bool:
        """Run mypy type checking"""
        if self.mode == "dev":
            self.log("Skipping type checks in dev mode", "info")
            return True

        self.log("Running type checks...", "check")
        result = self.run_command(["uv", "run", "mypy", "."], check=False)

        if result.returncode != 0:
            if self.mode == "release":
                self.log("Type check failed (release mode)", "error")
                return False
            else:
                self.log("Type check warnings (continuing)", "warning")
        else:
            self.log("Type checks passed", "success")

        return True

    def run_linters(self) -> bool:
        """Run code linters"""
        if self.mode == "dev":
            self.log("Skipping linters in dev mode", "info")
            return True

        self.log("Running linters...", "check")

        # Run ruff
        result = self.run_command(["uv", "run", "ruff", "check", "."], check=False)
        if result.returncode != 0:
            if self.mode == "release":
                self.log("Linting failed (release mode)", "error")
                return False
            else:
                self.log("Linting issues found (continuing)", "warning")

        return True

    def run_tests(self, use_real_llm: bool = False, pattern: Optional[str] = None) -> bool:
        """Run test suites

        Args:
            use_real_llm: If True, run ALL tests including real LLM tests
            pattern: Optional test pattern to match (e.g., 'test_agent*')
        """
        if self.mode == "dev":
            self.log("Skipping tests in dev mode", "info")
            return True

        # Build pytest command
        cmd = ["uv", "run", "pytest"]

        # Add verbosity
        if self.verbose:
            cmd.append("-v")

        # Add pattern matching if specified
        if pattern:
            cmd.extend(["-k", pattern])
            self.log(f"Running tests matching pattern: {pattern}", "check")
        elif use_real_llm:
            self.log("Running ALL tests including real LLM tests", "warning")
        else:
            # Skip real LLM tests by default
            self.log("Running tests (skipping real LLM tests)", "info")
            cmd.extend(["-k", "not real_llm"])

        result = self.run_command(cmd, check=False)

        if result.returncode != 0:
            if self.mode == "release":
                self.log("Tests failed (release mode)", "error")
                return False
            else:
                self.log("Some tests failed (continuing)", "warning")
        else:
            self.log("All tests passed", "success")

        return True

    def package_cli_dist(self) -> bool:
        """Package CLI for distribution"""
        self.log("Packaging CLI for distribution...", "package")

        cli_dir = self.root / "cli"
        build_dir = cli_dir / "build"
        dist_dir = cli_dir / "dist-package"

        # Clean previous builds
        if build_dir.exists():
            shutil.rmtree(build_dir)
        if dist_dir.exists():
            shutil.rmtree(dist_dir)

        build_dir.mkdir()
        dist_dir.mkdir()

        # Build TypeScript first
        if not (cli_dir / "dist").exists():
            self.log("CLI not built, building first...", "info")
            if not self.build_cli():
                return False

        # Copy Python backend
        self.log("Copying Python backend...", "package")
        backend_dir = build_dir / "backend"
        backend_dir.mkdir()

        # Copy essential files
        for file in ["main.py", "pyproject.toml", "uv.lock"]:
            src = self.root / file
            if src.exists():
                shutil.copy2(src, backend_dir)

        # Copy Python source directories
        dirs_to_copy = [
            "agents",
            "api",
            "auth",
            "client",
            "common",
            "db",
            "integrations",
            "memory",
            "tools",
        ]
        for dir_name in dirs_to_copy:
            src_dir = self.root / dir_name
            if src_dir.exists():
                shutil.copytree(src_dir, backend_dir / dir_name)

        # Copy built JavaScript
        shutil.copytree(cli_dir / "dist", build_dir / "dist")
        shutil.copytree(cli_dir / "node_modules", build_dir / "node_modules")

        # Create launcher script
        launcher = build_dir / "ambient"
        launcher.write_text("""#!/bin/bash
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
export METAGEN_PROJECT_ROOT="$SCRIPT_DIR/backend"
exec node "$SCRIPT_DIR/dist/cli/src/index.js" "$@"
""")
        launcher.chmod(0o755)

        # Create tarball
        archive_name = f"ambient-cli-{self.get_current_version()}-{self.platform}"
        self.log(f"Creating archive: {archive_name}.tar.gz", "package")

        shutil.make_archive(str(dist_dir / archive_name), "gztar", build_dir)

        self.log(f"CLI package created: {dist_dir / archive_name}.tar.gz", "success")
        return True

    def check_backend_running(self, port: int = 8080) -> bool:
        """Check if backend server is running

        Args:
            port: Port to check (default: 8080)
        """
        import urllib.request

        try:
            with urllib.request.urlopen(f"http://localhost:{port}/health", timeout=1) as response:
                return bool(response.status == 200)
        except Exception:
            return False

    def generate_api_stubs(self, force: bool = False) -> bool:
        """Generate TypeScript and Swift API stubs"""
        self.log("Generating API stubs...", "build")

        # Check if backend is running
        if not self.check_backend_running(self.backend_port):
            self.log(f"Backend not running on port {self.backend_port}", "error")
            self.log("Start it with: uv run python launch.py server start", "info")
            return False

        # Run stub generation
        cmd = ["uv", "run", "python", "generate_stubs.py"]
        if force:
            # generate_stubs.py doesn't have --force flag
            pass

        # Run with output visible for debugging
        if self.verbose:
            self.log("Running stub generation script...", "info")

        result = self.run_command(cmd, check=False)
        if result.returncode != 0:
            self.log("Failed to generate API stubs", "error")
            if result.stderr:
                self.log(f"Error: {result.stderr}", "error")
            return False

        self.log("API stubs generated", "success")
        return True

    def build_typescript_api(self) -> bool:
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

    def build_swift_api(self) -> bool:
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

    def build_cli(self) -> bool:
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

    def build_backend_executable(self) -> bool:
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

    def create_backend_build_script(self) -> None:
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

    def build_mac_app(self) -> bool:
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

    def package_mac_app(self) -> bool:
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

    def build_all(self) -> bool:
        """Build everything"""
        self.log("Building all components...", "build")

        # Check dependencies first
        if not self.check_dependencies():
            self.log("Missing dependencies. Install them and try again.", "error")
            return False

        # Run checks if not in dev mode
        if self.mode != "dev":
            self.run_type_checks()
            self.run_linters()

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

    def clean(self) -> bool:
        """Clean all build artifacts"""
        self.log("Cleaning build artifacts...", "info")

        # Directories to clean
        clean_dirs = [
            self.root / "dist",
            self.root / "build",
            self.root / "api" / "ts" / "dist",
            self.root / "api" / "swift" / ".build",
            self.root / "cli" / "dist",
            self.root / "cli" / "build",
            self.root / "cli" / "dist-package",
            self.root / "backend" / "dist",
            self.root / "backend" / "build",
            self.root / "macapp" / "build",
            self.root / "macapp" / "Ambient.xcodeproj",
        ]

        for dir_path in clean_dirs:
            if dir_path.exists():
                shutil.rmtree(dir_path)
                self.log(f"Removed {dir_path.relative_to(self.root)}", "info")

        self.log("Clean complete", "success")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Enhanced Metagen build script with uv")

    # Build modes
    parser.add_argument("--dev", action="store_true", help="Development mode (skip checks)")
    parser.add_argument("--release", action="store_true", help="Release mode (strict checks)")
    parser.add_argument("--check-only", action="store_true", help="Run checks without building")

    # Version management
    parser.add_argument("--bump-patch", action="store_true", help="Bump patch version (x.y.Z)")
    parser.add_argument("--bump-minor", action="store_true", help="Bump minor version (x.Y.0)")
    parser.add_argument("--bump-major", action="store_true", help="Bump major version (X.0.0)")

    # Build targets
    parser.add_argument("--all", action="store_true", help="Build everything")
    parser.add_argument("--api-stubs", action="store_true", help="Generate API stubs")
    parser.add_argument("--force-stubs", action="store_true", help="Force regenerate API stubs")
    parser.add_argument("--ts-api", action="store_true", help="Build TypeScript API")
    parser.add_argument("--swift-api", action="store_true", help="Build Swift API")
    parser.add_argument("--cli", action="store_true", help="Build CLI")
    parser.add_argument("--backend-exe", action="store_true", help="Build backend executable")
    parser.add_argument("--mac-app", action="store_true", help="Build Mac app")
    parser.add_argument("--package-mac", action="store_true", help="Package Mac app as DMG")
    parser.add_argument("--package-cli", action="store_true", help="Package CLI for distribution")
    parser.add_argument("--clean", action="store_true", help="Clean build artifacts")

    # Testing and checks
    parser.add_argument("--test", action="store_true", help="Run tests with mock LLMs")
    parser.add_argument(
        "--test-real", action="store_true", help="Run tests with real LLMs (requires API keys)"
    )
    parser.add_argument(
        "--test-pattern", help="Run specific tests matching pattern (e.g., 'test_agent*')"
    )
    parser.add_argument("--type-check", action="store_true", help="Run type checks")
    parser.add_argument("--lint", action="store_true", help="Run linters")

    # Other options
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Determine mode
    mode = "intelligent"  # default
    if args.dev:
        mode = "dev"
    elif args.release:
        mode = "release"

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
            args.package_cli,
            args.clean,
            args.check_only,
            args.bump_patch,
            args.bump_minor,
            args.bump_major,
            args.test,
            args.type_check,
            args.lint,
        ]
    ):
        parser.print_help()
        return 1

    builder = MetagenBuilder(verbose=args.verbose, mode=mode)

    try:
        # Handle version bumping
        if args.bump_patch:
            return 0 if builder.bump_version("patch") else 1
        if args.bump_minor:
            return 0 if builder.bump_version("minor") else 1
        if args.bump_major:
            return 0 if builder.bump_version("major") else 1

        # Handle checks and tests
        if args.check_only:
            # Quick checks only - NO TESTS
            builder.log("Running quick checks (type check + lint)...", "info")
            success = builder.run_type_checks() and builder.run_linters()
            return 0 if success else 1

        if args.type_check:
            return 0 if builder.run_type_checks() else 1

        if args.lint:
            return 0 if builder.run_linters() else 1

        if args.test or args.test_real:
            # Run tests with appropriate configuration
            use_real_llm = args.test_real
            pattern = args.test_pattern
            return 0 if builder.run_tests(use_real_llm=use_real_llm, pattern=pattern) else 1

        # Handle clean
        if args.clean:
            return 0 if builder.clean() else 1

        # Handle build all
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

        if args.package_cli:
            success = success and builder.package_cli_dist()

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
