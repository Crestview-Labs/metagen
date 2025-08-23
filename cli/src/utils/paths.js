/**
 * Path utilities for Ambient CLI
 */
import path from 'path';
import os from 'os';
import fs from 'fs-extra';
import { fileURLToPath } from 'url';
/**
 * Get the home directory for Ambient configuration
 */
export function getAmbientHome() {
    return process.env.AMBIENT_CONFIG_DIR || path.join(os.homedir(), '.ambient');
}
/**
 * Get the profiles directory
 */
export function getProfilesDir() {
    return path.join(getAmbientHome(), 'profiles');
}
/**
 * Get profile directory path
 */
export function getProfileDir(profileName) {
    return path.join(getProfilesDir(), profileName);
}
/**
 * Calculate profile paths
 */
export function getProfilePaths(profileName) {
    const baseDir = getProfileDir(profileName);
    const today = new Date().toISOString().split('T')[0];
    return {
        name: profileName,
        baseDir,
        configPath: path.join(baseDir, 'config.yaml'),
        dbPath: path.join(baseDir, 'data', 'metagen.db'),
        logsDir: path.join(baseDir, 'logs'),
        pidFile: path.join(baseDir, 'ambient.pid'),
        port: calculatePort(profileName),
        logLevel: 'INFO',
        currentLogFile: path.join(baseDir, 'logs', `backend-${today}.log`)
    };
}
/**
 * Calculate deterministic port for profile
 */
export function calculatePort(profileName) {
    // Use a simple hash function to generate consistent port
    let hash = 0;
    for (let i = 0; i < profileName.length; i++) {
        const char = profileName.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash = hash & hash; // Convert to 32bit integer
    }
    // Return port in range 8080-9080
    return 8080 + (Math.abs(hash) % 1000);
}
/**
 * Ensure directory exists
 */
export async function ensureDir(dirPath) {
    await fs.ensureDir(dirPath);
}
/**
 * Ensure all profile directories exist
 */
export async function ensureProfileDirs(profile) {
    await ensureDir(profile.baseDir);
    await ensureDir(path.dirname(profile.dbPath));
    await ensureDir(profile.logsDir);
}
/**
 * Get project root directory (where main.py is located)
 */
export function getProjectRoot() {
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
export async function fileExists(filePath) {
    try {
        await fs.access(filePath);
        return true;
    }
    catch {
        return false;
    }
}
/**
 * Read PID file
 */
export async function readPidFile(pidFile) {
    try {
        const content = await fs.readFile(pidFile, 'utf-8');
        const pid = parseInt(content.trim(), 10);
        return isNaN(pid) ? null : pid;
    }
    catch {
        return null;
    }
}
/**
 * Write PID file
 */
export async function writePidFile(pidFile, pid) {
    await fs.writeFile(pidFile, pid.toString());
}
/**
 * Remove PID file
 */
export async function removePidFile(pidFile) {
    try {
        await fs.unlink(pidFile);
    }
    catch {
        // Ignore if file doesn't exist
    }
}
/**
 * Get file size in human readable format
 */
export async function getFileSize(filePath) {
    try {
        const stats = await fs.stat(filePath);
        const bytes = stats.size;
        if (bytes === 0)
            return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return `${parseFloat((bytes / Math.pow(k, i)).toFixed(2))} ${sizes[i]}`;
    }
    catch {
        return '0 B';
    }
}
/**
 * Get latest log file for a profile
 */
export async function getLatestLogFile(logsDir) {
    try {
        const files = await fs.readdir(logsDir);
        const logFiles = files
            .filter((f) => f.startsWith('backend-') && f.endsWith('.log'))
            .sort()
            .reverse();
        return logFiles[0] || null;
    }
    catch {
        return null;
    }
}
/**
 * Clean old log files
 */
export async function cleanOldLogs(logsDir, maxAgeDays = 30) {
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
    }
    catch {
        // Ignore errors during cleanup
    }
}
