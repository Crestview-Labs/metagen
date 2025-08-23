#!/usr/bin/env node
/**
 * Ambient CLI - Main entry point
 */
import { Command } from 'commander';
import chalk from 'chalk';
import { serverCommand } from './commands/server.js';
import { setupCommand } from './commands/setup.js';
import { readFileSync } from 'fs';
import { fileURLToPath } from 'url';
import { dirname, join } from 'path';
// Get package.json for version
const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);
// Navigate up from dist/cli/src to find package.json
const packageJson = JSON.parse(readFileSync(join(__dirname, '..', '..', '..', 'package.json'), 'utf-8'));
// Create main program
const program = new Command();
program
    .name('ambient')
    .description('Ambient CLI - Unified interface for Metagen')
    .version(packageJson.version)
    .option('-p, --profile <name>', 'Use specified profile', 'default')
    .option('-v, --verbose', 'Verbose output')
    .option('-c, --config <path>', 'Use custom config file');
// Add commands
program.addCommand(setupCommand);
program.addCommand(serverCommand);
// Import chat command
import { chatCommand } from './commands/chat.js';
// Default command - launches interactive chat
program
    .command('cli', { isDefault: true })
    .description('Start interactive chat (default)')
    .option('-p, --profile <name>', 'Use specified profile', 'default')
    .option('-m, --message <text>', 'Send a single message')
    .option('--auto-approve', 'Auto-approve all tool calls')
    .option('--no-auto-start', 'Do not auto-start backend if not running')
    .action(async (options) => {
    await chatCommand(options);
});
// Add profiles command placeholder
program
    .command('profiles')
    .description('Manage profiles')
    .action(() => {
    console.log(chalk.yellow('⚠️  Profile management not yet implemented'));
});
// Add logs command placeholder  
program
    .command('logs')
    .description('View and manage logs')
    .action(() => {
    console.log(chalk.yellow('⚠️  Log viewing not yet implemented'));
});
// Add status command
program
    .command('status')
    .description('Check overall system status')
    .option('-p, --profile <name>', 'Profile to check', 'default')
    .action(async (options) => {
    const { getProfilePaths } = await import('./utils/paths.js');
    const { BackendManager } = await import('./backend/BackendManager.js');
    const profile = getProfilePaths(options.profile);
    const manager = new BackendManager(profile);
    console.log(chalk.blue.bold('🔍 System Status'));
    console.log(chalk.gray(`Profile: ${options.profile}\n`));
    try {
        const isRunning = await manager.isRunning();
        if (isRunning) {
            console.log(chalk.green('● Backend is running'));
            const info = await manager.getProcessInfo();
            if (info) {
                console.log(chalk.gray(`  PID: ${info.pid}`));
            }
            const health = await manager.getHealth();
            if (health.healthy) {
                console.log(chalk.green(`  Health: ${health.status}`));
            }
            else {
                console.log(chalk.yellow(`  Health: ${health.status}`));
            }
        }
        else {
            console.log(chalk.gray('⭘ Backend is not running'));
        }
        console.log(chalk.gray(`\n  Config: ~/.ambient/profiles/${options.profile}/`));
        console.log(chalk.gray(`  Database: ~/.ambient/profiles/${options.profile}/data/metagen.db`));
        console.log(chalk.gray(`  Logs: ~/.ambient/profiles/${options.profile}/logs/`));
    }
    catch (error) {
        console.error(chalk.red(`\n❌ Error checking status: ${error}`));
        process.exit(1);
    }
});
// Add version info
program
    .command('version')
    .description('Show version information')
    .action(() => {
    console.log(chalk.blue.bold('Ambient CLI'));
    console.log(`Version: ${packageJson.version}`);
    console.log(`Node: ${process.version}`);
    console.log(`Platform: ${process.platform}`);
});
// Handle unknown commands
program.on('command:*', () => {
    console.error(chalk.red('Invalid command: %s\nSee --help for available commands.'), program.args.join(' '));
    process.exit(1);
});
// Parse arguments
program.parse(process.argv);
// Show help if no command
if (!process.argv.slice(2).length) {
    console.log(chalk.blue.bold('🤖 Ambient CLI'));
    console.log(chalk.gray('Unified interface for Metagen\n'));
    program.outputHelp();
}
