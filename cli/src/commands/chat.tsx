/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */

import React from 'react';
import { render } from 'ink';
import App from '../components/App.js';
import { MetagenStreamingClient, OpenAPI } from '../../../api/ts/src/index.js';

// Configure API
OpenAPI.BASE = process.env.METAGEN_API_URL || 'http://localhost:8080';

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
      
      const client = new MetagenStreamingClient();
      let fullResponse = '';
      
      await client.streamChat(
        { message, session_id: client.generateSessionId() },
        (chunk) => {
          if (chunk.type === 'text' && chunk.content) {
            process.stdout.write(chunk.content);
            fullResponse += chunk.content;
          }
        }
      );
      
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