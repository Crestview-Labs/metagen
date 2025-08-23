/**
 * Path utilities for Ambient CLI
 */
import { Profile } from '../types/index.js';
/**
 * Get the home directory for Ambient configuration
 */
export declare function getAmbientHome(): string;
/**
 * Get the profiles directory
 */
export declare function getProfilesDir(): string;
/**
 * Get profile directory path
 */
export declare function getProfileDir(profileName: string): string;
/**
 * Calculate profile paths
 */
export declare function getProfilePaths(profileName: string): Profile;
/**
 * Calculate deterministic port for profile
 */
export declare function calculatePort(profileName: string): number;
/**
 * Ensure directory exists
 */
export declare function ensureDir(dirPath: string): Promise<void>;
/**
 * Ensure all profile directories exist
 */
export declare function ensureProfileDirs(profile: Profile): Promise<void>;
/**
 * Get project root directory (where main.py is located)
 */
export declare function getProjectRoot(): string;
/**
 * Check if file exists
 */
export declare function fileExists(filePath: string): Promise<boolean>;
/**
 * Read PID file
 */
export declare function readPidFile(pidFile: string): Promise<number | null>;
/**
 * Write PID file
 */
export declare function writePidFile(pidFile: string, pid: number): Promise<void>;
/**
 * Remove PID file
 */
export declare function removePidFile(pidFile: string): Promise<void>;
/**
 * Get file size in human readable format
 */
export declare function getFileSize(filePath: string): Promise<string>;
/**
 * Get latest log file for a profile
 */
export declare function getLatestLogFile(logsDir: string): Promise<string | null>;
/**
 * Clean old log files
 */
export declare function cleanOldLogs(logsDir: string, maxAgeDays?: number): Promise<void>;
