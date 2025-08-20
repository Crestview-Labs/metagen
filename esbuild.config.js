import { build } from 'esbuild';
import { existsSync, mkdirSync } from 'fs';
import { createRequire } from 'module';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const require = createRequire(import.meta.url);
const pkg = require(path.resolve(__dirname, 'package.json'));

// Ensure bundle directory exists
if (!existsSync('bundle')) {
  mkdirSync('bundle');
}

// ESM compatibility banner - creates require function and sets __filename/__dirname
const banner = `import { createRequire } from 'module'; const require = createRequire(import.meta.url); globalThis.__filename = require('url').fileURLToPath(import.meta.url); globalThis.__dirname = require('path').dirname(globalThis.__filename);`;

build({
  entryPoints: ['packages/cli/dist/packages/cli/src/index.js'],
  bundle: true,
  outfile: 'bundle/metagen.js',
  platform: 'node',
  target: 'node18',
  format: 'esm', // Changed from 'cjs' to 'esm'
  banner: { js: banner },
  external: [
    // Only exclude native/optional dependencies
    'fsevents'
  ],
  mainFields: ['module', 'main'],
  conditions: ['import', 'node'],
  keepNames: true,
  sourcemap: true,
  minify: false,
  logLevel: 'info',
  define: {
    'process.env.CLI_VERSION': JSON.stringify(pkg.version),
  }
}).then(() => {
  console.log('✅ Bundle created successfully!');
}).catch((error) => {
  console.error('❌ Build failed:', error);
  process.exit(1);
});