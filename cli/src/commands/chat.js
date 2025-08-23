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
export async function chatCommand(options = {}) {
    const profileName = options.profile || 'default';
    const profile = getProfilePaths(profileName);
    // Check if backend is running, start if needed (unless disabled)
    if (!options.noAutoStart) {
        const manager = new BackendManager(profile);
        const isRunning = await manager.isRunning();
        if (!isRunning) {
            console.log(chalk.gray('Backend not running, starting...'));
            try {
                await manager.start({ detached: true });
                console.log(chalk.green('✓ Backend started'));
                // Give it a moment to fully initialize
                await new Promise(resolve => setTimeout(resolve, 2000));
            }
            catch (error) {
                console.error(chalk.red('Failed to start backend:'), error);
                console.error(chalk.yellow('Try running "ambient server" manually'));
                process.exit(1);
            }
        }
        else {
            // Backend already running - possibly shared with Mac app or other CLI instances
            console.log(chalk.gray(`Connecting to backend on port ${profile.port}...`));
        }
    }
    // Set the API URL based on profile port
    process.env.METAGEN_API_URL = `http://localhost:${profile.port}`;
    // Launch chat interface
    // Each render gets its own session ID (generated in the App component)
    // This ensures CLI and Mac app have separate sessions even when sharing backend
    const { waitUntilExit } = render(React.createElement(App, {
        initialMessage: options.message,
        autoApproveTools: options.autoApprove || !!options.message, // Auto-approve if single message
        exitOnComplete: !!options.message, // Exit after response if single message  
        minimalUI: !!options.message // Simpler UI for single message mode
    }));
    await waitUntilExit();
}
