#!/usr/bin/env python3
"""
Unified launcher for Metagen ecosystem
Handles backend server, CLI, and Mac app launching with automatic dependency management
All operations use uv for Python package management
"""

import argparse
import os
import platform
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional


class MetagenLauncher:
    def __init__(self, profile: str = "default", verbose: bool = False):
        self.profile = profile
        self.verbose = verbose
        self.root = Path(__file__).parent.absolute()
        self.platform_name = platform.system().lower()
        self.ambient_home = Path.home() / ".ambient"
        self.profile_dir = self.ambient_home / "profiles" / profile
        self.pid_file = self.profile_dir / "backend.pid"
        self.log_dir = self.profile_dir / "logs"
        self.backend_port = 8080

    def log(self, message: str, level: str = "info") -> None:
        """Log messages with emoji prefixes"""
        prefixes = {
            "info": "ℹ️ ",
            "success": "✅",
            "warning": "⚠️ ",
            "error": "❌",
            "launch": "🚀",
            "server": "🖥️ ",
            "profile": "👤",
        }
        print(f"{prefixes.get(level, '')} {message}")

    def setup_profile(self) -> None:
        """Set up profile directories"""
        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(exist_ok=True)
        if self.verbose:
            self.log(f"Profile directory: {self.profile_dir}", "profile")

    def is_backend_running(self, port: Optional[int] = None) -> bool:
        """Check if backend server is running"""
        import urllib.request

        check_port = port or self.backend_port
        try:
            url = f"http://localhost:{check_port}/health"
            with urllib.request.urlopen(url, timeout=1) as response:
                return bool(response.status == 200)
        except Exception:
            return False

    def get_backend_pid(self) -> Optional[int]:
        """Get backend process ID if it exists"""
        if self.pid_file.exists():
            try:
                return int(self.pid_file.read_text().strip())
            except (ValueError, IOError):
                return None
        return None

    def is_process_running(self, pid: int) -> bool:
        """Check if a process with given PID is running"""
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def ensure_uv_installed(self) -> bool:
        """Ensure uv is installed"""
        if not shutil.which("uv"):
            self.log("uv not found. Please install it:", "error")
            self.log("  curl -LsSf https://astral.sh/uv/install.sh | sh", "info")
            return False
        return True

    def ensure_venv_exists(self) -> bool:
        """Ensure Python virtual environment exists"""
        venv_path = self.root / ".venv"
        if not venv_path.exists():
            self.log("Virtual environment not found. Creating...", "info")
            result = subprocess.run(["uv", "venv"], cwd=self.root, capture_output=not self.verbose)
            if result.returncode != 0:
                self.log("Failed to create virtual environment", "error")
                return False

            # Install dependencies
            self.log("Installing dependencies...", "info")
            result = subprocess.run(
                ["uv", "pip", "install", "-r", "requirements.txt"],
                cwd=self.root,
                capture_output=not self.verbose,
            )
            if result.returncode != 0:
                self.log("Failed to install dependencies", "error")
                return False

        return True

    def start_backend(self, port: Optional[int] = None, detach: bool = True) -> bool:
        """Start the backend server using uv"""
        use_port = port or self.backend_port

        # Check if already running
        if self.is_backend_running(use_port):
            pid = self.get_backend_pid()
            if pid:
                self.log(f"Backend already running (PID: {pid}, Port: {use_port})", "success")
            else:
                self.log(f"Backend already running on port {use_port}", "success")
            return True

        # Ensure uv is installed
        if not self.ensure_uv_installed():
            return False

        # Ensure virtual environment exists
        if not self.ensure_venv_exists():
            return False

        self.log(f"Starting backend server on port {use_port}...", "server")

        # Set up database path
        db_path = self.profile_dir / "metagen.db"

        # Set up log file
        log_file = self.log_dir / f"backend-{time.strftime('%Y-%m-%d')}.log"

        # Prepare command using uv
        cmd = ["uv", "run", "python", "main.py", "--port", str(use_port), "--db-path", str(db_path)]

        if detach:
            # Start in background
            with open(log_file, "a") as log:
                log.write(f"\n{'=' * 60}\n")
                log.write(f"Backend started at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                log.write(f"Profile: {self.profile}\n")
                log.write(f"Port: {use_port}\n")
                log.write(f"Database: {db_path}\n")
                log.write(f"{'=' * 60}\n\n")
                log.flush()

                process = subprocess.Popen(
                    cmd, cwd=self.root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
                )

            # Save PID
            self.pid_file.write_text(str(process.pid))

            # Wait for server to start
            self.log("Waiting for backend to start...", "info")
            for i in range(30):  # 30 second timeout
                if self.is_backend_running(use_port):
                    self.log(f"Backend started successfully (PID: {process.pid})", "success")
                    self.log(f"Logs: {log_file}", "info")
                    return True
                time.sleep(1)
                if i % 5 == 4:  # Every 5 seconds
                    self.log("Still waiting for backend...", "info")

            self.log("Backend failed to start within 30 seconds", "error")
            self.log(f"Check logs at: {log_file}", "info")
            return False
        else:
            # Run in foreground
            self.log("Running backend in foreground (Ctrl+C to stop)...", "server")
            try:
                result = subprocess.run(cmd, cwd=self.root)
                return result.returncode == 0
            except KeyboardInterrupt:
                self.log("\nBackend stopped", "info")
                return True

    def stop_backend(self) -> bool:
        """Stop the backend server"""
        pid = self.get_backend_pid()

        if pid and self.is_process_running(pid):
            self.log(f"Stopping backend server (PID: {pid})...", "server")
            try:
                # Send SIGTERM for graceful shutdown
                os.kill(pid, signal.SIGTERM)

                # Wait for graceful shutdown
                for i in range(10):
                    if not self.is_process_running(pid):
                        break
                    time.sleep(0.5)

                # Force kill if still running
                if self.is_process_running(pid):
                    self.log("Force stopping backend...", "warning")
                    os.kill(pid, signal.SIGKILL)
                    time.sleep(0.5)

                self.pid_file.unlink(missing_ok=True)
                self.log("Backend stopped", "success")
                return True
            except Exception as e:
                self.log(f"Failed to stop backend: {e}", "error")
                return False
        else:
            self.log("Backend not running", "info")
            self.pid_file.unlink(missing_ok=True)
            return True

    def restart_backend(self, port: Optional[int] = None) -> bool:
        """Restart the backend server"""
        self.log("Restarting backend...", "server")
        self.stop_backend()
        time.sleep(1)  # Brief pause before restart
        return self.start_backend(port=port)

    def launch_cli(self, args: Optional[list] = None) -> int:
        """Launch the CLI"""
        self.log("Launching Ambient CLI...", "launch")

        # Ensure backend is running
        backend_status = self.is_backend_running()
        if self.verbose:
            self.log(f"Backend check on port {self.backend_port}: {backend_status}", "info")

        if not backend_status:
            self.log("Backend not running, starting it first...", "info")
            if not self.start_backend():
                self.log("Failed to start backend", "error")
                return 1

        # Check if CLI is built
        cli_dist = self.root / "cli" / "dist" / "cli" / "src" / "index.js"
        if not cli_dist.exists():
            self.log("CLI not built. Building now...", "info")

            # Ensure uv is installed
            if not self.ensure_uv_installed():
                return 1

            build_result = subprocess.run(
                ["uv", "run", "python", "build.py", "--cli"],
                cwd=self.root,
                capture_output=not self.verbose,
            )
            if build_result.returncode != 0:
                self.log("Failed to build CLI", "error")
                self.log("Try building manually: uv run python build.py --cli", "info")
                return 1

        # Set environment variables
        env = os.environ.copy()
        env["METAGEN_PROJECT_ROOT"] = str(self.root)
        env["AMBIENT_HOME"] = str(self.ambient_home)
        env["AMBIENT_PROFILE"] = self.profile
        env["BACKEND_PORT"] = str(self.backend_port)

        # Launch CLI
        cmd = ["node", str(cli_dist)]
        if args:
            cmd.extend(args)

        try:
            return subprocess.run(cmd, env=env, cwd=self.root).returncode
        except KeyboardInterrupt:
            self.log("\nCLI interrupted", "info")
            return 0
        except FileNotFoundError:
            self.log("Node.js not found. Please install Node.js", "error")
            return 1

    def launch_mac_app(self) -> int:
        """Launch the Mac app"""
        if self.platform_name != "darwin":
            self.log("Mac app can only run on macOS", "error")
            return 1

        self.log("Launching Ambient Mac app...", "launch")

        # Ensure backend is running
        if not self.is_backend_running():
            self.log("Backend not running, starting it first...", "info")
            if not self.start_backend():
                self.log("Failed to start backend", "error")
                return 1

        # Check if app is built
        app_path = self.root / "macapp" / "build" / "Build" / "Products" / "Release" / "Ambient.app"

        if not app_path.exists():
            self.log("Mac app not built. Building now...", "info")

            # Ensure uv is installed
            if not self.ensure_uv_installed():
                return 1

            build_result = subprocess.run(
                ["uv", "run", "python", "build.py", "--mac-app"],
                cwd=self.root,
                capture_output=not self.verbose,
            )
            if build_result.returncode != 0:
                self.log("Failed to build Mac app", "error")
                self.log("Try building manually: uv run python build.py --mac-app", "info")
                return 1

        # Launch app
        try:
            subprocess.run(["open", str(app_path)], check=True)
            self.log("Mac app launched", "success")
            self.log(f"Backend running on port {self.backend_port}", "info")
            return 0
        except subprocess.CalledProcessError:
            self.log("Failed to launch Mac app", "error")
            return 1

    def show_status(self) -> None:
        """Show status of all components"""
        self.log("Metagen Status", "info")
        print("=" * 60)

        # Profile info
        print(f"Profile: {self.profile}")
        print(f"Profile directory: {self.profile_dir}")
        print()

        # Backend status
        if self.is_backend_running():
            pid = self.get_backend_pid()
            print("Backend Server:")
            print("  Status: ✅ Running")
            if pid:
                print(f"  PID: {pid}")
            print(f"  Port: {self.backend_port}")
            print(f"  URL: http://localhost:{self.backend_port}")
        else:
            print("Backend Server:")
            print("  Status: ❌ Not running")
            print("  Start with: uv run python launch.py server start")
        print()

        # Database info
        db_path = self.profile_dir / "metagen.db"
        if db_path.exists():
            size = db_path.stat().st_size / 1024 / 1024  # MB
            print("Database:")
            print(f"  Path: {db_path}")
            print(f"  Size: {size:.2f} MB")
        else:
            print("Database: Not created yet")
        print()

        # Logs
        print("Logs:")
        if self.log_dir.exists():
            log_files = list(self.log_dir.glob("backend-*.log"))
            if log_files:
                latest = max(log_files, key=lambda p: p.stat().st_mtime)
                size = latest.stat().st_size / 1024  # KB
                print(f"  Latest: {latest.name} ({size:.1f} KB)")
                print(f"  Total log files: {len(log_files)}")
            else:
                print("  No log files yet")
        else:
            print("  Log directory not created yet")
        print()

        # Build status
        print("Build Status:")

        # CLI
        cli_built = (self.root / "cli" / "dist").exists()
        print(f"  CLI: {'✅ Built' if cli_built else '❌ Not built'}")
        if not cli_built:
            print("    Build with: uv run python build.py --cli")

        # Mac App
        if self.platform_name == "darwin":
            app_path = (
                self.root / "macapp" / "build" / "Build" / "Products" / "Release" / "Ambient.app"
            )
            app_built = app_path.exists()
            print(f"  Mac App: {'✅ Built' if app_built else '❌ Not built'}")
            if not app_built:
                print("    Build with: uv run python build.py --mac-app")

        # API stubs
        ts_api = (self.root / "api" / "ts" / "dist").exists()
        print(f"  TypeScript API: {'✅ Built' if ts_api else '❌ Not built'}")

        if self.platform_name == "darwin":
            swift_api = (self.root / "api" / "swift" / ".build").exists()
            print(f"  Swift API: {'✅ Built' if swift_api else '❌ Not built'}")

        print()
        print("Quick Commands:")
        print("  Launch CLI:     uv run python launch.py cli")
        if self.platform_name == "darwin":
            print("  Launch Mac App: uv run python launch.py mac")
        print("  Start Backend:  uv run python launch.py server start")
        print("  View Logs:      uv run python launch.py logs -f")

    def show_logs(self, lines: int = 50, follow: bool = False) -> None:
        """Show backend logs"""
        if not self.log_dir.exists():
            self.log("No log directory found", "warning")
            return

        log_files = list(self.log_dir.glob("backend-*.log"))
        if not log_files:
            self.log("No log files found", "warning")
            self.log("Logs will be created when backend starts", "info")
            return

        latest = max(log_files, key=lambda p: p.stat().st_mtime)
        self.log(f"Showing logs from: {latest.name}", "info")

        if follow:
            # Use tail -f
            self.log("Following log output (Ctrl+C to stop)...", "info")
            try:
                subprocess.run(["tail", "-f", str(latest)])
            except KeyboardInterrupt:
                print()  # New line after Ctrl+C
        else:
            # Show last N lines
            subprocess.run(["tail", "-n", str(lines), str(latest)])

    def clean_profile(self) -> None:
        """Clean profile data (logs, database, etc.)"""
        self.log(f"Cleaning profile: {self.profile}", "warning")

        # Stop backend if running
        if self.is_backend_running():
            self.log("Stopping backend first...", "info")
            self.stop_backend()

        # Confirm with user
        response = input(f"⚠️  Delete all data for profile '{self.profile}'? (y/N): ")
        if response.lower() != "y":
            self.log("Cancelled", "info")
            return

        # Remove profile directory
        if self.profile_dir.exists():
            import shutil

            shutil.rmtree(self.profile_dir)
            self.log(f"Removed profile directory: {self.profile_dir}", "success")
        else:
            self.log("Profile directory doesn't exist", "info")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Metagen unified launcher - Start backend, CLI, or Mac app with uv",
        epilog="Examples:\n"
        "  uv run python launch.py              # Launch CLI (default)\n"
        "  uv run python launch.py cli          # Launch CLI explicitly\n"
        "  uv run python launch.py mac          # Launch Mac app\n"
        "  uv run python launch.py server start # Start backend server\n"
        "  uv run python launch.py status       # Show system status\n",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # Global options
    parser.add_argument(
        "-p",
        "--profile",
        default="default",
        help="Profile name for isolated environments (default: default)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # CLI command
    cli_parser = subparsers.add_parser("cli", help="Launch the CLI")
    cli_parser.add_argument("cli_args", nargs="*", help="Arguments to pass to CLI")

    # Mac app command
    subparsers.add_parser("mac", help="Launch the Mac app (macOS only)")

    # Server commands
    server_parser = subparsers.add_parser("server", help="Manage backend server")
    server_subparsers = server_parser.add_subparsers(dest="server_command")

    server_start = server_subparsers.add_parser("start", help="Start backend server")
    server_start.add_argument("--port", type=int, help="Port to use (default: 8080)")
    server_start.add_argument(
        "--foreground", action="store_true", help="Run in foreground instead of background"
    )

    server_subparsers.add_parser("stop", help="Stop backend server")
    server_subparsers.add_parser("restart", help="Restart backend server")
    server_subparsers.add_parser("status", help="Show server status")

    # Status command
    subparsers.add_parser("status", help="Show status of all components")

    # Logs command
    logs_parser = subparsers.add_parser("logs", help="Show backend logs")
    logs_parser.add_argument(
        "-n", "--lines", type=int, default=50, help="Number of lines to show (default: 50)"
    )
    logs_parser.add_argument(
        "-f", "--follow", action="store_true", help="Follow log output (like tail -f)"
    )

    # Clean command
    subparsers.add_parser("clean", help="Clean profile data (logs, database, etc.)")

    args = parser.parse_args()

    # Create launcher
    launcher = MetagenLauncher(profile=args.profile, verbose=args.verbose)
    launcher.setup_profile()

    # Default to CLI if no command specified
    if not args.command:
        return launcher.launch_cli()

    # Handle commands
    if args.command == "cli":
        return launcher.launch_cli(args.cli_args)

    elif args.command == "mac":
        return launcher.launch_mac_app()

    elif args.command == "server":
        if not args.server_command:
            # Show server help if no subcommand
            server_parser.print_help()
            return 1

        if args.server_command == "start":
            success = launcher.start_backend(port=args.port, detach=not args.foreground)
            return 0 if success else 1

        elif args.server_command == "stop":
            success = launcher.stop_backend()
            return 0 if success else 1

        elif args.server_command == "restart":
            success = launcher.restart_backend(port=getattr(args, "port", None))
            return 0 if success else 1

        elif args.server_command == "status":
            launcher.show_status()
            return 0

    elif args.command == "status":
        launcher.show_status()
        return 0

    elif args.command == "logs":
        launcher.show_logs(lines=args.lines, follow=args.follow)
        return 0

    elif args.command == "clean":
        launcher.clean_profile()
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
