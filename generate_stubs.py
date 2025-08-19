#!/usr/bin/env python3
"""
Generate TypeScript and Swift client stubs from FastAPI's OpenAPI spec.
No backward compatibility needed - UI and backend are bundled together.
"""

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
import yaml

# Configuration
API_BASE_URL = "http://localhost:8080"
VERSION_FILE = Path("api/version.json")
MAIN_VERSION_FILE = Path("version.json")


def load_version_data() -> dict[str, Any]:
    """Load existing version data or initialize"""
    if VERSION_FILE.exists():
        with open(VERSION_FILE) as f:
            data: dict[str, Any] = json.load(f)
            return data

    # Initialize with timestamp-based version
    now = datetime.now(timezone.utc)
    return {"version": now.strftime("%Y.%m.%d.%H%M%S"), "generated_at": now.isoformat()}


def save_version_data(version_data: dict[str, Any]) -> None:
    """Save version data to file"""
    VERSION_FILE.parent.mkdir(exist_ok=True)
    with open(VERSION_FILE, "w") as f:
        json.dump(version_data, f, indent=2)


def fetch_openapi_spec() -> dict[str, Any]:
    """Fetch OpenAPI spec from running FastAPI server"""
    print("📡 Fetching OpenAPI spec from FastAPI...")
    try:
        response = requests.get(f"{API_BASE_URL}/openapi.json", timeout=5)
        response.raise_for_status()
        spec: dict[str, Any] = response.json()
        return spec
    except requests.exceptions.ConnectionError:
        print("❌ Failed to connect to FastAPI server")
        print("   Make sure server is running: uv run python main.py")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error fetching OpenAPI spec: {e}")
        sys.exit(1)


def save_spec(spec: dict[str, Any], path: Path) -> None:
    """Save OpenAPI spec to file"""
    path.parent.mkdir(exist_ok=True)
    with open(path, "w") as f:
        json.dump(spec, f, indent=2)


def fix_typescript_imports(directory: Path) -> None:
    """Fix TypeScript imports to add .js extensions for ES modules"""
    import re

    for ts_file in directory.rglob("*.ts"):
        if ts_file.is_file():
            content = ts_file.read_text()
            original_content = content

            # Add .js extension to relative imports in generated files
            # Match: from './something' or from '../something' (but not if already has .js or .json)
            content = re.sub(
                r"from ['\"](\.\./[^'\"]+|\.\/[^'\"]+)(?<!\.js)(?<!\.json)(?<!\.ts)['\"]",
                r"from '\1.js'",
                content,
            )

            # Write back only if changed
            if content != original_content:
                ts_file.write_text(content)


