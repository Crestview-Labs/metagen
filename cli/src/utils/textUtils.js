/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */
/**
 * Convert a string to an array of code points (characters), properly handling
 * Unicode surrogate pairs and other multi-byte characters.
 */
export function toCodePoints(str) {
    const codePoints = [];
    for (const char of str) {
        codePoints.push(char);
    }
    return codePoints;
}
/**
 * Get the length of a string in code points (not UTF-16 code units).
 * This properly handles Unicode characters that might be represented
 * as surrogate pairs.
 */
export function cpLen(str) {
    return [...str].length;
}
/**
 * Slice a string by code point positions (not UTF-16 code units).
 * This is similar to Array.slice() but for strings with proper Unicode handling.
 *
 * @param str The string to slice
 * @param start Start position (inclusive)
 * @param end End position (exclusive), or undefined for end of string
 * @returns The sliced string
 */
export function cpSlice(str, start, end) {
    const codePoints = [...str];
    return codePoints.slice(start, end).join('');
}
/**
 * Get a single character at the specified code point index.
 * Returns undefined if the index is out of bounds.
 */
export function cpCharAt(str, index) {
    const codePoints = [...str];
    return codePoints[index];
}
/**
 * Find the index of a substring in terms of code points.
 * Returns -1 if not found.
 */
export function cpIndexOf(str, searchStr, fromIndex = 0) {
    const codePoints = [...str];
    const searchCodePoints = [...searchStr];
    for (let i = fromIndex; i <= codePoints.length - searchCodePoints.length; i++) {
        let found = true;
        for (let j = 0; j < searchCodePoints.length; j++) {
            if (codePoints[i + j] !== searchCodePoints[j]) {
                found = false;
                break;
            }
        }
        if (found)
            return i;
    }
    return -1;
}
/**
 * Check if a position is at a word boundary.
 * Used for word-wise navigation and selection.
 */
export function isWordBoundary(str, pos) {
    const codePoints = [...str];
    if (pos <= 0 || pos >= codePoints.length)
        return true;
    const prevChar = codePoints[pos - 1];
    const currChar = codePoints[pos];
    const isWordChar = (ch) => /\w/.test(ch);
    return isWordChar(prevChar) !== isWordChar(currChar);
}
/**
 * Find the next word boundary starting from the given position.
 * Used for Ctrl+Right word movement.
 */
export function findNextWordBoundary(str, pos) {
    const codePoints = [...str];
    let i = pos;
    // Skip current word characters
    while (i < codePoints.length && /\w/.test(codePoints[i]))
        i++;
    // Skip whitespace
    while (i < codePoints.length && /\s/.test(codePoints[i]))
        i++;
    return i;
}
/**
 * Find the previous word boundary starting from the given position.
 * Used for Ctrl+Left word movement.
 */
export function findPrevWordBoundary(str, pos) {
    const codePoints = [...str];
    let i = pos - 1;
    // Skip whitespace
    while (i >= 0 && /\s/.test(codePoints[i]))
        i--;
    // Skip word characters
    while (i >= 0 && /\w/.test(codePoints[i]))
        i--;
    return i + 1;
}
