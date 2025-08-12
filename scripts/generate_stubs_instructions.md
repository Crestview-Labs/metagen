# API Stub Generation Instructions for Claude Code

## Overview
Generate TypeScript and Swift client stubs for the Metagen FastAPI backend. All stubs must exactly match the current API version with no backward compatibility needed (UI and backend are bundled together).

## Pre-requisites
1. Check that `version.json` exists and has the current version
2. Ensure all API changes have been committed
3. Read the current version from `version.json`

## Step 1: Analyze the FastAPI Backend

### 1.1 Analyze All Route Files
Check every file in `api/routes/`:
- `api/routes/chat.py` - Chat endpoints
- `api/routes/auth.py` - Authentication endpoints  
- `api/routes/system.py` - System info endpoints
- `api/routes/tools.py` - Tool management endpoints
- `api/routes/memory.py` - Memory management endpoints
- `api/routes/telemetry.py` - Telemetry/tracing endpoints

For each route, extract:
- HTTP method (GET, POST, etc.)
- Path (e.g., `/api/chat`, `/api/auth/login`)
- Request body type (if any)
- Response type
- Whether it's a streaming endpoint (returns EventSourceResponse)

### 1.2 Analyze All Pydantic Models
Check every file in `api/models/`:
- `api/models/chat.py` - Chat request/response models
- `api/models/auth.py` - Auth models
- `api/models/system.py` - System info models
- `api/models/common.py` - Shared models

For each model, note:
- All fields and their types
- Optional vs required fields
- Default values
- Enums and literal types

### 1.3 Check Server Configuration
In `api/server.py`, check for:
- Middleware that adds headers
- CORS configuration
- Base path configuration

## Step 2: Generate TypeScript Stubs

Create the following directory structure:
```
api/ts/
├── src/
│   ├── api.ts        # API client class
│   ├── types.ts      # TypeScript interfaces
│   ├── streaming.ts  # SSE handling
│   ├── errors.ts     # Error types
│   └── version.ts    # Version from version.json
├── tests/
│   ├── api.test.ts
│   └── types.test.ts
├── package.json
└── tsconfig.json
```

### 2.1 Create api/ts/src/version.ts
```typescript
// Auto-generated from version.json - DO NOT EDIT
export const API_VERSION = "0.1.0";  // Use actual version from version.json
export const BUILD_VERSION = "2025.01.08.001";  // Use actual build from version.json
```

### 2.2 Create api/ts/src/types.ts
Convert ALL Pydantic models to TypeScript interfaces:

```typescript
// Auto-generated from api/models - DO NOT EDIT

// From api/models/chat.py
export interface ChatRequest {
  message: string;
  context?: Record<string, any>;
  metadata?: Record<string, any>;
  session_id?: string;
}

export interface ChatResponse {
  responses: UIResponseModel[];
  session_id: string;
  metadata?: Record<string, any>;
}

export interface UIResponseModel {
  type: 'text' | 'error' | 'tool_use' | 'partial_json' | 'success';
  text?: string;
  error?: string;
  tool_use?: ToolUse;
  partial_json?: string;
}

// From api/models/auth.py
export interface AuthStatus {
  authenticated: boolean;
  message: string;
  user_id?: string;
  email?: string;
}

export interface AuthLoginRequest {
  username: string;
  password: string;
  remember_me?: boolean;
}

// Include ALL models from ALL files
```

### 2.3 Create api/ts/src/api.ts
Create methods for ALL endpoints:

```typescript
import { API_VERSION } from './version';
import * as types from './types';

export class MetagenAPI {
  constructor(private baseURL: string = 'http://localhost:8000') {}

  // Chat endpoints
  async chat(request: types.ChatRequest): Promise<types.ChatResponse> {
    const response = await this.fetch('/api/chat', {
      method: 'POST',
      body: JSON.stringify(request)
    });
    return response.json();
  }

  async *chatStream(request: types.ChatRequest): AsyncIterable<types.UIResponseModel> {
    // SSE implementation
  }

  // Auth endpoints
  async login(request: types.AuthLoginRequest): Promise<types.AuthResponse> {
    const response = await this.fetch('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(request)
    });
    return response.json();
  }

  async logout(): Promise<void> {
    await this.fetch('/api/auth/logout', { method: 'POST' });
  }

  async getAuthStatus(): Promise<types.AuthStatus> {
    const response = await this.fetch('/api/auth/status');
    return response.json();
  }

  // System endpoints
  async getSystemInfo(): Promise<types.SystemInfo> {
    const response = await this.fetch('/api/system/info');
    return response.json();
  }

  // Tools endpoints
  async getTools(): Promise<types.ToolsResponse> {
    const response = await this.fetch('/api/tools/list');
    return response.json();
  }

  // Memory endpoints
  async clearMemory(): Promise<void> {
    await this.fetch('/api/memory/clear', { method: 'POST' });
  }

  // Include methods for ALL endpoints found in api/routes/

  private async fetch(path: string, options?: RequestInit): Promise<Response> {
    const response = await fetch(`${this.baseURL}${path}`, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        'X-API-Version': API_VERSION,
        ...options?.headers,
      }
    });

    if (!response.ok) {
      throw new Error(`API Error: ${response.statusText}`);
    }

    return response;
  }
}
```

