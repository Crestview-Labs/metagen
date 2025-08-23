import { jsx as _jsx, jsxs as _jsxs } from "react/jsx-runtime";
/**
 * @license
 * Adapted from Google's Gemini CLI InputPrompt
 * SPDX-License-Identifier: Apache-2.0
 */
import { useCallback } from 'react';
import { Box, Text } from 'ink';
import { cpSlice, cpLen } from '../utils/textUtils.js';
import chalk from 'chalk';
import stringWidth from 'string-width';
import { useKeypress } from '../hooks/useKeypress.js';
export const InputPrompt = ({ buffer, onSubmit, placeholder = 'Type your message or "/help" for commands', focus = true, inputWidth, }) => {
    // Handle submission and clearing pattern from Gemini CLI
    const handleSubmitAndClear = useCallback((submittedValue) => {
        // Store the value before clearing to prevent race conditions
        const valueToSubmit = submittedValue.trim();
        // Clear the buffer immediately to prevent corruption
        buffer.setText('');
        // Submit after clearing
        onSubmit(valueToSubmit);
    }, [onSubmit, buffer]);
    const handleInput = useCallback((key) => {
        if (!focus)
            return;
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
    return (_jsxs(Box, { borderStyle: "round", paddingLeft: 1, paddingRight: 1, children: [_jsx(Text, { color: "gray", bold: true, children: '> ' }), _jsx(Box, { flexGrow: 1, flexDirection: "column", children: buffer.text.length === 0 && placeholder ? (focus ? (_jsxs(Text, { children: [chalk.inverse(placeholder.slice(0, 1)), _jsx(Text, { color: "gray", children: placeholder.slice(1) })] })) : (_jsx(Text, { color: "gray", children: placeholder }))) : (linesToRender.map((lineText, visualIdxInRenderedSet) => {
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
                                const charToHighlight = cpSlice(display, relativeVisualColForHighlight, relativeVisualColForHighlight + 1) || ' ';
                                const highlighted = chalk.inverse(charToHighlight);
                                display =
                                    cpSlice(display, 0, relativeVisualColForHighlight) +
                                        highlighted +
                                        cpSlice(display, relativeVisualColForHighlight + 1);
                            }
                            else if (relativeVisualColForHighlight === cpLen(display) &&
                                cpLen(display) === inputWidth) {
                                display = display + chalk.inverse(' ');
                            }
                        }
                    }
                    return (_jsx(Text, { children: display }, `line-${visualIdxInRenderedSet}`));
                })) })] }));
};
