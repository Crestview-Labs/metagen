import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    include: ['tests/**/*.test.ts'],
    exclude: ['tests/**/*.test.js', 'node_modules', 'dist'],
    globals: true,
    environment: 'node',
    testTimeout: 60000, // 60 seconds timeout for streaming tests
  },
  resolve: {
    extensions: ['.ts', '.js'],
  },
});