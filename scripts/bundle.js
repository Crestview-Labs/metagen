#!/usr/bin/env node

import { execSync } from 'child_process';
import { dirname, join } from 'path';
import { fileURLToPath } from 'url';
import { chmodSync, readFileSync, writeFileSync, existsSync, mkdirSync } from 'fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
const rootDir = join(__dirname, '..');

console.log('📦 Creating CLI bundle...');

try {
  // Create bundle directory
  const bundleDir = join(rootDir, 'bundle');
  if (!existsSync(bundleDir)) {
    mkdirSync(bundleDir, { recursive: true });
  }

  // Run esbuild config
  execSync('node esbuild.config.js', { 
    stdio: 'inherit',
    cwd: rootDir
  });

  // Make it executable
  const bundlePath = join(bundleDir, 'metagen.js');
  chmodSync(bundlePath, '755');

  // Add shebang
  const content = readFileSync(bundlePath, 'utf-8');
  if (!content.startsWith('#!/usr/bin/env node')) {
    writeFileSync(bundlePath, '#!/usr/bin/env node\n' + content);
  }

  console.log('✅ Bundle created successfully at bundle/metagen.js');
} catch (error) {
  console.error('❌ Bundle failed:', error.message);
  process.exit(1);
}