def generate_typescript_stubs(spec_path: Path, version: str) -> bool:
    """Generate TypeScript client stubs using OpenAPI generator"""
    print("\n📘 Generating TypeScript stubs...")

    output_dir = Path("api/ts/generated")
    output_dir.parent.mkdir(exist_ok=True)

    # Clean up old generated files
    if output_dir.exists():
        print("   Cleaning up old TypeScript stubs...")
        shutil.rmtree(output_dir)

    # Also clean dist directory to ensure fresh builds
    dist_dir = Path("api/ts/dist")
    if dist_dir.exists():
        print("   Cleaning up old TypeScript build artifacts...")
        shutil.rmtree(dist_dir)

    output_dir.mkdir(exist_ok=True)

    # Try @hey-api/openapi-ts first (modern maintained fork)
    cmd = [
        "npx",
        "@hey-api/openapi-ts",
        "-i",
        str(spec_path),
        "-o",
        str(output_dir),
        "-c",
        "fetch",
        "--name",
        "MetagenClient",
        "--useOptions",
    ]

    try:
        print("   Using @hey-api/openapi-ts generator...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd, result.stderr)

        # Fix imports for ES modules
        fix_typescript_imports(output_dir)
        print(f"✅ TypeScript stubs generated (v{version})")
    except subprocess.CalledProcessError as e:
        print(f"   @hey-api/openapi-ts failed: {e.stderr if hasattr(e, 'stderr') else str(e)}")
        # Fallback to openapi-typescript-codegen
        print("   Falling back to openapi-typescript-codegen...")
        cmd_fallback = [
            "npx",
            "openapi-typescript-codegen",
            "--input",
            str(spec_path),
            "--output",
            str(output_dir),
            "--client",
            "fetch",
            "--useOptions",
        ]
        try:
            subprocess.run(cmd_fallback, check=True, capture_output=True, text=True)
            # Fix imports for ES modules
            fix_typescript_imports(output_dir)
            print(f"✅ TypeScript stubs generated with fallback (v{version})")
        except subprocess.CalledProcessError as e2:
            print(f"❌ Failed to generate TypeScript stubs: {e2.stderr}")
            print("   Install generator: npm install -g @hey-api/openapi-ts")
            return False

    # Create streaming wrapper on top of generated code
    create_typescript_wrapper(version)

    # Fix imports in all TypeScript files (generated, src, tests)
    fix_typescript_imports(Path("api/ts"))

    # Write version file
    version_file = Path("api/ts/VERSION")
    version_file.write_text(version)

    return True


def create_typescript_wrapper(version: str) -> None:
    """Create TypeScript SSE streaming wrapper and additional utilities"""
    print("🔧 Creating TypeScript streaming wrapper...")

    ts_dir = Path("api/ts")
    src_dir = ts_dir / "src"
    src_dir.mkdir(parents=True, exist_ok=True)

    # Create version file
    version_content = f'''// Auto-generated from version.json - DO NOT EDIT
export const API_VERSION = "{version}";
'''
    (src_dir / "version.ts").write_text(version_content)

    # Create streaming wrapper
    wrapper_path = src_dir / "streaming.ts"
    wrapper_content = f"""/**
 * SSE Streaming wrapper for Metagen API v{version}
 * Generated: {datetime.now(timezone.utc).isoformat()}
 */

import {{ OpenAPI, ChatService }} from '../generated/index';
import type {{ ChatRequest, CancelablePromise }} from '../generated/index';

export interface StreamOptions {{
  signal?: AbortSignal;
  onError?: (error: Error) => void;
  retryDelay?: number;
}}

// Extract the SSE message type from the generated service
// This extracts the union type from the ChatService.chatStreamApiChatStreamPost return type
type ExtractPromiseType<T> = T extends CancelablePromise<infer U> ? U : never;
type ChatStreamReturnType = ReturnType<typeof ChatService.chatStreamApiChatStreamPost>;
export type SSEMessage = ExtractPromiseType<ChatStreamReturnType>;

export async function* parseSSEStream(
  response: Response,
  options?: StreamOptions
): AsyncGenerator<SSEMessage, void, unknown> {{
  if (!response.body) {{
    throw new Error('Response body is empty');
  }}

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {{
    while (true) {{
      const {{ done, value }} = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, {{ stream: true }});
      const lines = buffer.split('\\n');
      buffer = lines.pop() || '';

      for (const line of lines) {{
        if (line.trim() === '') continue;
        
        if (line.startsWith('data: ')) {{
          const data = line.slice(6);
          if (data === '[DONE]') {{
            return;
          }}
          
          try {{
            const message = JSON.parse(data) as SSEMessage;
            yield message;
          }} catch (e) {{
            console.warn('Failed to parse SSE data:', data);
          }}
        }}
      }}
    }}
  }} catch (error) {{
    if (options?.onError) {{
      options.onError(error as Error);
    }} else {{
      throw error;
    }}
  }} finally {{
    reader.releaseLock();
  }}
}}

export class MetagenStreamingClient {{
  private baseURL: string;
  
  constructor(baseURL: string = 'http://localhost:8080') {{
    this.baseURL = baseURL;
    OpenAPI.BASE = baseURL;
  }}
  
  /**
   * Stream chat responses using Server-Sent Events
   */
  async *chatStream(request: ChatRequest): AsyncGenerator<SSEMessage, void, unknown> {{
    const response = await fetch(`${{this.baseURL}}/api/chat/stream`, {{
      method: 'POST',
      headers: {{
        'Content-Type': 'application/json',
        'Accept': 'text/event-stream',
      }},
      body: JSON.stringify(request)
    }});

    if (!response.ok) {{
      throw new Error(`HTTP error! status: ${{response.status}}`);
    }}

    for await (const message of parseSSEStream(response)) {{
      yield message;
      // Check if this is an AgentMessage with final flag set
      if (message.type === 'agent' && (message as any).final) {{
        return;
      }}
    }}
  }}
}}

export const VERSION = '{version}';
"""

    wrapper_path.write_text(wrapper_content)

    # Create index.ts
    index_content = f"""// Metagen API Client v{version}
export * from '../generated/index';
export {{ MetagenStreamingClient, parseSSEStream, VERSION }} from './streaming';
export type {{ StreamOptions, SSEMessage }} from './streaming';
export {{ API_VERSION }} from './version';

// Default export
import {{ MetagenStreamingClient }} from './streaming';
export default MetagenStreamingClient;
"""

    (src_dir / "index.ts").write_text(index_content)

    # Create/update package.json
    create_package_files(version)

    print("✅ TypeScript wrapper created")


def generate_swift_stubs(spec_path: Path, version: str) -> bool:
    """Generate Swift client stubs using Swift Package plugin"""
    print("\n🍎 Generating Swift stubs...")

    # Clean up old generated files
    output_dir = Path("api/swift/Sources/MetagenAPI")
    if output_dir.exists():
        print("   Cleaning up old Swift stubs...")
        # Remove only generated files, keep the config
        for file in output_dir.glob("*.swift"):
            file.unlink()
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create configuration file for the Swift Package plugin
    config_path = output_dir / "openapi-generator-config.yaml"
    config = {"generate": ["types", "client"], "accessModifier": "public"}

    with open(config_path, "w") as f:
        yaml.dump(config, f)

    # Copy spec to the source directory (required by Swift Package plugin)
    swift_spec_path = output_dir / "openapi.json"
    shutil.copy(spec_path, swift_spec_path)

    # Create wrapper files BEFORE running Swift build (so the target isn't empty)
    create_swift_wrapper(version)

    # The Swift Package plugin generates code during build
    # We trigger a build to generate the stubs
    cmd = ["swift", "build", "--package-path", "api/swift"]

    try:
        print("   Running Swift Package build to generate stubs...")
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"✅ Swift stubs generated (v{version})")
        else:
            # Check if stubs were generated despite build errors
            generated_files = list(output_dir.glob("*.swift"))
            if generated_files:
                print(f"✅ Swift stubs generated with warnings (v{version})")
            else:
                print("⚠️  Swift generation had issues")
                if result.stderr:
                    print(f"   Error: {result.stderr[:300]}...")
    except FileNotFoundError:
        print("⚠️  Swift generation skipped (Swift not found)")
        print("   Ensure Xcode and Swift are installed")
        return False

    # Write version file
    version_file = Path("api/swift/VERSION")
    version_file.write_text(version)

    return True


