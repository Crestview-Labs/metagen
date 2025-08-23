/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */
import { useEffect, useRef } from 'react';
import { useStdin } from 'ink';
import readline from 'readline';
/**
 * A hook that listens for keypress events from stdin, providing a
 * key object that mirrors the one from Node's `readline` module.
 * This provides much better key handling than Ink's useInput.
 */
export function useKeypress(onKeypress, { isActive }) {
    const { stdin, setRawMode } = useStdin();
    const onKeypressRef = useRef(onKeypress);
    useEffect(() => {
        onKeypressRef.current = onKeypress;
    }, [onKeypress]);
    useEffect(() => {
        if (!isActive || !stdin || !stdin.isTTY) {
            return;
        }
        setRawMode(true);
        const rl = readline.createInterface({ input: stdin });
        let isPaste = false;
        let pasteBuffer = Buffer.alloc(0);
        const handleKeypress = (_, key) => {
            if (!key)
                return;
            const mappedKey = {
                name: key.name || '',
                ctrl: key.ctrl || false,
                meta: key.meta || false,
                shift: key.shift || false,
                paste: false,
                sequence: key.sequence || ''
            };
            if (mappedKey.name === 'paste-start') {
                isPaste = true;
            }
            else if (mappedKey.name === 'paste-end') {
                isPaste = false;
                onKeypressRef.current({
                    name: '',
                    ctrl: false,
                    meta: false,
                    shift: false,
                    paste: true,
                    sequence: pasteBuffer.toString(),
                });
                pasteBuffer = Buffer.alloc(0);
            }
            else {
                if (isPaste) {
                    pasteBuffer = Buffer.concat([pasteBuffer, Buffer.from(mappedKey.sequence)]);
                }
                else {
                    // Handle special keys
                    if (mappedKey.name === 'return' && mappedKey.sequence === '\x1B\r') {
                        mappedKey.meta = true;
                    }
                    onKeypressRef.current({ ...mappedKey, paste: isPaste });
                }
            }
        };
        readline.emitKeypressEvents(stdin, rl);
        stdin.on('keypress', handleKeypress);
        return () => {
            stdin.removeListener('keypress', handleKeypress);
            rl.close();
            setRawMode(false);
            // If we are in the middle of a paste, send what we have.
            if (isPaste) {
                onKeypressRef.current({
                    name: '',
                    ctrl: false,
                    meta: false,
                    shift: false,
                    paste: true,
                    sequence: pasteBuffer.toString(),
                });
                pasteBuffer = Buffer.alloc(0);
            }
        };
    }, [isActive, stdin, setRawMode]);
}
