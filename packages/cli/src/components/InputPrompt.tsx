/**
 * @license
 * Adapted from Google's Gemini CLI InputPrompt
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useCallback } from 'react';
import { Box, Text } from 'ink';
import { TextBuffer } from './TextBuffer.js';
import { cpSlice, cpLen } from '../utils/textUtils.js';
import chalk from 'chalk';
import stringWidth from 'string-width';
import { useKeypress, Key } from '../hooks/useKeypress.js';

export interface InputPromptProps {
  buffer: TextBuffer;
  onSubmit: (value: string) => void;
  placeholder?: string;
  focus?: boolean;
  inputWidth: number;
}

export const InputPrompt: React.FC<InputPromptProps> = ({
  buffer,
  onSubmit,
  placeholder = 'Type your message or "/help" for commands',
  focus = true,
  inputWidth,
}) => {
  // Handle submission and clearing pattern from Gemini CLI
  const handleSubmitAndClear = useCallback(
    (submittedValue: string) => {
      // Store the value before clearing to prevent race conditions
      const valueToSubmit = submittedValue.trim();
      
      // Clear the buffer immediately to prevent corruption
      buffer.setText('');
      
      // Submit after clearing
      onSubmit(valueToSubmit);
    },
    [onSubmit, buffer],
  );

  const handleInput = useCallback((key: Key) => {
    if (!focus) return;

    // Handle Enter for submission
    if (key.name === 'return' && !key.ctrl && !key.meta) {
      const text = buffer.text.trim();
      if (text) {
        handleSubmitAndClear(text);
      }
      return;
    }

    // Let the text buffer handle all input
    buffer.handleInput(key);
  }, [focus, buffer, handleSubmitAndClear]);

  useKeypress(handleInput, { isActive: focus });

  const linesToRender = buffer.viewportVisualLines;
  const [cursorVisualRowAbsolute, cursorVisualColAbsolute] = buffer.visualCursor;
  const scrollVisualRow = buffer.visualScrollRow;

  const isCommandMode = buffer.text.startsWith('/');

  return (
    <Box borderStyle="round" paddingLeft={1} paddingRight={1}>
      <Text color="gray" bold>{'> '}</Text>
      <Box flexGrow={1} flexDirection="column">
        {buffer.text.length === 0 && placeholder ? (
          focus ? (
            <Text>
              {chalk.inverse(placeholder.slice(0, 1))}
              <Text color="gray">{placeholder.slice(1)}</Text>
            </Text>
          ) : (
            <Text color="gray">{placeholder}</Text>
          )
        ) : (
          linesToRender.map((lineText, visualIdxInRenderedSet) => {
            const cursorVisualRow = cursorVisualRowAbsolute - scrollVisualRow;
            let display = cpSlice(lineText, 0, inputWidth);
            const currentVisualWidth = stringWidth(display);
            
            // Pad the line to the full width
            if (currentVisualWidth < inputWidth) {
              display = display + ' '.repeat(inputWidth - currentVisualWidth);
            }

            // Highlight the cursor position
            if (visualIdxInRenderedSet === cursorVisualRow && focus) {
              const relativeVisualColForHighlight = cursorVisualColAbsolute;
              if (relativeVisualColForHighlight >= 0) {
                if (relativeVisualColForHighlight < cpLen(display)) {
                  const charToHighlight =
                    cpSlice(
                      display,
                      relativeVisualColForHighlight,
                      relativeVisualColForHighlight + 1,
                    ) || ' ';
                  const highlighted = chalk.inverse(charToHighlight);
                  display =
                    cpSlice(display, 0, relativeVisualColForHighlight) +
                    highlighted +
                    cpSlice(display, relativeVisualColForHighlight + 1);
                } else if (
                  relativeVisualColForHighlight === cpLen(display) &&
                  cpLen(display) === inputWidth
                ) {
                  display = display + chalk.inverse(' ');
                }
              }
            }
            
            return (
              <Text key={`line-${visualIdxInRenderedSet}`}>{display}</Text>
            );
          })
        )}
      </Box>
    </Box>
  );
};