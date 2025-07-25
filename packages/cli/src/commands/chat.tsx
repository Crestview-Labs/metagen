/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { render } from 'ink';
import App from '../components/App.js';
import { apiClient } from '@metagen/api-client';

interface ChatOptions {
  interactive?: boolean;
}

export async function chatCommand(message: string | undefined, options: ChatOptions) {
  if (options.interactive || !message) {
    // Interactive mode - use the sophisticated App component
    const { waitUntilExit } = render(<App />);
    await waitUntilExit();
  } else {
    // Single message mode
    try {
      console.log('🤖 Sending message to agent...');
      
      let fullResponse = '';
      const streamGenerator = apiClient.sendMessageStream({ message });
      
      for await (const chunk of streamGenerator) {
        if (chunk.type === 'text') {
          process.stdout.write(chunk.content);
          fullResponse += chunk.content;
        } else if (chunk.type === 'complete') {
          break;
        }
      }
      
      if (fullResponse) {
        console.log('\n'); // Add final newline
      } else {
        console.log('No response received from agent.');
      }
    } catch (error) {
      console.error('❌ Error:', error instanceof Error ? error.message : error);
      process.exit(1);
    }
  }
}