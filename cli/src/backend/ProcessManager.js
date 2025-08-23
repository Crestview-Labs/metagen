/**
 * Process management utilities for backend server
 */
import { spawn } from 'child_process';
import { createWriteStream } from 'fs';
import { EventEmitter } from 'events';
import * as fs from 'fs-extra';
import { ProcessError } from '../types/index.js';
import { readPidFile, writePidFile, removePidFile } from '../utils/paths.js';
export class ProcessManager extends EventEmitter {
    processes = new Map();
    /**
     * Spawn a new process
     */
    async spawn(command, args, options = {}) {
        const { cwd, env, detached = false, logFile } = options;
        // Create log stream if needed
        let logStream;
        if (logFile) {
            await fs.ensureFile(logFile);
            logStream = createWriteStream(logFile, { flags: 'a' });
        }
        return new Promise((resolve, reject) => {
            // Spawn the process
            const childProcess = spawn(command, args, {
                cwd,
                env: { ...process.env, ...env },
                detached,
                stdio: ['ignore', 'pipe', 'pipe']
            });
            // Handle spawn errors immediately
            let errorHandled = false;
            childProcess.on('error', (error) => {
                logStream?.end();
                if (!errorHandled) {
                    errorHandled = true;
                    if (error.code === 'ENOENT') {
                        reject(new ProcessError(`Failed to spawn process: ${command} - command not found`));
                    }
                    else {
                        reject(new ProcessError(`Failed to spawn process: ${command} - ${error.message}`));
                    }
                }
            });
            // Check if process started successfully
            if (!childProcess.pid) {
                logStream?.end();
                reject(new ProcessError(`Failed to spawn process: ${command}`));
                return;
            }
            const handle = {
                process: childProcess,
                pid: childProcess.pid,
                logStream
            };
            // Pipe output to log file if configured
            if (logStream) {
                childProcess.stdout?.pipe(logStream);
                childProcess.stderr?.pipe(logStream);
            }
            // Handle process exit
            childProcess.on('exit', (code, signal) => {
                this.emit('exit', { pid: childProcess.pid, code, signal });
                logStream?.end();
                if (childProcess.pid) {
                    this.processes.delete(childProcess.pid.toString());
                }
            });
            // Track the process
            this.processes.set(childProcess.pid.toString(), handle);
            // Resolve with handle once process is started
            resolve(handle);
        });
    }
    /**
     * Check if a process is running
     */
    isRunning(pid) {
        try {
            // Send signal 0 to check if process exists
            process.kill(pid, 0);
            return true;
        }
        catch (error) {
            // ESRCH means process doesn't exist
            return error.code !== 'ESRCH';
        }
    }
    /**
     * Kill a process
     */
    async kill(pid, signal = 'SIGTERM') {
        try {
            process.kill(pid, signal);
        }
        catch (error) {
            if (error.code !== 'ESRCH') {
                throw new ProcessError(`Failed to kill process ${pid}: ${error.message}`);
            }
        }
    }
    /**
     * Kill a process with timeout
     */
    async killWithTimeout(pid, timeout = 10000, signal = 'SIGTERM') {
        await this.kill(pid, signal);
        const startTime = Date.now();
        while (Date.now() - startTime < timeout) {
            if (!this.isRunning(pid)) {
                return;
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        // Force kill if still running
        await this.kill(pid, 'SIGKILL');
    }
    /**
     * Wait for a process to exit
     */
    async waitForExit(pid, timeout) {
        const startTime = Date.now();
        while (this.isRunning(pid)) {
            if (timeout && Date.now() - startTime > timeout) {
                throw new ProcessError(`Process ${pid} did not exit within timeout`);
            }
            await new Promise(resolve => setTimeout(resolve, 100));
        }
    }
    /**
     * Read PID from file and check if process is running
     */
    async checkPidFile(pidFile) {
        const pid = await readPidFile(pidFile);
        if (!pid) {
            return { pid: null, running: false };
        }
        const running = this.isRunning(pid);
        // Clean up stale PID file
        if (!running) {
            await removePidFile(pidFile);
        }
        return { pid, running };
    }
    /**
     * Write PID to file
     */
    async writePidFile(pidFile, pid) {
        await writePidFile(pidFile, pid);
    }
    /**
     * Remove PID file
     */
    async removePidFile(pidFile) {
        await removePidFile(pidFile);
    }
    /**
     * Get process info
     */
    getProcessInfo(pid) {
        // This would require platform-specific implementation
        // For now, return basic info
        if (!this.isRunning(pid)) {
            return null;
        }
        return {
            cpu: 0,
            memory: 0
        };
    }
    /**
     * Clean up all tracked processes
     */
    async cleanup() {
        const promises = [];
        for (const [, handle] of this.processes) {
            promises.push(this.killWithTimeout(handle.pid, 5000).catch(() => {
                // Ignore errors during cleanup
            }));
            handle.logStream?.end();
        }
        await Promise.all(promises);
        this.processes.clear();
    }
    /**
     * Check if a port is available
     */
    async isPortAvailable(port, host = '127.0.0.1') {
        return new Promise((resolve) => {
            const net = require('net');
            const server = net.createServer();
            server.once('error', () => {
                resolve(false);
            });
            server.once('listening', () => {
                server.close();
                resolve(true);
            });
            server.listen(port, host);
        });
    }
    /**
     * Find an available port
     */
    async findAvailablePort(startPort, endPort = startPort + 100, host = '127.0.0.1') {
        for (let port = startPort; port <= endPort; port++) {
            if (await this.isPortAvailable(port, host)) {
                return port;
            }
        }
        throw new ProcessError(`No available ports found between ${startPort} and ${endPort}`);
    }
}