def create_swift_wrapper(version: str) -> None:
    """Create Swift version info and additional utilities"""
    print("🔧 Creating Swift utilities...")

    output_dir = Path("api/swift/Sources/MetagenAPI")

    # Create Version.swift
    version_path = output_dir / "Version.swift"
    version_content = f'''// Auto-generated version info - DO NOT EDIT
// Generated: {datetime.now(timezone.utc).isoformat()}

public struct APIVersion {{
    public static let version = "{version}"
    public static let generatedAt = "{datetime.now(timezone.utc).isoformat()}"
}}
'''
    version_path.write_text(version_content)

    print("✅ Swift utilities created")

    # Write version file
    version_file = Path("api/swift/VERSION")
    version_file.write_text(version)

    # Create SSE streaming wrapper
    create_swift_streaming_wrapper(version)


def create_swift_streaming_wrapper(version: str) -> None:
    """Create Swift SSE streaming wrapper"""
    wrapper_content = f"""// SSE Streaming wrapper for Metagen API v{version}
// Generated: {datetime.now(timezone.utc).isoformat()}

import Foundation
import OpenAPIRuntime
import OpenAPIURLSession

/// SSE Streaming wrapper for Metagen API
public class MetagenStreamingClient {{
    private let client: Client
    private let baseURL: URL
    
    public init(baseURL: String = "http://localhost:8080") throws {{
        self.baseURL = URL(string: baseURL)!
        self.client = Client(
            serverURL: self.baseURL,
            transport: URLSessionTransport()
        )
    }}
    
    /// Stream chat responses using Server-Sent Events
    public func chatStream(
        message: String,
        sessionId: String
    ) -> AsyncThrowingStream<Any, Error> {{
        AsyncThrowingStream {{ continuation in
            Task {{
                do {{
                    let url = baseURL.appendingPathComponent("/api/chat/stream")
                    var request = URLRequest(url: url)
                    request.httpMethod = "POST"
                    request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    request.setValue("text/event-stream", forHTTPHeaderField: "Accept")
                    
                    let body = ["message": message, "session_id": sessionId]
                    request.httpBody = try JSONSerialization.data(withJSONObject: body)
                    
                    let (bytes, _) = try await URLSession.shared.bytes(for: request)
                    
                    for try await line in bytes.lines {{
                        if line.hasPrefix("data: ") {{
                            let jsonStr = String(line.dropFirst(6))
                            if let data = jsonStr.data(using: .utf8) {{
                                let response = try JSONSerialization.jsonObject(with: data)
                                continuation.yield(response)
                                
                                // Check for completion
                                if let dict = response as? [String: Any],
                                   let type = dict["type"] as? String,
                                   type == "complete" {{
                                    continuation.finish()
                                    return
                                }}
                            }}
                        }}
                    }}
                    continuation.finish()
                }} catch {{
                    continuation.finish(throwing: error)
                }}
            }}
        }}
    }}
}}
"""

    # Save the streaming wrapper
    wrapper_dir = Path("api/swift/Sources/MetagenAPI")
    wrapper_dir.mkdir(parents=True, exist_ok=True)
    wrapper_path = wrapper_dir / "StreamingClient.swift"
    wrapper_path.write_text(wrapper_content)

    print("✅ Swift streaming wrapper created")


