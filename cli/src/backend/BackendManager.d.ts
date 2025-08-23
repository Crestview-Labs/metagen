/**
 * Backend server lifecycle management
 */
import { EventEmitter } from 'events';
import { Profile, BackendOptions, HealthStatus, ProcessInfo } from '../types/index.js';
export declare class BackendManager extends EventEmitter {
    private profile;
    private processManager;
    private processHandle?;
    private healthCheckInterval?;
    private startupTimeout;
    private healthCheckIntervalMs;
    private isShuttingDown;
    constructor(profile: Profile);
    /**
     * Start the backend server
     */
    start(options?: Partial<BackendOptions>): Promise<void>;
    /**
     * Stop the backend server
     */
    stop(): Promise<void>;
    /**
     * Restart the backend server
     */
    restart(options?: Partial<BackendOptions>): Promise<void>;
    /**
     * Check if backend is running
     */
    isRunning(): Promise<boolean>;
    /**
     * Get backend health status
     */
    getHealth(port?: number): Promise<HealthStatus>;
    /**
     * Get process info
     */
    getProcessInfo(): Promise<ProcessInfo | null>;
    /**
     * Wait for backend to be healthy
     */
    private waitForHealthy;
    /**
     * Start health monitoring
     */
    private startHealthMonitoring;
    /**
     * Handle unhealthy backend
     */
    private handleUnhealthy;
    /**
     * Handle process exit
     */
    private handleProcessExit;
    /**
     * Check required dependencies and return paths
     */
    private checkDependencies;
    /**
     * Find available port
     */
    private findAvailablePort;
    /**
     * Clean up resources
     */
    private cleanup;
    /**
     * Destroy the manager
     */
    destroy(): Promise<void>;
}
