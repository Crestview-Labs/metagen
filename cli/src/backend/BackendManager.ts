/**
 * Backend server lifecycle management
 */

import chalk from 'chalk';
import fetch from 'node-fetch';
import { EventEmitter } from 'events';
import which from 'which';
import path from 'path';
import { 
  Profile, 
  BackendOptions, 
  HealthStatus, 
  BackendError,
  ProcessInfo 
} from '../types/index.js';
import { 
  ensureProfileDirs, 
  getProjectRoot,
  fileExists,
  getAmbientHome 
} from '../utils/paths.js';
import { ProcessManager, ProcessHandle } from './ProcessManager.js';
import { ensureUv, checkUv } from '../utils/uv.js';

export class BackendManager extends EventEmitter {
  private profile: Profile;
  private processManager: ProcessManager;
  private processHandle?: ProcessHandle;
  private healthCheckInterval?: NodeJS.Timeout;
  private startupTimeout: number = 30000; // 30 seconds
  private healthCheckIntervalMs: number = 5000; // 5 seconds
  private isShuttingDown: boolean = false;

  constructor(profile: Profile) {
    super();
    this.profile = profile;
    this.processManager = new ProcessManager();

    // Forward process events
    this.processManager.on('error', (data) => this.emit('error', data));
    this.processManager.on('exit', (data) => this.handleProcessExit(data));
  }

  /**
   * Start the backend server
   */
  async start(options: Partial<BackendOptions> = {}): Promise<void> {
    // Check if already running
    const { pid, running } = await this.processManager.checkPidFile(this.profile.pidFile);
    
    if (running && pid) {
      console.log(chalk.yellow('⚠️  Backend already running with PID:'), pid);
      return;
    }

    // Ensure profile directories exist
    await ensureProfileDirs(this.profile);

    // Check for Python and uv, get paths
    const { uvPath, pythonPath } = await this.checkDependencies();

    // Find available port
    const port = options.port || this.profile.port;
    const availablePort = await this.findAvailablePort(port);
    
    if (availablePort !== port) {
      console.log(chalk.yellow(`⚠️  Port ${port} is busy, using ${availablePort}`));
    }

    // Start the backend
    console.log(chalk.blue('🚀 Starting backend server...'));
    console.log(chalk.gray(`   Profile: ${this.profile.name}`));
    console.log(chalk.gray(`   Port: ${availablePort}`));
    console.log(chalk.gray(`   Database: ${this.profile.dbPath}`));
    console.log(chalk.gray(`   Logs: ${this.profile.currentLogFile}`));
    console.log(chalk.gray(`   View logs: tail -f ${this.profile.currentLogFile}\n`));

    const projectRoot = getProjectRoot();
    const venvPath = path.join(getAmbientHome(), 'venv');
    const env = {
      ...process.env,
      PYTHONUNBUFFERED: '1',
      METAGEN_PORT: availablePort.toString(),
      METAGEN_DB_PATH: this.profile.dbPath,
      METAGEN_LOG_LEVEL: options.logLevel || this.profile.logLevel,
      METAGEN_PROFILE: this.profile.name,
      VIRTUAL_ENV: venvPath,
      PATH: `${path.join(venvPath, 'bin')}:${process.env.PATH}`,
      ...options.env
    };

    try {
      // Use the Python from our managed environment directly
      this.processHandle = await this.processManager.spawn(
        pythonPath,
        ['main.py', '--port', availablePort.toString()],
        {
          cwd: projectRoot,
          env,
          detached: options.detached || false,
          logFile: this.profile.currentLogFile
        }
      );

      // Write PID file
      await this.processManager.writePidFile(this.profile.pidFile, this.processHandle.pid);

      // Wait for backend to be healthy
      await this.waitForHealthy(availablePort);

      // Start health monitoring
      this.startHealthMonitoring(availablePort);

      console.log(chalk.green('✓ Backend started successfully'));
      this.emit('started', { pid: this.processHandle.pid, port: availablePort });

    } catch (error) {
      await this.cleanup();
      throw new BackendError(`Failed to start backend: ${error}`);
    }
  }

  /**
   * Stop the backend server
   */
  async stop(): Promise<void> {
    this.isShuttingDown = true;

    // Stop health monitoring
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = undefined;
    }

    // Check PID file
    const { pid, running } = await this.processManager.checkPidFile(this.profile.pidFile);

    if (!running || !pid) {
      console.log(chalk.gray('Backend not running'));
      return;
    }

    console.log(chalk.blue('🛑 Stopping backend...'));

