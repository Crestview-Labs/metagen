import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import { SystemService, AuthenticationService, OpenAPI } from '../../../../api/ts/src/index.js';

// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

export const systemCommand = new Command('system')
  .description('System information and health checks');

systemCommand
  .command('info')
  .description('Show system information')
  .action(async () => {
    const spinner = ora('Fetching system information...').start();
    
    try {
      const info = await SystemService.getSystemInfoApiSystemInfoGet();
      spinner.stop();
      
      console.log(chalk.blue.bold('📊 System Information'));
      console.log();
      console.log(chalk.green(`Agent: ${info.agent_name}`));
      console.log(chalk.green(`Model: ${info.model}`));
      console.log(chalk.green(`Tools: ${info.tool_count}`));
      console.log(chalk.green(`Memory: ${info.memory_path}`));
      
      // Tools are fetched separately via /api/tools endpoint
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error fetching system info: ${error instanceof Error ? error.message : String(error)}`));
      process.exit(1);
    }
  });

systemCommand
  .command('health')
  .description('Check system health')
  .action(async () => {
    const spinner = ora('Checking system health...').start();
    
    try {
      await SystemService.healthCheckApiSystemHealthGet();
      spinner.stop();
      
      console.log(chalk.blue.bold('🏥 System Health'));
      console.log();
      console.log(`Status: ${chalk.green('HEALTHY')}`);
      console.log();
      console.log(chalk.gray(`Last checked: ${new Date().toISOString()}`));
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error checking health: ${error instanceof Error ? error.message : String(error)}`));
      process.exit(1);
    }
  });

systemCommand
  .command('status')
  .description('Quick status check (health + auth)')
  .action(async () => {
    const spinner = ora('Checking system status...').start();
    
    try {
      const [healthOk, auth] = await Promise.all([
        SystemService.healthCheckApiSystemHealthGet().then(() => true).catch(() => false),
        AuthenticationService.getAuthStatusApiAuthStatusGet()
      ]);
      
      spinner.stop();
      
      console.log(chalk.blue.bold('⚡ Quick Status'));
      console.log();
      
      // System health
      const statusColor = healthOk ? chalk.green : chalk.red;
      console.log(`System: ${statusColor(healthOk ? 'HEALTHY' : 'UNHEALTHY')}`);
      
      // Authentication
      const authColor = auth.authenticated ? chalk.green : chalk.yellow;
      const authStatus = auth.authenticated ? '✅ Authenticated' : '⚠️  Not authenticated';
      console.log(`Auth: ${authColor(authStatus)}`);
      
      if (auth.authenticated && auth.user_info?.email) {
        console.log(chalk.gray(`  User: ${auth.user_info.email}`));
      }
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error checking status: ${error instanceof Error ? error.message : String(error)}`));
      process.exit(1);
    }
  });