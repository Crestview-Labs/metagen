/**
 * @license
 * Adapted from Google's Gemini CLI InputPrompt
 * SPDX-License-Identifier: Apache-2.0
 */
import React from 'react';
import { TextBuffer } from './TextBuffer.js';
export interface InputPromptProps {
    buffer: TextBuffer;
    onSubmit: (value: string) => void;
    placeholder?: string;
    focus?: boolean;
    inputWidth: number;
}
export declare const InputPrompt: React.FC<InputPromptProps>;
