/**
 * UV Package Manager utilities
 * Handles downloading and managing the uv Python package manager
 */
/**
 * Ensure uv is available, downloading if necessary
 */
export declare function ensureUv(): Promise<string>;
/**
 * Check if uv is available without downloading
 */
export declare function checkUv(): Promise<{
    available: boolean;
    path?: string;
}>;
/**
 * Get uv version
 */
export declare function getUvVersion(uvPath: string): Promise<string>;
/**
 * Setup Python environment using uv
 */
export declare function setupPythonEnvironment(uvPath: string, pythonVersion?: string): Promise<string>;
/**
 * Install Python dependencies using uv
 */
export declare function installDependencies(uvPath: string, venvPath: string, projectRoot: string): Promise<void>;
