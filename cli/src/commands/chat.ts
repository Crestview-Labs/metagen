/**
 * Chat command with auto-start backend support
 * Each CLI instance gets its own session, even when sharing a backend
 */

import chalk from 'chalk';
import React from 'react';
import { render } from 'ink';
import { BackendManager } from '../backend/BackendManager.js';
import { getProfilePaths } from '../utils/paths.js';
import App from '../components/App.js';

interface ChatOptions {
  profile?: string;
  message?: string;
  autoApprove?: boolean;
}

export async function chatCommand(options: ChatOptions = {}) {
  const profileName = options.profile || 'default';
  const profile = getProfilePaths(profileName);
  
  // Check if backend is accessible
  const manager = new BackendManager(profile);
  
  try {
    const health = await manager.getHealth();
    if (health.status === 'healthy') {
      console.log(chalk.gray(`Connected to backend on port ${profile.port}`));
    }
  } catch (error) {
    console.error(chalk.red('❌ Cannot connect to backend'));
    console.error(chalk.yellow('Start it with one of these commands:'));
    console.error(chalk.cyan('  uv run python launch.py server start'));
    console.error(chalk.cyan('  uv run python main.py'));
    process.exit(1);
  }
  
  // Set the API URL based on profile port
  process.env.METAGEN_API_URL = `http://localhost:${profile.port}`;
  
  // Launch chat interface
  // Each render gets its own session ID (generated in the App component)
  // This ensures CLI and Mac app have separate sessions even when sharing backend
  const { waitUntilExit } = render(
    React.createElement(App, {
      initialMessage: options.message,
      autoApproveTools: options.autoApprove || !!options.message, // Auto-approve if single message
      exitOnComplete: !!options.message, // Exit after response if single message  
      minimalUI: !!options.message // Simpler UI for single message mode
    })
  );
  
  await waitUntilExit();
}