// Test setup file for vitest
import { beforeAll, afterAll, beforeEach, afterEach } from 'vitest';
import fs from 'fs-extra';
import path from 'path';
import os from 'os';
// Create a temporary directory for test profiles
const TEST_HOME = path.join(os.tmpdir(), 'ambient-test', Date.now().toString());
beforeAll(async () => {
    // Set test environment
    process.env.AMBIENT_TEST_MODE = 'true';
    process.env.AMBIENT_CONFIG_DIR = TEST_HOME;
    // Create test directory
    await fs.ensureDir(TEST_HOME);
});
afterAll(async () => {
    // Clean up test directory
    try {
        await fs.remove(TEST_HOME);
    }
    catch (error) {
        console.warn('Failed to clean up test directory:', error);
    }
});
beforeEach(() => {
    // Reset any mocks or state
});
afterEach(() => {
    // Clean up after each test
});
// Helper to create test profile
export async function createTestProfile(name) {
    const profileDir = path.join(TEST_HOME, 'profiles', name);
    await fs.ensureDir(profileDir);
    await fs.ensureDir(path.join(profileDir, 'data'));
    await fs.ensureDir(path.join(profileDir, 'logs'));
    return profileDir;
}
// Helper to clean test profile
export async function cleanTestProfile(name) {
    const profileDir = path.join(TEST_HOME, 'profiles', name);
    await fs.remove(profileDir);
}
// Mock process spawning for tests
export function mockSpawn() {
    return {
        pid: 12345,
        stdout: { pipe: jest.fn(), on: jest.fn() },
        stderr: { pipe: jest.fn(), on: jest.fn() },
        on: jest.fn(),
        kill: jest.fn()
    };
}
