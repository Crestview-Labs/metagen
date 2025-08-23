/**
 * Setup command - Initialize Ambient environment
 */
import { Command } from 'commander';
import chalk from 'chalk';
import ora from 'ora';
import { ensureUv, setupPythonEnvironment, installDependencies, checkUv, getUvVersion } from '../utils/uv.js';
import { getProjectRoot, fileExists } from '../utils/paths.js';
import path from 'path';
export const setupCommand = new Command('setup')
    .description('Setup Ambient environment (Python, dependencies, etc.)')
    .option('--python <version>', 'Python version to use', '3.12')
    .option('--force', 'Force reinstall even if already setup')
    .action(async (options) => {
    console.log(chalk.blue.bold('🚀 Ambient Setup'));
    console.log();
    const spinner = ora();
    try {
        // Step 1: Check/Install uv
        spinner.start('Checking for uv package manager...');
        const uvCheck = await checkUv();
        if (uvCheck.available && !options.force) {
            spinner.succeed(`uv found at ${uvCheck.path}`);
        }
        else {
            spinner.text = 'Installing uv package manager...';
            const uvPath = await ensureUv();
            spinner.succeed(`uv installed at ${uvPath}`);
            // Show version
            const version = await getUvVersion(uvPath);
            console.log(chalk.gray(`  Version: ${version}`));
        }
        // Get uv path for next steps
        const uvPath = await ensureUv();
        // Step 2: Setup Python environment
        spinner.start(`Setting up Python ${options.python} environment...`);
        const venvPath = await setupPythonEnvironment(uvPath, options.python);
        spinner.succeed(`Python environment created at ${venvPath}`);
        // Step 3: Install backend dependencies
        spinner.start('Installing backend dependencies...');
        const projectRoot = getProjectRoot();
        const pyprojectPath = path.join(projectRoot, 'pyproject.toml');
        if (!await fileExists(pyprojectPath)) {
            spinner.fail('pyproject.toml not found');
            console.error(chalk.red(`Expected at: ${pyprojectPath}`));
            process.exit(1);
        }
        await installDependencies(uvPath, venvPath, projectRoot);
        spinner.succeed('Dependencies installed');
        // Step 4: Verify setup
        spinner.start('Verifying setup...');
        const pythonPath = path.join(venvPath, 'bin', 'python');
        if (await fileExists(pythonPath)) {
            spinner.succeed('Setup complete!');
            console.log();
            console.log(chalk.green.bold('✅ Ambient is ready to use!'));
            console.log();
            console.log(chalk.gray('Run `ambient` to start the CLI'));
            console.log(chalk.gray('Run `ambient server` to manage the backend'));
        }
        else {
            spinner.fail('Setup verification failed');
            process.exit(1);
        }
    }
    catch (error) {
        spinner.fail('Setup failed');
        console.error(chalk.red('Error:'), error);
        if (error instanceof Error && error.message.includes('You can install it manually')) {
            console.log();
            console.log(chalk.yellow('Manual installation instructions:'));
            console.log(error.message);
        }
        process.exit(1);
    }
});
// Convenience function to check if setup is needed
export async function checkSetup() {
    const uvCheck = await checkUv();
    if (!uvCheck.available) {
        return false;
    }
    const venvPath = path.join(getProjectRoot(), '.ambient', 'venv');
    const pythonPath = path.join(venvPath, 'bin', 'python');
    return await fileExists(pythonPath);
}
// Prompt user to run setup if needed
export async function promptSetup() {
    if (await checkSetup()) {
        return;
    }
    console.log(chalk.yellow('⚠️  Ambient environment not set up'));
    console.log();
    console.log('Run the following command to set up:');
    console.log(chalk.cyan('  ambient setup'));
    console.log();
    console.log('This will:');
    console.log('  • Install uv package manager');
    console.log('  • Create Python 3.12 environment');
    console.log('  • Install backend dependencies');
    process.exit(1);
}