def create_package_files(version: str) -> None:
    """Create package files for TypeScript"""
    print("\n📦 Creating TypeScript package files...")

    ts_dir = Path("api/ts")

    # package.json
    package_json = {
        "name": "@metagen/api-client",
        "version": version,
        "type": "module",
        "main": "dist/index.js",
        "types": "dist/index.d.ts",
        "scripts": {"build": "tsc", "test": "vitest", "type-check": "tsc --noEmit"},
        "dependencies": {},
        "devDependencies": {"@types/node": "^20.0.0", "typescript": "^5.0.0", "vitest": "^1.0.0"},
    }

    package_path = ts_dir / "package.json"
    with open(package_path, "w") as f:
        json.dump(package_json, f, indent=2)

    # tsconfig.json
    tsconfig = {
        "compilerOptions": {
            "target": "ES2022",
            "module": "ESNext",
            "lib": ["ES2022", "DOM"],
            "outDir": "./dist",
            "rootDir": "./",
            "strict": True,
            "esModuleInterop": True,
            "skipLibCheck": True,
            "forceConsistentCasingInFileNames": True,
            "declaration": True,
            "declarationMap": True,
            "sourceMap": True,
            "moduleResolution": "node",
        },
        "include": ["src/**/*", "generated/**/*"],
        "exclude": ["node_modules", "dist", "tests"],
    }

    config_path = ts_dir / "tsconfig.json"
    with open(config_path, "w") as f:
        json.dump(tsconfig, f, indent=2)

    print("✅ Package files created")


def main() -> None:
    """Main generation workflow"""
    parser = argparse.ArgumentParser(description="Generate API client stubs")
    parser.add_argument("--skip-typescript", action="store_true", help="Skip TypeScript generation")
    parser.add_argument("--skip-swift", action="store_true", help="Skip Swift generation")
    args = parser.parse_args()

    # Load main project version
    if not MAIN_VERSION_FILE.exists():
        print("❌ Main version.json not found!")
        sys.exit(1)

    with open(MAIN_VERSION_FILE) as f:
        main_version_data = json.load(f)

    project_version = main_version_data["version"]

    # Load or initialize API version tracking
    version_data = load_version_data()
    now = datetime.now(timezone.utc)

    print("🚀 Metagen Stub Generation")
    print(f"   Version: {project_version}")
    print("=" * 50)

    # Fetch current OpenAPI spec
    current_spec = fetch_openapi_spec()

    # Save spec
    current_spec["info"]["version"] = project_version
    spec_path = Path("api/openapi.json")
    save_spec(current_spec, spec_path)

    # Generate TypeScript stubs
    if not args.skip_typescript:
        if not generate_typescript_stubs(spec_path, project_version):
            print("⚠️  TypeScript generation had issues")

    # Generate Swift stubs
    if not args.skip_swift:
        if not generate_swift_stubs(spec_path, project_version):
            print("⚠️  Swift generation had issues")

    # Update version tracking
    version_data = {
        "version": project_version,
        "generated_at": now.isoformat(),
        "typescript": {"version": project_version, "generated": now.isoformat()},
        "swift": {"version": project_version, "generated": now.isoformat()},
    }
    save_version_data(version_data)

    print("\n" + "=" * 50)
    print("✨ Stub generation complete!")
    print(f"   Version: {project_version}")
    print("\n📋 Next steps:")
    if not args.skip_typescript:
        print("  TypeScript:")
        print("    Build:  cd api/ts && npm install && npm run build")
        print("    Test:   cd api/ts && npm test")
    if not args.skip_swift:
        print("  Swift:")
        print("    Build:  cd api/swift && swift build")
        print("    Test:   cd api/swift && swift test")


if __name__ == "__main__":
    main()
