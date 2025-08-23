/**
 * Server command - run backend server only
 */

import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import { BackendManager } from '../backend/BackendManager.js';
import { getProfilePaths } from '../utils/paths.js';
import { ServerCommandOptions, BackendError } from '../types/index.js';

export const serverCommand = new Command('server')
  .description('Run the backend server')
  .option('-p, --profile <name>', 'Use specified profile', 'default')
  .option('--port <number>', 'Port to run server on', parseInt)
  .option('--host <host>', 'Host to bind to', '127.0.0.1')
  .option('-d, --detached', 'Run in detached mode')
  .option('-l, --log-level <level>', 'Log level (DEBUG|INFO|WARNING|ERROR)', 'INFO')
  .action(async (options: ServerCommandOptions) => {
    const profileName = options.profile || 'default';
    const profile = getProfilePaths(profileName);
    
    console.log(chalk.blue.bold('🚀 Ambient Server'));
    console.log(chalk.gray(`Profile: ${profileName}\n`));
    
    const manager = new BackendManager(profile);
    const spinner = ora('Starting backend server...').start();
    
    try {
      // Handle shutdown signals
      const shutdown = async () => {
        console.log('\n' + chalk.yellow('Shutting down...'));
        spinner.start('Stopping backend...');
        
        try {
          await manager.stop();
          spinner.succeed('Backend stopped');
          process.exit(0);
        } catch (error) {
          spinner.fail('Failed to stop backend cleanly');
          process.exit(1);
        }
      };
      
      process.on('SIGINT', shutdown);
      process.on('SIGTERM', shutdown);
      
      // Start the backend
      await manager.start({
        port: options.port,
        logLevel: options.logLevel as any,
        detached: options.detached,
        env: {
          METAGEN_HOST: options.host || '127.0.0.1'
        }
      });
      
      spinner.succeed('Backend started successfully');
      
      // Get process info
      const info = await manager.getProcessInfo();
      if (info) {
        console.log(chalk.green(`✓ Running with PID: ${info.pid}`));
      }
      
      // Show health status
      const health = await manager.getHealth();
      if (health.healthy) {
        console.log(chalk.green(`✓ Health check: ${health.status}`));
      }
      
      if (options.detached) {
        console.log(chalk.yellow('\nRunning in detached mode'));
        console.log(chalk.gray('To stop: ambient server stop'));
        process.exit(0);
      } else {
        console.log(chalk.gray('\nPress Ctrl+C to stop the server'));
        
        // Keep the process alive
        await new Promise(() => {});
      }
      
    } catch (error) {
      spinner.fail('Failed to start backend');
      
      if (error instanceof BackendError) {
        console.error(chalk.red(`\n❌ ${error.message}`));
        if (error.details) {
          console.error(chalk.gray(JSON.stringify(error.details, null, 2)));
        }
      } else {
        console.error(chalk.red(`\n❌ ${error}`));
      }
      
      process.exit(1);
    }
  });

// Add stop subcommand
serverCommand
  .command('stop')
  .description('Stop the backend server')
  .option('-p, --profile <name>', 'Profile to stop', 'default')
  .action(async (options) => {
    const profileName = options.profile || 'default';
    const profile = getProfilePaths(profileName);
    
    const manager = new BackendManager(profile);
    const spinner = ora('Stopping backend server...').start();
    
    try {
      const isRunning = await manager.isRunning();
      
      if (!isRunning) {
        spinner.info('Backend is not running');
        return;
      }
      
      await manager.stop();
      spinner.succeed('Backend stopped successfully');
      
    } catch (error) {
      spinner.fail('Failed to stop backend');
      console.error(chalk.red(`\n❌ ${error}`));
      process.exit(1);
    }
  });

// Add status subcommand
serverCommand
  .command('status')
  .description('Check backend server status')
  .option('-p, --profile <name>', 'Profile to check', 'default')
  .action(async (options) => {
    const profileName = options.profile || 'default';
    const profile = getProfilePaths(profileName);
    
    const manager = new BackendManager(profile);
    
    try {
      const isRunning = await manager.isRunning();
      
      if (!isRunning) {
        console.log(chalk.gray('⭘ Backend is not running'));
        return;
      }
      
      const info = await manager.getProcessInfo();
      const health = await manager.getHealth();
      
      console.log(chalk.green('● Backend is running'));
      
      if (info) {
        console.log(chalk.gray(`  PID: ${info.pid}`));
      }
      
      console.log(chalk.gray(`  Port: ${profile.port}`));
      console.log(chalk.gray(`  Profile: ${profileName}`));
      
      if (health.healthy) {
        console.log(chalk.green(`  Health: ${health.status}`));
        if (health.uptime) {
          const uptimeHours = Math.floor(health.uptime / 3600);
          const uptimeMinutes = Math.floor((health.uptime % 3600) / 60);
          console.log(chalk.gray(`  Uptime: ${uptimeHours}h ${uptimeMinutes}m`));
        }
      } else {
        console.log(chalk.yellow(`  Health: ${health.status}`));
        if (health.message) {
          console.log(chalk.yellow(`  Issue: ${health.message}`));
        }
      }
      
    } catch (error) {
      console.error(chalk.red(`❌ Failed to check status: ${error}`));
      process.exit(1);
    }
  });

// Add restart subcommand  
serverCommand
  .command('restart')
  .description('Restart the backend server')
  .option('-p, --profile <name>', 'Profile to restart', 'default')
  .action(async (options) => {
    const profileName = options.profile || 'default';
    const profile = getProfilePaths(profileName);
    
    const manager = new BackendManager(profile);
    const spinner = ora('Restarting backend server...').start();
    
    try {
      await manager.restart();
      spinner.succeed('Backend restarted successfully');
      
      const health = await manager.getHealth();
      if (health.healthy) {
        console.log(chalk.green(`✓ Health check: ${health.status}`));
      }
      
    } catch (error) {
      spinner.fail('Failed to restart backend');
      console.error(chalk.red(`\n❌ ${error}`));
      process.exit(1);
    }
  });