/**
 * Unit tests for path utilities
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import * as os from 'os';
import * as path from 'path';
import * as fs from 'fs-extra';
import {
  getAmbientHome,
  getProfilesDir,
  getProfileDir,
  getProfilePaths,
  calculatePort,
  ensureDir,
  ensureProfileDirs,
  getProjectRoot,
  fileExists,
  readPidFile,
  writePidFile,
  removePidFile,
  getFileSize,
  getLatestLogFile,
  cleanOldLogs
} from '../../../src/utils/paths';

describe('Path Utilities', () => {
  const TEST_DIR = path.join(os.tmpdir(), 'ambient-test', Date.now().toString());
  
  beforeEach(async () => {
    await fs.ensureDir(TEST_DIR);
    process.env.AMBIENT_CONFIG_DIR = TEST_DIR;
  });
  
  afterEach(async () => {
    await fs.remove(TEST_DIR);
    delete process.env.AMBIENT_CONFIG_DIR;
  });
  
  describe('getAmbientHome', () => {
    it('should use AMBIENT_CONFIG_DIR when set', () => {
      const home = getAmbientHome();
      expect(home).toBe(TEST_DIR);
    });
    
    it('should use ~/.ambient when env not set', () => {
      delete process.env.AMBIENT_CONFIG_DIR;
      const home = getAmbientHome();
      expect(home).toBe(path.join(os.homedir(), '.ambient'));
    });
  });
  
  describe('getProfilesDir', () => {
    it('should return profiles subdirectory', () => {
      const dir = getProfilesDir();
      expect(dir).toBe(path.join(TEST_DIR, 'profiles'));
    });
  });
  
  describe('getProfileDir', () => {
    it('should return profile-specific directory', () => {
      const dir = getProfileDir('test-profile');
      expect(dir).toBe(path.join(TEST_DIR, 'profiles', 'test-profile'));
    });
  });
  
  describe('getProfilePaths', () => {
    it('should return complete profile paths', () => {
      const profile = getProfilePaths('test');
      const today = new Date().toISOString().split('T')[0];
      
      expect(profile.name).toBe('test');
      expect(profile.baseDir).toBe(path.join(TEST_DIR, 'profiles', 'test'));
      expect(profile.configPath).toBe(path.join(TEST_DIR, 'profiles', 'test', 'config.yaml'));
      expect(profile.dbPath).toBe(path.join(TEST_DIR, 'profiles', 'test', 'data', 'metagen.db'));
      expect(profile.logsDir).toBe(path.join(TEST_DIR, 'profiles', 'test', 'logs'));
      expect(profile.pidFile).toBe(path.join(TEST_DIR, 'profiles', 'test', 'ambient.pid'));
      expect(profile.currentLogFile).toBe(path.join(TEST_DIR, 'profiles', 'test', 'logs', `backend-${today}.log`));
      expect(profile.port).toBeGreaterThanOrEqual(8080);
      expect(profile.port).toBeLessThan(9080);
      expect(profile.logLevel).toBe('INFO');
    });
  });
  
  describe('calculatePort', () => {
    it('should generate consistent port for same profile name', () => {
      const port1 = calculatePort('test-profile');
      const port2 = calculatePort('test-profile');
      expect(port1).toBe(port2);
    });
    
    it('should generate different ports for different profiles', () => {
      const port1 = calculatePort('profile1');
      const port2 = calculatePort('profile2');
      expect(port1).not.toBe(port2);
    });
    
    it('should generate port in valid range', () => {
      const port = calculatePort('test');
      expect(port).toBeGreaterThanOrEqual(8080);
      expect(port).toBeLessThan(9080);
    });
  });
  
  describe('ensureDir', () => {
    it('should create directory if it does not exist', async () => {
      const testPath = path.join(TEST_DIR, 'new-dir');
      await ensureDir(testPath);
      const exists = await fs.pathExists(testPath);
      expect(exists).toBe(true);
    });
    
    it('should not fail if directory already exists', async () => {
      const testPath = path.join(TEST_DIR, 'existing-dir');
      await fs.ensureDir(testPath);
      await ensureDir(testPath);
      const exists = await fs.pathExists(testPath);
      expect(exists).toBe(true);
    });
  });
  
  describe('ensureProfileDirs', () => {
    it('should create all profile directories', async () => {
      const profile = getProfilePaths('test');
      await ensureProfileDirs(profile);
      
      expect(await fs.pathExists(profile.baseDir)).toBe(true);
      expect(await fs.pathExists(path.dirname(profile.dbPath))).toBe(true);
      expect(await fs.pathExists(profile.logsDir)).toBe(true);
    });
  });
  
  describe('fileExists', () => {
    it('should return true for existing file', async () => {
      const testFile = path.join(TEST_DIR, 'test.txt');
      await fs.writeFile(testFile, 'test');
      const exists = await fileExists(testFile);
      expect(exists).toBe(true);
    });
    
    it('should return false for non-existing file', async () => {
      const testFile = path.join(TEST_DIR, 'nonexistent.txt');
      const exists = await fileExists(testFile);
      expect(exists).toBe(false);
    });
  });
  
  describe('PID file operations', () => {
    const pidFile = path.join(TEST_DIR, 'test.pid');
    
    it('should write and read PID file', async () => {
      await writePidFile(pidFile, 12345);
      const pid = await readPidFile(pidFile);
      expect(pid).toBe(12345);
    });
    
    it('should return null for non-existing PID file', async () => {
      const pid = await readPidFile(path.join(TEST_DIR, 'nonexistent.pid'));
      expect(pid).toBe(null);
    });
    
    it('should remove PID file', async () => {
      await writePidFile(pidFile, 12345);
      await removePidFile(pidFile);
      const exists = await fileExists(pidFile);
      expect(exists).toBe(false);
    });
    
    it('should not fail when removing non-existing PID file', async () => {
      await removePidFile(path.join(TEST_DIR, 'nonexistent.pid'));
      // Should not throw
    });
  });
  
  describe('getFileSize', () => {
    it('should return human-readable file size', async () => {
      const testFile = path.join(TEST_DIR, 'test.txt');
      await fs.writeFile(testFile, 'a'.repeat(1024));
      const size = await getFileSize(testFile);
      expect(size).toBe('1 KB');
    });
    
    it('should return 0 B for non-existing file', async () => {
      const size = await getFileSize(path.join(TEST_DIR, 'nonexistent.txt'));
      expect(size).toBe('0 B');
    });
  });
  
  describe('getLatestLogFile', () => {
    it('should return latest log file', async () => {
      const logsDir = path.join(TEST_DIR, 'logs');
      await fs.ensureDir(logsDir);
      
      await fs.writeFile(path.join(logsDir, 'backend-2024-01-01.log'), '');
      await fs.writeFile(path.join(logsDir, 'backend-2024-01-02.log'), '');
      await fs.writeFile(path.join(logsDir, 'backend-2024-01-03.log'), '');
      
      const latest = await getLatestLogFile(logsDir);
      expect(latest).toBe('backend-2024-01-03.log');
    });
    
    it('should return null for empty directory', async () => {
      const logsDir = path.join(TEST_DIR, 'empty-logs');
      await fs.ensureDir(logsDir);
      const latest = await getLatestLogFile(logsDir);
      expect(latest).toBe(null);
    });
    
    it('should return null for non-existing directory', async () => {
      const latest = await getLatestLogFile(path.join(TEST_DIR, 'nonexistent'));
      expect(latest).toBe(null);
    });
  });
  
  describe('cleanOldLogs', () => {
    it('should remove logs older than specified days', async () => {
      const logsDir = path.join(TEST_DIR, 'logs');
      await fs.ensureDir(logsDir);
      
      const oldFile = path.join(logsDir, 'old.log');
      const newFile = path.join(logsDir, 'new.log');
      
      await fs.writeFile(oldFile, '');
      await fs.writeFile(newFile, '');
      
      // Set old file time to 40 days ago
      const oldTime = Date.now() - (40 * 24 * 60 * 60 * 1000);
      await fs.utimes(oldFile, oldTime / 1000, oldTime / 1000);
      
      await cleanOldLogs(logsDir, 30);
      
      expect(await fileExists(oldFile)).toBe(false);
      expect(await fileExists(newFile)).toBe(true);
    });
    
    it('should not fail for non-existing directory', async () => {
      await cleanOldLogs(path.join(TEST_DIR, 'nonexistent'), 30);
      // Should not throw
    });
  });
});