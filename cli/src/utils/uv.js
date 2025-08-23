/**
 * UV Package Manager utilities
 * Handles downloading and managing the uv Python package manager
 */
import { promises as fs } from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import fetch from 'node-fetch';
import { createWriteStream } from 'fs';
import { pipeline } from 'stream/promises';
import { getAmbientHome, fileExists } from './paths.js';
import which from 'which';
import chalk from 'chalk';
/**
 * Get the platform-specific uv binary name
 */
function getUvBinaryName() {
    const platform = process.platform;
    const arch = process.arch;
    if (platform === 'darwin') {
        // macOS
        if (arch === 'x64') {
            return 'uv-x86_64-apple-darwin';
        }
        else if (arch === 'arm64') {
            return 'uv-aarch64-apple-darwin';
        }
    }
    else if (platform === 'linux') {
        // Linux
        if (arch === 'x64') {
            return 'uv-x86_64-unknown-linux-gnu';
        }
        else if (arch === 'arm64') {
            return 'uv-aarch64-unknown-linux-gnu';
        }
    }
    else if (platform === 'win32') {
        // Windows
        if (arch === 'x64') {
            return 'uv-x86_64-pc-windows-msvc.exe';
        }
    }
    throw new Error(`Unsupported platform: ${platform} ${arch}`);
}
/**
 * Get the URL to download uv from
 */
function getUvDownloadUrl() {
    const binaryName = getUvBinaryName();
    // Using a stable version instead of 'latest' for reproducibility
    const version = '0.4.18'; // Update this as needed
    return `https://github.com/astral-sh/uv/releases/download/${version}/${binaryName}.tar.gz`;
}
/**
 * Download and extract uv binary
 */
async function downloadUv(targetPath) {
    const url = getUvDownloadUrl();
    const tempFile = `${targetPath}.download`;
    console.log(chalk.gray(`Downloading from ${url}...`));
    try {
        // Download the file
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`Failed to download: ${response.statusText}`);
        }
        // Save to temp file
        const fileStream = createWriteStream(tempFile);
        await pipeline(response.body, fileStream);
        // Extract (uv releases are tar.gz)
        if (process.platform === 'win32') {
            // On Windows, the binary might be direct exe
            await fs.rename(tempFile, targetPath);
        }
        else {
            // On Unix, extract from tar.gz
            execSync(`tar -xzf ${tempFile} -C ${path.dirname(targetPath)}`, {
                stdio: 'ignore'
            });
            // The extracted binary might have the same name as downloaded
            const extractedBinary = path.join(path.dirname(targetPath), getUvBinaryName());
            if (await fileExists(extractedBinary)) {
                await fs.rename(extractedBinary, targetPath);
            }
            // Clean up temp file
            await fs.unlink(tempFile).catch(() => { });
        }
        // Make executable on Unix
        if (process.platform !== 'win32') {
            await fs.chmod(targetPath, 0o755);
        }
    }
    catch (error) {
        // Clean up on failure
        await fs.unlink(tempFile).catch(() => { });
        await fs.unlink(targetPath).catch(() => { });
        throw error;
    }
}
/**
 * Ensure uv is available, downloading if necessary
 */
export async function ensureUv() {
    // 1. Check if uv exists in system PATH
    try {
        const systemUv = await which('uv');
        console.log(chalk.green('✓ Using system uv'));
        return systemUv;
    }
    catch {
        // Not found in system PATH
    }
    // 2. Check if we've already downloaded it
    const ambientBin = path.join(getAmbientHome(), 'bin');
    const localUv = path.join(ambientBin, process.platform === 'win32' ? 'uv.exe' : 'uv');
    if (await fileExists(localUv)) {
        console.log(chalk.green('✓ Using Ambient-managed uv'));
        return localUv;
    }
    // 3. Need to download it
    console.log(chalk.yellow('uv package manager not found'));
    console.log(chalk.gray('uv is required for Python environment management'));
    // Create bin directory if it doesn't exist
    await fs.mkdir(ambientBin, { recursive: true });
    // Download uv
    console.log(chalk.blue('📦 Downloading uv package manager...'));
    try {
        await downloadUv(localUv);
        console.log(chalk.green('✓ uv installed successfully'));
        // Verify it works
        try {
            execSync(`${localUv} --version`, { stdio: 'ignore' });
        }
        catch (error) {
            throw new Error('Downloaded uv binary is not working correctly');
        }
        return localUv;
    }
    catch (error) {
        console.error(chalk.red('Failed to download uv:'), error);
        throw new Error('Failed to download uv. You can install it manually:\n' +
            '  curl -LsSf https://astral.sh/uv/install.sh | sh\n' +
            'Or on macOS with Homebrew:\n' +
            '  brew install uv');
    }
}
/**
 * Check if uv is available without downloading
 */
export async function checkUv() {
    // Check system PATH
    try {
        const systemUv = await which('uv');
        return { available: true, path: systemUv };
    }
    catch {
        // Not in PATH
    }
    // Check local installation
    const localUv = path.join(getAmbientHome(), 'bin', process.platform === 'win32' ? 'uv.exe' : 'uv');
    if (await fileExists(localUv)) {
        return { available: true, path: localUv };
    }
    return { available: false };
}
/**
 * Get uv version
 */
export async function getUvVersion(uvPath) {
    try {
        const output = execSync(`${uvPath} --version`, { encoding: 'utf-8' });
        return output.trim();
    }
    catch {
        return 'unknown';
    }
}
/**
 * Setup Python environment using uv
 */
export async function setupPythonEnvironment(uvPath, pythonVersion = '3.12') {
    const venvPath = path.join(getAmbientHome(), 'venv');
    // Check if venv already exists
    if (await fileExists(path.join(venvPath, 'bin', 'python'))) {
        console.log(chalk.green('✓ Python environment already exists'));
        return venvPath;
    }
    console.log(chalk.blue(`📦 Creating Python ${pythonVersion} environment...`));
    try {
        // Create virtual environment with specified Python version
        execSync(`${uvPath} venv ${venvPath} --python ${pythonVersion}`, {
            stdio: 'inherit'
        });
        console.log(chalk.green('✓ Python environment created'));
        return venvPath;
    }
    catch (error) {
        throw new Error(`Failed to create Python environment: ${error}`);
    }
}
/**
 * Install Python dependencies using uv
 */
export async function installDependencies(uvPath, venvPath, projectRoot) {
    console.log(chalk.blue('📚 Installing Python dependencies...'));
    try {
        // Use uv pip install to install the project and its dependencies
        execSync(`${uvPath} pip install -e ${projectRoot}`, {
            stdio: 'inherit',
            cwd: projectRoot,
            env: {
                ...process.env,
                VIRTUAL_ENV: venvPath,
                PATH: `${path.join(venvPath, 'bin')}:${process.env.PATH}`
            }
        });
        console.log(chalk.green('✓ Dependencies installed'));
    }
    catch (error) {
        throw new Error(`Failed to install dependencies: ${error}`);
    }
}