### 2.4 Create api/ts/package.json
```json
{
  "name": "@metagen/api-client",
  "version": "0.1.0",
  "type": "module",
  "main": "dist/index.js",
  "types": "dist/index.d.ts",
  "scripts": {
    "build": "tsc",
    "test": "vitest",
    "type-check": "tsc --noEmit"
  },
  "devDependencies": {
    "@types/node": "^20.0.0",
    "typescript": "^5.0.0",
    "vitest": "^1.0.0"
  }
}
```

### 2.5 Create api/ts/tsconfig.json
```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "lib": ["ES2022", "DOM"],
    "outDir": "./dist",
    "rootDir": "./src",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "forceConsistentCasingInFileNames": true,
    "declaration": true,
    "declarationMap": true,
    "sourceMap": true,
    "moduleResolution": "node"
  },
  "include": ["src/**/*"],
  "exclude": ["node_modules", "dist", "tests"]
}
```

## Step 3: Generate Swift Stubs

Create the following directory structure:
```
api/swift/
├── Sources/
│   └── MetagenAPI/
│       ├── API.swift
│       ├── Models.swift
│       ├── Streaming.swift
│       ├── Errors.swift
│       └── Version.swift
├── Tests/
│   └── MetagenAPITests/
│       └── APITests.swift
└── Package.swift
```

### 3.1 Create api/swift/Sources/MetagenAPI/Version.swift
```swift
// Auto-generated from version.json - DO NOT EDIT
public struct APIVersion {
    public static let version = "0.1.0"  // Use actual version
    public static let build = "2025.01.08.001"  // Use actual build
}
```

### 3.2 Create api/swift/Sources/MetagenAPI/Models.swift
Convert ALL Pydantic models to Swift structs:

```swift
import Foundation

// From api/models/chat.py
public struct ChatRequest: Codable {
    public let message: String
    public let context: [String: Any]?
    public let metadata: [String: Any]?
    public let sessionId: String?
    
    enum CodingKeys: String, CodingKey {
        case message
        case context
        case metadata
        case sessionId = "session_id"
    }
}

// Include ALL models
```

### 3.3 Create api/swift/Sources/MetagenAPI/API.swift
```swift
import Foundation

public class MetagenAPI {
    private let baseURL: String
    
    public init(baseURL: String = "http://localhost:8000") {
        self.baseURL = baseURL
    }
    
    // Include methods for ALL endpoints
}
```

### 3.4 Create api/swift/Package.swift
```swift
// swift-tools-version:5.7
import PackageDescription

let package = Package(
    name: "MetagenAPI",
    platforms: [.macOS(.v12), .iOS(.v15)],
    products: [
        .library(name: "MetagenAPI", targets: ["MetagenAPI"])
    ],
    targets: [
        .target(name: "MetagenAPI", path: "Sources"),
        .testTarget(name: "MetagenAPITests", dependencies: ["MetagenAPI"], path: "Tests")
    ]
)
```

## Step 4: Validation

After generating all files:

1. **Verify TypeScript compilation:**
   ```bash
   cd api/ts
   pnpm install
   pnpm tsc --noEmit
   ```

2. **Verify Swift compilation (macOS only):**
   ```bash
   cd api/swift
   swift build
   ```

3. **Check version consistency:**
   - Ensure api/ts/src/version.ts matches version.json
   - Ensure api/swift/Sources/MetagenAPI/Version.swift matches version.json

4. **Completeness check:**
   - Every endpoint in api/routes/ has a corresponding method
   - Every model in api/models/ has a corresponding type
   - All optional fields are properly marked

## Important Notes

1. **No backward compatibility** - The generated stubs only need to work with the current version
2. **Include everything** - Every endpoint and model must be included
3. **Streaming support** - Chat endpoints that return EventSourceResponse need special handling
4. **Type safety** - Preserve all type information from Pydantic models
5. **Version header** - All API calls must include X-API-Version header

## Completion Checklist

- [ ] All route files analyzed
- [ ] All model files analyzed  
- [ ] TypeScript stubs generated
- [ ] Swift stubs generated
- [ ] Version files match version.json
- [ ] TypeScript compiles without errors
- [ ] Swift compiles without errors (if on macOS)
- [ ] All endpoints have methods
- [ ] All models have types