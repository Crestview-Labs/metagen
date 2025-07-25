import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import { apiClient } from '@metagen/api-client';

export const authCommand = new Command('auth')
  .description('Authentication commands');

authCommand
  .command('status')
  .description('Check authentication status')
  .action(async () => {
    const spinner = ora('Checking authentication status...').start();
    
    try {
      const status = await apiClient.getAuthStatus();
      spinner.stop();
      
      if (status.authenticated) {
        console.log(chalk.green('✅ Authenticated'));
        if (status.email) {
          console.log(chalk.gray(`   User: ${status.email}`));
        }
        if (status.expires_at) {
          console.log(chalk.gray(`   Expires: ${status.expires_at}`));
        }
      } else {
        console.log(chalk.yellow('⚠️  Not authenticated'));
        console.log(chalk.gray('   Run "metagen auth login" to authenticate'));
      }
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error checking auth status: ${error instanceof Error ? error.message : error}`));
      process.exit(1);
    }
  });

authCommand
  .command('login')
  .description('Login with Google OAuth')
  .option('--force', 'Force re-authentication even if already logged in')
  .action(async (options) => {
    const spinner = ora('Initiating Google OAuth login...').start();
    
    try {
      const response = await apiClient.login(options.force);
      spinner.stop();
      
      console.log(chalk.blue('🔐 Google OAuth Login'));
      console.log(chalk.gray(response.message));
      console.log(chalk.yellow(`\n🌐 Open this URL in your browser:`));
      console.log(chalk.cyan(response.auth_url));
      console.log(chalk.gray('\nWaiting for authentication...'));
      
      // Poll for authentication status
      const pollInterval = setInterval(async () => {
        try {
          const status = await apiClient.getAuthStatus();
          if (status.authenticated) {
            clearInterval(pollInterval);
            clearTimeout(timeoutId);
            console.log(chalk.green('\n✅ Authentication successful!'));
            if (status.email) {
              console.log(chalk.gray(`   Logged in as: ${status.email}`));
            }
          }
        } catch {
          // Continue polling
        }
      }, 2000);
      
      // Stop polling after 5 minutes
      const timeoutId = setTimeout(() => {
        clearInterval(pollInterval);
        console.log(chalk.yellow('\n⏰ Authentication timeout. Please try again.'));
      }, 300000);
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Login error: ${error instanceof Error ? error.message : error}`));
      process.exit(1);
    }
  });

authCommand
  .command('logout')
  .description('Logout and clear tokens')
  .action(async () => {
    const spinner = ora('Logging out...').start();
    
    try {
      const response = await apiClient.logout();
      spinner.stop();
      
      console.log(chalk.green('✅ Logged out successfully'));
      console.log(chalk.gray(response.message));
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Logout error: ${error instanceof Error ? error.message : error}`));
      process.exit(1);
    }
  });