#!/usr/bin/env node
import { Command } from 'commander';
import chalk from 'chalk';
import { chatCommand } from './commands/chat.js';
import { authCommand } from './commands/auth.js';
import { toolsCommand } from './commands/tools.js';
import { systemCommand } from './commands/system.js';

const program = new Command();

program
  .name('metagen')
  .description('Metagen - Superintelligent Personal Agent CLI')
  .version('0.1.0');

// Add commands
program.addCommand(chatCommand);
program.addCommand(authCommand);
program.addCommand(toolsCommand);
program.addCommand(systemCommand);

// Add help command
program
  .command('help [command]')
  .description('Show help information')
  .action((command) => {
    if (command) {
      program.commands.find(cmd => cmd.name() === command)?.help();
    } else {
      program.help();
    }
  });

// Handle unknown commands
program.on('command:*', () => {
  console.error(chalk.red('Invalid command: %s\nSee --help for a list of available commands.'), program.args.join(' '));
  process.exit(1);
});

// Parse command line arguments
program.parse(process.argv);

// Show help if no command provided
if (!process.argv.slice(2).length) {
  console.log(chalk.blue.bold('🤖 Metagen CLI'));
  console.log(chalk.gray('Superintelligent Personal Agent\n'));
  program.outputHelp();
}