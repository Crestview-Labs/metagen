/**
 * Path utilities for Ambient CLI
 */

import path from 'path';
import os from 'os';
import fs from 'fs-extra';
import { fileURLToPath } from 'url';
import { Profile } from '../types/index.js';

/**
 * Get the home directory for Ambient configuration
 */
export function getAmbientHome(): string {
  return process.env.AMBIENT_CONFIG_DIR || path.join(os.homedir(), '.ambient');
}

/**
 * Get the profiles directory
 */
export function getProfilesDir(): string {
  return path.join(getAmbientHome(), 'profiles');
}

/**
 * Get profile directory path
 */
export function getProfileDir(profileName: string): string {
  return path.join(getProfilesDir(), profileName);
}

/**
 * Calculate profile paths
 */
export function getProfilePaths(profileName: string): Profile {
  const baseDir = getProfileDir(profileName);
  const today = new Date().toISOString().split('T')[0];
  
  // Always use BACKEND_PORT from environment, default to 8080
  const port = parseInt(process.env.BACKEND_PORT || '8080', 10);
  
  return {
    name: profileName,
    baseDir,
    configPath: path.join(baseDir, 'config.yaml'),
    dbPath: path.join(baseDir, 'data', 'metagen.db'),
    logsDir: path.join(baseDir, 'logs'),
    pidFile: path.join(baseDir, 'ambient.pid'),
    port,
    logLevel: 'INFO',
    currentLogFile: path.join(baseDir, 'logs', `backend-${today}.log`)
  };
}


/**
 * Ensure directory exists
 */
export async function ensureDir(dirPath: string): Promise<void> {
  await fs.ensureDir(dirPath);
}

/**
 * Ensure all profile directories exist
 */
export async function ensureProfileDirs(profile: Profile): Promise<void> {
  await ensureDir(profile.baseDir);
  await ensureDir(path.dirname(profile.dbPath));
  await ensureDir(profile.logsDir);
}

/**
 * Get project root directory (where main.py is located)
 */
export function getProjectRoot(): string {
  // In production, the CLI will be installed globally or in node_modules
  // During development, we're in cli/src/utils/
  
  if (process.env.METAGEN_PROJECT_ROOT) {
    return process.env.METAGEN_PROJECT_ROOT;
  }
  
  // Get __dirname equivalent for ES modules
  const __filename = fileURLToPath(import.meta.url);
  const __dirname = path.dirname(__filename);
  
  // Try to find project root by looking for main.py
  let currentDir = __dirname;
  
  // Handle both compiled (dist) and source (src) locations
  if (currentDir.includes('/dist/')) {
    currentDir = currentDir.replace('/dist/', '/src/');
  }
  
  // Go up from cli/src/utils or cli/dist/utils
  for (let i = 0; i < 5; i++) {
    currentDir = path.dirname(currentDir);
    const mainPy = path.join(currentDir, 'main.py');
    
    if (fs.existsSync(mainPy)) {
      return currentDir;
    }
  }
  
  // Fallback: Go up from dist/cli/src/utils to project root
  return path.resolve(__dirname, '..', '..', '..', '..', '..');
}

/**
 * Check if file exists
 */
export async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

/**
 * Read PID file
 */
export async function readPidFile(pidFile: string): Promise<number | null> {
  try {
    const content = await fs.readFile(pidFile, 'utf-8');
    const pid = parseInt(content.trim(), 10);
    return isNaN(pid) ? null : pid;
  } catch {
    return null;
  }
}

/**
 * Write PID file
 */
export async function writePidFile(pidFile: string, pid: number): Promise<void> {
  await fs.writeFile(pidFile, pid.toString());
}

/**
 * Remove PID file
 */
export async function removePidFile(pidFile: string): Promise<void> {
  try {
    await fs.unlink(pidFile);
  } catch {
    // Ignore if file doesn't exist
  }
}

/**
 * Get file size in human readable format
 */
export async function getFileSize(filePath: string): Promise<string> {
  try {
    const stats = await fs.stat(filePath);
    const bytes = stats.size;
    
    if (bytes === 0) return '0 B';
    
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    
    return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
  } catch {
    return '0 B';
  }
}

/**
 * Get latest log file for a profile
 */
export async function getLatestLogFile(logsDir: string): Promise<string | null> {
  try {
    const files = await fs.readdir(logsDir);
    const logFiles = files
      .filter((f: string) => f.startsWith('backend-') && f.endsWith('.log'))
      .sort()
      .reverse();
    
    return logFiles[0] || null;
  } catch {
    return null;
  }
}

/**
 * Clean old log files
 */
export async function cleanOldLogs(logsDir: string, maxAgeDays: number = 30): Promise<void> {
  const cutoff = Date.now() - (maxAgeDays * 24 * 60 * 60 * 1000);
  
  try {
    const files = await fs.readdir(logsDir);
    
    for (const file of files) {
      const filePath = path.join(logsDir, file);
      const stats = await fs.stat(filePath);
      
      if (stats.mtime.getTime() < cutoff) {
        await fs.unlink(filePath);
      }
    }
  } catch {
    // Ignore errors during cleanup
  }
}