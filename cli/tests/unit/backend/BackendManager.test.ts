import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { EventEmitter } from 'events';
import { BackendManager } from '../../../src/backend/BackendManager';
import { ProcessManager } from '../../../src/backend/ProcessManager';
import * as paths from '../../../src/utils/paths';
import { Profile } from '../../../src/types';
import fetch from 'node-fetch';
import which from 'which';

// Mock dependencies
vi.mock('node-fetch');
vi.mock('which');
vi.mock('../../../src/backend/ProcessManager');
vi.mock('../../../src/utils/paths');

describe('BackendManager', () => {
  let manager: BackendManager;
  let mockProfile: Profile;
  let mockProcessManager: any;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.useFakeTimers();

    mockProfile = {
      name: 'test',
      port: 8080,
      dir: '/test/.ambient/profiles/test',
      dbPath: '/test/.ambient/profiles/test/metagen.db',
      logsDir: '/test/.ambient/profiles/test/logs',
      currentLogFile: '/test/.ambient/profiles/test/logs/metagen.log',
      pidFile: '/test/.ambient/profiles/test/backend.pid',
      config: '/test/.ambient/profiles/test/config.yaml',
      logLevel: 'info'
    };

    // Create mock ProcessManager instance
    mockProcessManager = {
      on: vi.fn(),
      checkPidFile: vi.fn(),
      spawn: vi.fn(),
      writePidFile: vi.fn(),
      removePidFile: vi.fn(),
      killWithTimeout: vi.fn(),
      isPortAvailable: vi.fn(),
      findAvailablePort: vi.fn(),
      getProcessInfo: vi.fn(),
      cleanup: vi.fn()
    };

    // Mock ProcessManager constructor
    vi.mocked(ProcessManager).mockImplementation(() => mockProcessManager);

    // Mock path utilities
    vi.mocked(paths.ensureProfileDirs).mockResolvedValue(undefined);
    vi.mocked(paths.getProjectRoot).mockReturnValue('/test/project');
    vi.mocked(paths.fileExists).mockResolvedValue(true);

    // Mock which
    vi.mocked(which).mockResolvedValue('/usr/bin/command');

    manager = new BackendManager(mockProfile);
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
  });

  describe('start', () => {
    beforeEach(() => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });
      mockProcessManager.isPortAvailable.mockResolvedValue(true);
      mockProcessManager.spawn.mockResolvedValue({
        pid: 12345,
        logStream: { end: vi.fn() }
      });
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({ message: 'healthy', uptime: 100 })
      } as any);
    });

    it('should start the backend successfully', async () => {
      await manager.start();

      expect(mockProcessManager.checkPidFile).toHaveBeenCalledWith(mockProfile.pidFile);
      expect(paths.ensureProfileDirs).toHaveBeenCalledWith(mockProfile);
      expect(mockProcessManager.spawn).toHaveBeenCalledWith(
        'uv',
        ['run', 'python', 'main.py', '--port', '8080'],
        expect.objectContaining({
          cwd: '/test/project',
          logFile: mockProfile.currentLogFile
        })
      );
      expect(mockProcessManager.writePidFile).toHaveBeenCalledWith(mockProfile.pidFile, 12345);
    });

    it('should not start if already running', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: 12345, running: true });
      const consoleSpy = vi.spyOn(console, 'log');

      await manager.start();

      expect(mockProcessManager.spawn).not.toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Backend already running'),
        12345
      );
    });

    it('should use alternative port if preferred is busy', async () => {
      mockProcessManager.isPortAvailable.mockResolvedValueOnce(false);
      mockProcessManager.findAvailablePort.mockResolvedValue(8081);

      await manager.start();

      expect(mockProcessManager.spawn).toHaveBeenCalledWith(
        'uv',
        ['run', 'python', 'main.py', '--port', '8081'],
        expect.anything()
      );
    });

    it('should wait for backend to be healthy with timeout', async () => {
      let healthCheckCount = 0;
      vi.mocked(fetch).mockImplementation(async () => {
        healthCheckCount++;
        if (healthCheckCount < 3) {
          throw new Error('Connection refused');
        }
        return {
          ok: true,
          json: async () => ({ message: 'healthy' })
        } as any;
      });

      const startPromise = manager.start();
      
      // Advance timers to simulate health check retries
      for (let i = 0; i < 3; i++) {
        await vi.advanceTimersByTimeAsync(1000);
      }

      await startPromise;
      expect(healthCheckCount).toBe(3);
    });

    it('should throw error if backend fails to start within timeout', async () => {
      vi.mocked(fetch).mockRejectedValue(new Error('Connection refused'));

      const startPromise = manager.start();
      
      // Advance past the timeout (30 seconds)
      await vi.advanceTimersByTimeAsync(31000);

      await expect(startPromise).rejects.toThrow('Backend failed to start within timeout');
    });

    it('should clean up on startup failure', async () => {
      mockProcessManager.spawn.mockRejectedValue(new Error('Spawn failed'));

      await expect(manager.start()).rejects.toThrow('Failed to start backend');
      
      expect(mockProcessManager.removePidFile).toHaveBeenCalledWith(mockProfile.pidFile);
    });

    it('should emit started event on success', async () => {
      const startedHandler = vi.fn();
      manager.on('started', startedHandler);

      await manager.start();

      expect(startedHandler).toHaveBeenCalledWith({
        pid: 12345,
        port: 8080
      });
    });
  });

  describe('stop', () => {
    it('should stop running backend', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: 12345, running: true });
      mockProcessManager.killWithTimeout.mockResolvedValue(undefined);

      await manager.stop();

      expect(mockProcessManager.killWithTimeout).toHaveBeenCalledWith(12345, 10000);
      expect(mockProcessManager.removePidFile).toHaveBeenCalledWith(mockProfile.pidFile);
    });

    it('should do nothing if backend not running', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });
      const consoleSpy = vi.spyOn(console, 'log');

      await manager.stop();

      expect(mockProcessManager.killWithTimeout).not.toHaveBeenCalled();
      expect(consoleSpy).toHaveBeenCalledWith(expect.stringContaining('Backend not running'));
    });

    it('should emit stopped event', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: 12345, running: true });
      const stoppedHandler = vi.fn();
      manager.on('stopped', stoppedHandler);

      await manager.stop();

      expect(stoppedHandler).toHaveBeenCalled();
    });

    it('should stop health monitoring', async () => {
      // Start the manager first to initiate health monitoring
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });
      mockProcessManager.isPortAvailable.mockResolvedValue(true);
      mockProcessManager.spawn.mockResolvedValue({
        pid: 12345,
        logStream: { end: vi.fn() }
      });
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({ message: 'healthy' })
      } as any);

      await manager.start();
      
      // Now stop
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: 12345, running: true });
      await manager.stop();

      // Advance timers to check health monitoring doesn't run
      const fetchCallsBefore = vi.mocked(fetch).mock.calls.length;
      await vi.advanceTimersByTimeAsync(10000);
      const fetchCallsAfter = vi.mocked(fetch).mock.calls.length;
      
      expect(fetchCallsAfter).toBe(fetchCallsBefore);
    });
  });

  describe('restart', () => {
    it('should stop and then start backend', async () => {
      mockProcessManager.checkPidFile
        .mockResolvedValueOnce({ pid: 12345, running: true }) // For stop
        .mockResolvedValueOnce({ pid: null, running: false }); // For start
      mockProcessManager.isPortAvailable.mockResolvedValue(true);
      mockProcessManager.spawn.mockResolvedValue({
        pid: 12346,
        logStream: { end: vi.fn() }
      });
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({ message: 'healthy' })
      } as any);

      const restartPromise = manager.restart();
      
      // Advance timer past the 1 second pause in restart
      await vi.advanceTimersByTimeAsync(1000);
      
      await restartPromise;

      expect(mockProcessManager.killWithTimeout).toHaveBeenCalled();
      expect(mockProcessManager.spawn).toHaveBeenCalled();
    });
  });

  describe('isRunning', () => {
    it('should return true when backend is running', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: 12345, running: true });

      const result = await manager.isRunning();

      expect(result).toBe(true);
    });

    it('should return false when backend is not running', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });

      const result = await manager.isRunning();

      expect(result).toBe(false);
    });
  });

  describe('getHealth', () => {
    it('should return healthy status when backend responds', async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({ message: 'Backend running', uptime: 3600 })
      } as any);

      const health = await manager.getHealth();

      expect(health.healthy).toBe(true);
      expect(health.status).toBe('healthy');
      expect(health.uptime).toBe(3600);
    });

    it('should return unhealthy status for non-OK response', async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: false,
        status: 500
      } as any);

      const health = await manager.getHealth();

      expect(health.healthy).toBe(false);
      expect(health.status).toBe('unhealthy');
      expect(health.message).toContain('500');
    });

    it('should return unknown status on fetch error', async () => {
      vi.mocked(fetch).mockRejectedValue(new Error('Connection refused'));

      const health = await manager.getHealth();

      expect(health.healthy).toBe(false);
      expect(health.status).toBe('unknown');
      expect(health.message).toContain('Connection refused');
    });

    it('should use custom port if provided', async () => {
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({})
      } as any);

      await manager.getHealth(9090);

      expect(fetch).toHaveBeenCalledWith('http://localhost:9090/health');
    });
  });

  describe('getProcessInfo', () => {
    it('should return process info when running', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: 12345, running: true });
      mockProcessManager.getProcessInfo.mockReturnValue({
        cpuUsage: '10%',
        memoryUsage: '100MB'
      });

      const info = await manager.getProcessInfo();

      expect(info).toEqual({
        pid: 12345,
        status: 'running',
        cpuUsage: '10%',
        memoryUsage: '100MB'
      });
    });

    it('should return null when not running', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });

      const info = await manager.getProcessInfo();

      expect(info).toBeNull();
    });
  });

  describe('health monitoring', () => {
    beforeEach(async () => {
      // Start the backend to initiate health monitoring
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });
      mockProcessManager.isPortAvailable.mockResolvedValue(true);
      mockProcessManager.spawn.mockResolvedValue({
        pid: 12345,
        logStream: { end: vi.fn() }
      });
      vi.mocked(fetch).mockResolvedValue({
        ok: true,
        json: async () => ({ message: 'healthy' })
      } as any);

      await manager.start();
    });

    it('should emit unhealthy event when health check fails', async () => {
      const unhealthyHandler = vi.fn();
      manager.on('unhealthy', unhealthyHandler);

      // Make health check fail
      vi.mocked(fetch).mockRejectedValue(new Error('Connection refused'));

      // Advance timer to trigger health check
      await vi.advanceTimersByTimeAsync(5000);

      expect(unhealthyHandler).toHaveBeenCalledWith(
        expect.objectContaining({
          healthy: false,
          status: 'unknown'
        })
      );
    });

    it('should emit crashed event when process dies', async () => {
      const crashedHandler = vi.fn();
      manager.on('crashed', crashedHandler);

      // Make health check fail
      vi.mocked(fetch).mockRejectedValue(new Error('Connection refused'));
      // Process is not running
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });

      // Advance timer to trigger health check
      await vi.advanceTimersByTimeAsync(5000);

      expect(crashedHandler).toHaveBeenCalled();
    });
  });

  describe('dependency checking', () => {
    it('should throw error if uv is not found', async () => {
      vi.mocked(which).mockRejectedValueOnce(new Error('not found'));
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });

      await expect(manager.start()).rejects.toThrow('uv is required but not found');
    });

    it('should throw error if python3 is not found', async () => {
      vi.mocked(which)
        .mockResolvedValueOnce('/usr/bin/uv') // uv found
        .mockRejectedValueOnce(new Error('not found')); // python3 not found
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });

      await expect(manager.start()).rejects.toThrow('Python 3 is required but not found');
    });

    it('should throw error if main.py does not exist', async () => {
      vi.mocked(paths.fileExists).mockResolvedValue(false);
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: null, running: false });

      await expect(manager.start()).rejects.toThrow('Backend entry point not found');
    });
  });

  describe('destroy', () => {
    it('should stop backend and clean up resources', async () => {
      mockProcessManager.checkPidFile.mockResolvedValue({ pid: 12345, running: true });

      await manager.destroy();

      expect(mockProcessManager.killWithTimeout).toHaveBeenCalled();
      expect(mockProcessManager.cleanup).toHaveBeenCalled();
    });
  });
});