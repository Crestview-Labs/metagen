/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */
export interface Key {
    name: string;
    ctrl: boolean;
    meta: boolean;
    shift: boolean;
    paste: boolean;
    sequence: string;
}
/**
 * A hook that listens for keypress events from stdin, providing a
 * key object that mirrors the one from Node's `readline` module.
 * This provides much better key handling than Ink's useInput.
 */
export declare function useKeypress(onKeypress: (key: Key) => void, { isActive }: {
    isActive: boolean;
}): void;
