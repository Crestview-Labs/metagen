/**
 * Process management utilities for backend server
 */
import { ChildProcess } from 'child_process';
import { WriteStream } from 'fs';
import { EventEmitter } from 'events';
export interface SpawnOptions {
    cwd?: string;
    env?: Record<string, string>;
    detached?: boolean;
    stdio?: 'pipe' | 'ignore' | 'inherit';
    logFile?: string;
}
export interface ProcessHandle {
    process: ChildProcess;
    pid: number;
    logStream?: WriteStream;
}
export declare class ProcessManager extends EventEmitter {
    private processes;
    /**
     * Spawn a new process
     */
    spawn(command: string, args: string[], options?: SpawnOptions): Promise<ProcessHandle>;
    /**
     * Check if a process is running
     */
    isRunning(pid: number): boolean;
    /**
     * Kill a process
     */
    kill(pid: number, signal?: NodeJS.Signals): Promise<void>;
    /**
     * Kill a process with timeout
     */
    killWithTimeout(pid: number, timeout?: number, signal?: NodeJS.Signals): Promise<void>;
    /**
     * Wait for a process to exit
     */
    waitForExit(pid: number, timeout?: number): Promise<void>;
    /**
     * Read PID from file and check if process is running
     */
    checkPidFile(pidFile: string): Promise<{
        pid: number | null;
        running: boolean;
    }>;
    /**
     * Write PID to file
     */
    writePidFile(pidFile: string, pid: number): Promise<void>;
    /**
     * Remove PID file
     */
    removePidFile(pidFile: string): Promise<void>;
    /**
     * Get process info
     */
    getProcessInfo(pid: number): {
        cpu?: number;
        memory?: number;
    } | null;
    /**
     * Clean up all tracked processes
     */
    cleanup(): Promise<void>;
    /**
     * Check if a port is available
     */
    isPortAvailable(port: number, host?: string): Promise<boolean>;
    /**
     * Find an available port
     */
    findAvailablePort(startPort: number, endPort?: number, host?: string): Promise<number>;
}
