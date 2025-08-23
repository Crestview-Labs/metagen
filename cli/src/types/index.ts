/**
 * Core type definitions for Ambient CLI
 */

export interface Profile {
  name: string;
  baseDir: string;
  configPath: string;
  dbPath: string;
  logsDir: string;
  pidFile: string;
  port: number;
  logLevel: string;
  currentLogFile: string;
}

export interface ProfileStatus {
  name: string;
  port: number;
  status: 'running' | 'stopped' | 'error';
  pid: number | null;
  dbSize: string;
  logFile: string;
  started?: Date;
}

export interface BackendOptions {
  profile: Profile;
  port?: number;
  logLevel?: LogLevel;
  detached?: boolean;
  env?: Record<string, string>;
}

export type LogLevel = 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR' | 'CRITICAL';

export interface HealthStatus {
  healthy: boolean;
  status: 'healthy' | 'unhealthy' | 'starting' | 'stopping' | 'unknown';
  message?: string;
  uptime?: number;
  lastCheck?: Date;
}

export interface ProcessInfo {
  pid: number;
  status: 'running' | 'stopped';
  startTime?: Date;
  cpu?: number;
  memory?: number;
}

export interface LogEntry {
  timestamp: Date;
  level: LogLevel;
  message: string;
  component?: string;
  metadata?: Record<string, any>;
}

export interface SearchOptions {
  pattern?: string;
  level?: LogLevel;
  component?: string;
  startTime?: Date;
  endTime?: Date;
  limit?: number;
}

export interface BackendConfig {
  port: number;
  host: string;
  logLevel: LogLevel;
  dbPath: string;
  workers?: number;
  timeout?: number;
}

export interface CLIConfig {
  theme: 'dark' | 'light';
  editor?: string;
  shortcuts?: boolean;
}

export interface ToolsConfig {
  autoApprove: string[];
  requireApproval: boolean;
  timeout?: number;
}

export interface ProfileConfig {
  profile: string;
  backend: BackendConfig;
  cli?: CLIConfig;
  tools?: ToolsConfig;
  logging?: {
    maxFileSize: string;
    maxFiles: number;
    compress: boolean;
  };
}

export interface CommandOptions {
  profile?: string;
  verbose?: boolean;
  config?: string;
  json?: boolean;
}

export interface ServerCommandOptions extends CommandOptions {
  port?: number;
  host?: string;
  detached?: boolean;
  logLevel?: LogLevel;
}

export interface LogsCommandOptions extends CommandOptions {
  follow?: boolean;
  tail?: number;
  level?: LogLevel;
  search?: string;
  since?: string;
}

export class AmbientError extends Error {
  constructor(
    message: string,
    public code: string,
    public details?: any
  ) {
    super(message);
    this.name = 'AmbientError';
  }
}

export class BackendError extends AmbientError {
  constructor(message: string, details?: any) {
    super(message, 'BACKEND_ERROR', details);
    this.name = 'BackendError';
  }
}

export class ProfileError extends AmbientError {
  constructor(message: string, details?: any) {
    super(message, 'PROFILE_ERROR', details);
    this.name = 'ProfileError';
  }
}

export class ProcessError extends AmbientError {
  constructor(message: string, details?: any) {
    super(message, 'PROCESS_ERROR', details);
    this.name = 'ProcessError';
  }
}