/**
 * Process management utilities for backend server
 */

import { spawn, ChildProcess } from 'child_process';
import { createWriteStream, WriteStream } from 'fs';
import { EventEmitter } from 'events';
import * as fs from 'fs-extra';
import * as net from 'net';
import { ProcessError } from '../types/index.js';
import { readPidFile, writePidFile, removePidFile } from '../utils/paths.js';

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

export class ProcessManager extends EventEmitter {
  private processes: Map<string, ProcessHandle> = new Map();

  /**
   * Spawn a new process
   */
  async spawn(
    command: string,
    args: string[],
    options: SpawnOptions = {}
  ): Promise<ProcessHandle> {
    const { cwd, env, detached = false, logFile } = options;

    // Create log stream if needed
    let logStream: WriteStream | undefined;
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
      childProcess.on('error', (error: any) => {
        logStream?.end();
        if (!errorHandled) {
          errorHandled = true;
          if (error.code === 'ENOENT') {
            reject(new ProcessError(`Failed to spawn process: ${command} - command not found`));
          } else {
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

      const handle: ProcessHandle = {
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
        this.emit('exit', { pid: childProcess.pid!, code, signal });
        logStream?.end();
        if (childProcess.pid) {
          this.processes.delete(childProcess.pid.toString());
        }
      });

      // Track the process
      this.processes.set(childProcess.pid!.toString(), handle);

      // Resolve with handle once process is started
      resolve(handle);
    });
  }

  /**
   * Check if a process is running
   */
  isRunning(pid: number): boolean {
    try {
      // Send signal 0 to check if process exists
      process.kill(pid, 0);
      return true;
    } catch (error: any) {
      // ESRCH means process doesn't exist
      return error.code !== 'ESRCH';
    }
  }

  /**
   * Kill a process
   */
  async kill(pid: number, signal: NodeJS.Signals = 'SIGTERM'): Promise<void> {
    try {
      process.kill(pid, signal);
    } catch (error: any) {
      if (error.code !== 'ESRCH') {
        throw new ProcessError(`Failed to kill process ${pid}: ${error.message}`);
      }
    }
  }

  /**
   * Kill a process with timeout
   */
  async killWithTimeout(
    pid: number,
    timeout: number = 10000,
    signal: NodeJS.Signals = 'SIGTERM'
  ): Promise<void> {
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
  async waitForExit(pid: number, timeout?: number): Promise<void> {
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
  async checkPidFile(pidFile: string): Promise<{ pid: number | null; running: boolean }> {
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
  async writePidFile(pidFile: string, pid: number): Promise<void> {
    await writePidFile(pidFile, pid);
  }

  /**
   * Remove PID file
   */
  async removePidFile(pidFile: string): Promise<void> {
    await removePidFile(pidFile);
  }

  /**
   * Get process info
   */
  getProcessInfo(pid: number): { cpu?: number; memory?: number } | null {
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
  async cleanup(): Promise<void> {
    const promises: Promise<void>[] = [];

    for (const [, handle] of this.processes) {
      promises.push(
        this.killWithTimeout(handle.pid, 5000).catch(() => {
          // Ignore errors during cleanup
        })
      );
      
      handle.logStream?.end();
    }

    await Promise.all(promises);
    this.processes.clear();
  }

  /**
   * Check if a port is available
   */
  async isPortAvailable(port: number, host: string = '127.0.0.1'): Promise<boolean> {
    return new Promise((resolve) => {
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
  async findAvailablePort(
    startPort: number,
    endPort: number = startPort + 100,
    host: string = '127.0.0.1'
  ): Promise<number> {
    for (let port = startPort; port <= endPort; port++) {
      if (await this.isPortAvailable(port, host)) {
        return port;
      }
    }

    throw new ProcessError(
      `No available ports found between ${startPort} and ${endPort}`
    );
  }
}