    try {
      // Send graceful shutdown signal
      await this.processManager.killWithTimeout(pid, 10000);
      
      // Clean up PID file
      await this.processManager.removePidFile(this.profile.pidFile);

      console.log(chalk.green('✓ Backend stopped'));
      this.emit('stopped');

    } catch (error) {
      throw new BackendError(`Failed to stop backend: ${error}`);
    } finally {
      this.isShuttingDown = false;
    }
  }

  /**
   * Restart the backend server
   */
  async restart(options: Partial<BackendOptions> = {}): Promise<void> {
    console.log(chalk.blue('🔄 Restarting backend...'));
    await this.stop();
    await new Promise(resolve => setTimeout(resolve, 1000)); // Brief pause
    await this.start(options);
  }

  /**
   * Check if backend is running
   */
  async isRunning(): Promise<boolean> {
    const { running } = await this.processManager.checkPidFile(this.profile.pidFile);
    return running;
  }

  /**
   * Get backend health status
   */
  async getHealth(port?: number): Promise<HealthStatus> {
    const targetPort = port || this.profile.port;
    
    try {
      const response = await fetch(`http://localhost:${targetPort}/health`);

      if (response.ok) {
        const data = await response.json() as any;
        return {
          healthy: true,
          status: 'healthy',
          message: data.message || 'Backend is healthy',
          uptime: data.uptime,
          lastCheck: new Date()
        };
      }

      return {
        healthy: false,
        status: 'unhealthy',
        message: `Health check returned ${response.status}`,
        lastCheck: new Date()
      };

    } catch (error) {
      return {
        healthy: false,
        status: 'unknown',
        message: `Health check failed: ${error}`,
        lastCheck: new Date()
      };
    }
  }

  /**
   * Get process info
   */
  async getProcessInfo(): Promise<ProcessInfo | null> {
    const { pid, running } = await this.processManager.checkPidFile(this.profile.pidFile);
    
    if (!running || !pid) {
      return null;
    }

    const info = this.processManager.getProcessInfo(pid);
    
    return {
      pid,
      status: 'running',
      ...info
    };
  }

  /**
   * Wait for backend to be healthy
   */
  private async waitForHealthy(port: number): Promise<void> {
    const startTime = Date.now();
    
    console.log(chalk.gray('⏳ Waiting for backend to be ready...'));

    while (Date.now() - startTime < this.startupTimeout) {
      const health = await this.getHealth(port);
      
      if (health.healthy) {
        return;
      }

      await new Promise(resolve => setTimeout(resolve, 1000));
    }

    throw new BackendError('Backend failed to start within timeout');
  }

  /**
   * Start health monitoring
   */
  private startHealthMonitoring(port: number): void {
    this.healthCheckInterval = setInterval(async () => {
      if (this.isShuttingDown) return;

      const health = await this.getHealth(port);
      
      if (!health.healthy) {
        console.error(chalk.red('⚠️  Backend health check failed'));
        this.emit('unhealthy', health);
        
        // Attempt recovery
        await this.handleUnhealthy();
      }
    }, this.healthCheckIntervalMs);
  }

  /**
   * Handle unhealthy backend
   */
  private async handleUnhealthy(): Promise<void> {
    // Check if process is still running
    const { running } = await this.processManager.checkPidFile(this.profile.pidFile);
    
    if (!running && !this.isShuttingDown) {
      console.error(chalk.red('⚠️  Backend process died unexpectedly'));
      this.emit('crashed');
      
      // Could implement auto-restart here if desired
      // await this.start();
    }
  }

  /**
   * Handle process exit
   */
  private handleProcessExit(data: { pid: number; code: number | null; signal: string | null }): void {
    if (this.isShuttingDown) return;

    console.error(chalk.red(`⚠️  Backend exited unexpectedly (code: ${data.code}, signal: ${data.signal})`));
    this.emit('crashed', data);
    
    // Clean up
    this.cleanup().catch(console.error);
  }

  /**
   * Check required dependencies and return paths
   */
  private async checkDependencies(): Promise<{ uvPath: string; pythonPath: string }> {
    // Ensure uv is available (download if needed)
    const uvPath = await ensureUv();
    
    // Check for Python environment
    const venvPath = path.join(getAmbientHome(), 'venv');
    const pythonPath = path.join(venvPath, 'bin', 'python');
    
    if (!await fileExists(pythonPath)) {
      throw new BackendError(
        'Python environment not set up. Run "ambient setup" first.'
      );
    }

    // Check for main.py
    const mainPy = path.join(getProjectRoot(), 'main.py');
    if (!await fileExists(mainPy)) {
      throw new BackendError(`Backend entry point not found: ${mainPy}`);
    }
    
    return { uvPath, pythonPath };
  }

  /**
   * Find available port
   */
  private async findAvailablePort(preferredPort: number): Promise<number> {
    if (await this.processManager.isPortAvailable(preferredPort)) {
      return preferredPort;
    }

    return this.processManager.findAvailablePort(preferredPort, preferredPort + 100);
  }

  /**
   * Clean up resources
   */
  private async cleanup(): Promise<void> {
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = undefined;
    }

    if (this.processHandle) {
      this.processHandle.logStream?.end();
    }

    await this.processManager.removePidFile(this.profile.pidFile);
  }

  /**
   * Destroy the manager
   */
  async destroy(): Promise<void> {
    await this.stop();
    await this.processManager.cleanup();
    this.removeAllListeners();
  }
}