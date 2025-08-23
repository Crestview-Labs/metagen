/**
 * @license
 * Adapted from Google's Gemini CLI
 * SPDX-License-Identifier: Apache-2.0
 */
/**
 * Convert a string to an array of code points (characters), properly handling
 * Unicode surrogate pairs and other multi-byte characters.
 */
export declare function toCodePoints(str: string): string[];
/**
 * Get the length of a string in code points (not UTF-16 code units).
 * This properly handles Unicode characters that might be represented
 * as surrogate pairs.
 */
export declare function cpLen(str: string): number;
/**
 * Slice a string by code point positions (not UTF-16 code units).
 * This is similar to Array.slice() but for strings with proper Unicode handling.
 *
 * @param str The string to slice
 * @param start Start position (inclusive)
 * @param end End position (exclusive), or undefined for end of string
 * @returns The sliced string
 */
export declare function cpSlice(str: string, start: number, end?: number): string;
/**
 * Get a single character at the specified code point index.
 * Returns undefined if the index is out of bounds.
 */
export declare function cpCharAt(str: string, index: number): string | undefined;
/**
 * Find the index of a substring in terms of code points.
 * Returns -1 if not found.
 */
export declare function cpIndexOf(str: string, searchStr: string, fromIndex?: number): number;
/**
 * Check if a position is at a word boundary.
 * Used for word-wise navigation and selection.
 */
export declare function isWordBoundary(str: string, pos: number): boolean;
/**
 * Find the next word boundary starting from the given position.
 * Used for Ctrl+Right word movement.
 */
export declare function findNextWordBoundary(str: string, pos: number): number;
/**
 * Find the previous word boundary starting from the given position.
 * Used for Ctrl+Left word movement.
 */
export declare function findPrevWordBoundary(str: string, pos: number): number;
