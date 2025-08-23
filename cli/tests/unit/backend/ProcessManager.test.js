/**
 * Unit tests for ProcessManager
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as path from 'path';
import * as os from 'os';
import * as fs from 'fs-extra';
import { ProcessManager } from '../../../src/backend/ProcessManager';
describe('ProcessManager', () => {
    let manager;
    const TEST_DIR = path.join(os.tmpdir(), 'process-test', Date.now().toString());
    beforeEach(async () => {
        await fs.ensureDir(TEST_DIR);
        manager = new ProcessManager();
    });
    afterEach(async () => {
        await manager.cleanup();
        await fs.remove(TEST_DIR);
    });
    describe('spawn', () => {
        it('should spawn a simple process', async () => {
            const handle = await manager.spawn('echo', ['hello'], {
                cwd: TEST_DIR
            });
            expect(handle).toBeDefined();
            expect(handle.pid).toBeGreaterThan(0);
            expect(handle.process).toBeDefined();
            // Wait for process to exit
            await new Promise(resolve => setTimeout(resolve, 100));
        });
        it('should write output to log file', async () => {
            const logFile = path.join(TEST_DIR, 'test.log');
            const handle = await manager.spawn('echo', ['test output'], {
                logFile
            });
            // Wait for process to complete and write to file
            await new Promise(resolve => setTimeout(resolve, 100));
            const logContent = await fs.readFile(logFile, 'utf-8');
            expect(logContent).toContain('test output');
        });
        it('should throw error for invalid command', async () => {
            await expect(manager.spawn('nonexistent-command-xyz', [])).rejects.toThrow('Failed to spawn process');
        });
    });
    describe('isRunning', () => {
        it('should return true for running process', () => {
            const isRunning = manager.isRunning(process.pid);
            expect(isRunning).toBe(true);
        });
        it('should return false for non-existing process', () => {
            const isRunning = manager.isRunning(99999999);
            expect(isRunning).toBe(false);
        });
    });
    describe('kill', () => {
        it('should kill a running process', async () => {
            const handle = await manager.spawn('sleep', ['10']);
            await manager.kill(handle.pid);
            // Wait a bit for process to die
            await new Promise(resolve => setTimeout(resolve, 100));
            const isRunning = manager.isRunning(handle.pid);
            expect(isRunning).toBe(false);
        });
        it('should not throw for non-existing process', async () => {
            await manager.kill(99999999);
            // Should not throw
        });
    });
    describe('killWithTimeout', () => {
        it('should kill process within timeout', async () => {
            const handle = await manager.spawn('sleep', ['10']);
            await manager.killWithTimeout(handle.pid, 1000);
            const isRunning = manager.isRunning(handle.pid);
            expect(isRunning).toBe(false);
        });
    });
    describe('PID file operations', () => {
        const pidFile = path.join(TEST_DIR, 'test.pid');
        it('should check PID file and detect running process', async () => {
            await manager.writePidFile(pidFile, process.pid);
            const result = await manager.checkPidFile(pidFile);
            expect(result.pid).toBe(process.pid);
            expect(result.running).toBe(true);
        });
        it('should clean up stale PID file', async () => {
            await manager.writePidFile(pidFile, 99999999);
            const result = await manager.checkPidFile(pidFile);
            expect(result.pid).toBe(99999999);
            expect(result.running).toBe(false);
            // Should have removed the stale file
            const exists = await fs.pathExists(pidFile);
            expect(exists).toBe(false);
        });
        it('should handle missing PID file', async () => {
            const result = await manager.checkPidFile(path.join(TEST_DIR, 'nonexistent.pid'));
            expect(result.pid).toBe(null);
            expect(result.running).toBe(false);
        });
    });
    describe('isPortAvailable', () => {
        it('should detect available port', async () => {
            const isAvailable = await manager.isPortAvailable(19999);
            expect(isAvailable).toBe(true);
        });
        it('should detect busy port', async () => {
            // Start a server on a port
            const net = await import('net');
            const server = net.createServer();
            await new Promise((resolve) => {
                server.listen(19998, '127.0.0.1', () => resolve());
            });
            const isAvailable = await manager.isPortAvailable(19998);
            expect(isAvailable).toBe(false);
            // Clean up
            await new Promise((resolve) => {
                server.close(() => resolve());
            });
        });
    });
    describe('findAvailablePort', () => {
        it('should find an available port in range', async () => {
            const port = await manager.findAvailablePort(19000, 19100);
            expect(port).toBeGreaterThanOrEqual(19000);
            expect(port).toBeLessThanOrEqual(19100);
            // Verify it's actually available
            const isAvailable = await manager.isPortAvailable(port);
            expect(isAvailable).toBe(true);
        });
        it('should throw when no ports available', async () => {
            // Create servers on all ports in range
            const net = await import('net');
            const servers = [];
            for (let i = 19995; i <= 19997; i++) {
                const server = net.createServer();
                await new Promise((resolve) => {
                    server.listen(i, '127.0.0.1', () => resolve());
                });
                servers.push(server);
            }
            // Try to find port in occupied range
            await expect(manager.findAvailablePort(19995, 19997)).rejects.toThrow('No available ports found');
            // Clean up
            for (const server of servers) {
                await new Promise((resolve) => {
                    server.close(() => resolve());
                });
            }
        });
    });
    describe('cleanup', () => {
        it('should clean up all tracked processes', async () => {
            const handle1 = await manager.spawn('sleep', ['10']);
            const handle2 = await manager.spawn('sleep', ['10']);
            await manager.cleanup();
            // Processes should be killed
            expect(manager.isRunning(handle1.pid)).toBe(false);
            expect(manager.isRunning(handle2.pid)).toBe(false);
        });
    });
});
