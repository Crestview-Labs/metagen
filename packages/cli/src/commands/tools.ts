import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import { ToolsService, OpenAPI } from '../../../../api/ts/src/index.js';

// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

export const toolsCommand = new Command('tools')
  .description('List available tools')
  .option('-g, --google-only', 'Show only Google tools')
  .action(async (options) => {
    const spinner = ora('Fetching available tools...').start();
    
    try {
      const response = options.googleOnly 
        ? await ToolsService.getGoogleToolsApiToolsGoogleGet()
        : await ToolsService.getToolsApiToolsGet();
      
      spinner.stop();
      
      console.log(chalk.blue.bold(`🔧 Available Tools (${response.count})`));
      console.log();
      
      if (response.tools.length === 0) {
        console.log(chalk.yellow('⚠️  No tools available'));
        return;
      }
      
      response.tools.forEach((tool: any, index: number) => {
        console.log(chalk.green(`${index + 1}. ${tool.name}`));
        console.log(chalk.gray(`   ${tool.description}`));
        
        // Show input schema if it exists
        if (tool.input_schema && Object.keys(tool.input_schema).length > 0) {
          const paramNames = Object.keys(tool.input_schema.properties || {});
          if (paramNames.length > 0) {
            console.log(chalk.gray(`   Parameters: ${paramNames.join(', ')}`));
          }
        }
        console.log();
      });
      
    } catch (error) {
      spinner.stop();
      console.error(chalk.red(`❌ Error fetching tools: ${error instanceof Error ? error.message : String(error)}`));
      process.exit(1);
    }
  });