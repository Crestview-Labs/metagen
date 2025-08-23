/**
 * Setup command - Initialize Ambient environment
 */
import { Command } from 'commander';
export declare const setupCommand: Command;
export declare function checkSetup(): Promise<boolean>;
export declare function promptSetup(): Promise<void>;
