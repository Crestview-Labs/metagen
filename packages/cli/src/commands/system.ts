import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import { apiClient } from '@metagen/api-client';

export const systemCommand = new Command('system')
  .description('System information and health checks');

systemCommand
  .command('info')
  .description('Show system information')
  .action(async () => {
    const spinner = ora('Fetching system information...').start();
    
    try {
      const info = await apiClient.getSystemInfo();
      spinner.stop();
      
      console.log(chalk.blue.bold('📊 System Information'));
      console.log();
      console.log(chalk.green(`Agent Name: ${info.agent_name}`));
      console.log(chalk.green(`Model: ${info.model}`));
      console.log(chalk.green(`Tools Available: ${info.tool_count}`));
      console.log(chalk.green(`Memory Path: ${info.memory_path}`));
      console.log(chalk.green(`Initialized: ${info.initialized ? '✅' : '❌'}`));
      
      if (info.tools && info.tools.length > 0) {
        console.log();
        console.log(chalk.blue('🔧 Tools:'));
        info.tools.forEach((tool, index) => {
          console.log(chalk.gray(`  ${index + 1}. ${tool.name} - ${tool.description}`));
        });
      }
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error fetching system info: ${error instanceof Error ? error.message : error}`));
      process.exit(1);
    }
  });

systemCommand
  .command('health')
  .description('Check system health')
  .action(async () => {
    const spinner = ora('Checking system health...').start();
    
    try {
      const health = await apiClient.getSystemHealth();
      spinner.stop();
      
      console.log(chalk.blue.bold('🏥 System Health'));
      console.log();
      
      const statusColor = health.status === 'healthy' ? chalk.green : 
                         health.status === 'degraded' ? chalk.yellow : chalk.red;
      
      console.log(`Status: ${statusColor(health.status.toUpperCase())}`);
      
      if (health.components) {
        console.log();
        console.log(chalk.blue('Components:'));
        Object.entries(health.components).forEach(([component, status]) => {
          const componentColor = status.includes('available') || status.includes('initialized') ? 
                                chalk.green : chalk.yellow;
          console.log(`  ${component}: ${componentColor(status)}`);
        });
      }
      
      if (health.error) {
        console.log();
        console.log(chalk.red(`Error: ${health.error}`));
      }
      
      console.log();
      console.log(chalk.gray(`Last checked: ${health.timestamp}`));
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error checking health: ${error instanceof Error ? error.message : error}`));
      process.exit(1);
    }
  });

systemCommand
  .command('status')
  .description('Quick status check (health + auth)')
  .action(async () => {
    const spinner = ora('Checking system status...').start();
    
    try {
      const [health, auth] = await Promise.all([
        apiClient.getSystemHealth(),
        apiClient.getAuthStatus()
      ]);
      
      spinner.stop();
      
      console.log(chalk.blue.bold('⚡ Quick Status'));
      console.log();
      
      // System health
      const statusColor = health.status === 'healthy' ? chalk.green : 
                         health.status === 'degraded' ? chalk.yellow : chalk.red;
      console.log(`System: ${statusColor(health.status.toUpperCase())}`);
      
      // Authentication
      const authColor = auth.authenticated ? chalk.green : chalk.yellow;
      const authStatus = auth.authenticated ? '✅ Authenticated' : '⚠️  Not authenticated';
      console.log(`Auth: ${authColor(authStatus)}`);
      
      if (auth.authenticated && auth.email) {
        console.log(chalk.gray(`  User: ${auth.email}`));
      }
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error checking status: ${error instanceof Error ? error.message : error}`));
      process.exit(1);
    }
  });