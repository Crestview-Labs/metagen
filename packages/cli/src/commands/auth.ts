import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import { AuthenticationService, OpenAPI } from '../../../../api/ts/src/index.js';

// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

export const authCommand = new Command('auth')
  .description('Authentication commands');

authCommand
  .command('status')
  .description('Check authentication status')
  .action(async () => {
    const spinner = ora('Checking authentication status...').start();
    
    try {
      const status = await AuthenticationService.getAuthStatusApiAuthStatusGet();
      spinner.stop();
      
      if (status.authenticated) {
        console.log(chalk.green('✅ Authenticated'));
        if (status.user_info?.email) {
          console.log(chalk.gray(`   User: ${status.user_info.email}`));
        }
      } else {
        console.log(chalk.yellow('⚠️  Not authenticated'));
        console.log(chalk.gray('   Run "metagen auth login" to authenticate'));
      }
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error checking auth status: ${error instanceof Error ? error.message : String(error)}`));
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
      const response = await AuthenticationService.loginApiAuthLoginPost({
        requestBody: { force: options.force || false }
      });
      spinner.stop();
      
      if (response.auth_url) {
        console.log(chalk.blue('🔐 Google OAuth Login'));
        console.log(chalk.gray(response.message || 'Login required'));
        console.log(chalk.yellow(`\n🌐 Open this URL in your browser:`));
        console.log(chalk.cyan(response.auth_url));
        console.log(chalk.gray('\nWaiting for authentication...'));
        
        // Try to open the URL in the browser
        try {
          const open = (await import('open')).default;
          await open(response.auth_url);
        } catch {
          // Ignore errors - user can manually open the URL
        }
        
        // Poll for authentication status
        const pollInterval = setInterval(async () => {
          try {
            const status = await AuthenticationService.getAuthStatusApiAuthStatusGet();
            if (status.authenticated) {
              clearInterval(pollInterval);
              clearTimeout(timeoutId);
              console.log(chalk.green('\n✅ Authentication successful!'));
              if (status.user_info?.email) {
                console.log(chalk.gray(`   Logged in as: ${status.user_info.email}`));
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
      } else {
        console.log(chalk.green('✅ ' + (response.message || 'Already authenticated')));
      }
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Login error: ${error instanceof Error ? error.message : String(error)}`));
      process.exit(1);
    }
  });

authCommand
  .command('logout')
  .description('Logout and clear tokens')
  .action(async () => {
    const spinner = ora('Logging out...').start();
    
    try {
      await AuthenticationService.logoutApiAuthLogoutPost();
      spinner.stop();
      
      console.log(chalk.green('✅ Logged out successfully'));
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Logout error: ${error instanceof Error ? error.message : String(error)}`));
      process.exit(1);
    }
  });