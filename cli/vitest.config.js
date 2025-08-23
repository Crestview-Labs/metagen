import { defineConfig } from 'vitest/config';
import path from 'path';
export default defineConfig({
    test: {
        globals: true,
        environment: 'node',
        coverage: {
            provider: 'v8',
            reporter: ['text', 'json', 'html'],
            exclude: [
                'node_modules/',
                'dist/',
                '*.config.ts',
                'tests/',
                'src/types/'
            ],
            thresholds: {
                branches: 80,
                functions: 80,
                lines: 85,
                statements: 85
            }
        },
        testTimeout: 10000,
        setupFiles: ['./tests/helpers/setup.ts']
    },
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
            '@backend': path.resolve(__dirname, './src/backend'),
            '@commands': path.resolve(__dirname, './src/commands'),
            '@utils': path.resolve(__dirname, './src/utils'),
            '@types': path.resolve(__dirname, './src/types')
        }
    }
});
