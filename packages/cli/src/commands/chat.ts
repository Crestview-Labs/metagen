import { Command } from 'commander';
import React from 'react';
import { render } from 'ink';
import chalk from 'chalk';
import App from '../components/App.js';
import { SystemService, OpenAPI, MetagenStreamingClient } from '../../../../api/ts/src/index.js';

// Configure API base URL
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

export const chatCommand = new Command('chat')
  .description('Chat with the metagen agent')
  .argument('[message]', 'Message to send to the agent')
  .option('-i, --interactive', 'Start interactive chat mode')
  .action(async (message, options) => {
    try {
      // Check if backend is running
      let isHealthy = false;
      try {
        await SystemService.healthCheckApiSystemHealthGet();
        isHealthy = true;
      } catch {
        isHealthy = false;
      }
      if (!isHealthy) {
        console.error(chalk.red('❌ Backend server is not running. Please start it with: npm run start:backend'));
        process.exit(1);
      }

      if (options.interactive || !message) {
        // Check if we're in a proper TTY environment
        if (!process.stdout.isTTY || !process.stdin.isTTY) {
          console.error(chalk.red('❌ Interactive mode requires a TTY terminal.'));
          console.error(chalk.yellow('💡 Tip: Try running directly in your terminal, not through a pipe or script.'));
          console.error(chalk.yellow('   Or use: metagen chat "your message" for single message mode.'));
          process.exit(1);
        }
        
        // Start interactive mode with React/Ink
        let instance: any = null;
        try {
          instance = render(React.createElement(App));
          await instance.waitUntilExit();
        } catch (error: any) {
          if (error.message?.includes('Raw mode')) {
            console.error(chalk.red('\n❌ Interactive mode error: Terminal does not support raw mode.'));
            console.error(chalk.yellow('💡 Try one of these solutions:'));
            console.error(chalk.yellow('   1. Run in a different terminal (Terminal.app, iTerm2, etc.)'));
            console.error(chalk.yellow('   2. Use SSH if running remotely'));
            console.error(chalk.yellow('   3. Use single message mode: metagen chat "your message"'));
          } else {
            console.error(chalk.red(`\n❌ Interactive mode error: ${error.message}`));
          }
          process.exit(1);
        } finally {
          // Clean up properly
          if (instance) {
            instance.unmount();
          }
        }
      } else {
        // Send single message with streaming
        console.log(chalk.blue('💬 Sending message to agent...'));
        
        console.log(chalk.green('\n🤖 Agent Response:'));
        
        let sessionId = null;
        const client = new MetagenStreamingClient();
        const streamGenerator = client.chatStream({ message, session_id: sessionId || '' });
        
        for await (const message of streamGenerator) {
          // Check for completion (AgentMessage with final flag)
          if (message.type === 'agent' && (message as any).final) {
            break;
          }
          
          // Format different response types
          switch (message.type) {
            case 'agent':
              // Main agent response content
              console.log((message as any).content);
              break;
            case 'thinking':
              console.log(chalk.yellow(`${(message as any).content}`));
              break;
            case 'tool_call':
              console.log(chalk.magenta(`🔧 Calling tool: ${(message as any).tool_name}`));
              break;
            case 'tool_started':
              console.log(chalk.blue(`▶️  Started: ${(message as any).tool_name}`));
              break;
            case 'tool_result':
              console.log(chalk.cyan(`✅ Result from ${(message as any).tool_name}`));
              break;
            case 'tool_error':
              console.log(chalk.red(`❌ Tool error: ${(message as any).error}`));
              break;
            case 'approval_request':
              console.log(chalk.yellow.bold(`🔐 Tool requires approval: ${(message as any).tool_name}`));
              console.log(chalk.yellow('Note: Run in interactive mode to approve/reject tools'));
              break;
            case 'approval_response':
              const decision = (message as any).decision;
              if (decision === 'approved') {
                console.log(chalk.green(`✅ Tool approved`));
              } else if (decision === 'rejected') {
                console.log(chalk.red(`❌ Tool rejected`));
              }
              break;
            case 'usage':
              // Token usage - skip in normal output
              break;
            case 'error':
              console.log(chalk.red(`❌ ${(message as any).message}`));
              break;
            default:
              // User or system messages
              if ('content' in message) {
                console.log((message as any).content);
              }
          }
        }
        
        console.log(chalk.gray(`\nSession: ${sessionId}`));
      }
    } catch (error) {
      console.error(chalk.red(`❌ Chat error: ${error instanceof Error ? error.message : error}`));
      process.exit(1);
    }
  });