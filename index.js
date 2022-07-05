const core = require('@actions/core');
const exec = require('@actions/exec');
const os = require('os');

const main = async () => {
    try {
        const options = {
            cwd: __dirname,
        };
        console.log(os.platform());
        console.log(os.arch());
        console.log(process.env);
        if (os.platform() === 'win32') {
            if (process.env.WIN_ARCH !== 'x86') {
                await exec.exec('cp', ['./lib/x64/*', 'C:\\Windows\\system32'], options);
            } else {
                await exec.exec('cp', ['./lib/x32/*', 'C:\\Windows\\system32'], options);
            }
            // await exec.exec('python', ['ghost.py', '--test', '--without_pcl'], options);
            await exec.exec('pyinstaller', ['--clean', 'ghost-github-action.spec'], options);
        } else if( os.platform() === 'linux' ) {
            await exec.exec('python3', ['ghost.py', '--test', '--without_pcl'], options);
            await exec.exec('pyinstaller', ['--clean', 'ghost-github-action.spec'], options);
        } else if( os.platform() === 'darwin' ) {
            const pythonVersion = process.env.PYTHON_VERSION || '3.6';
            await exec.exec('python3', ['ghost.py', '--test', '--without_pcl'], options);
            await exec.exec('pyinstaller', ['--clean', 'ghost-github-action.spec'], options);
            await exec.exec('sudo', ['cp', './lib/mac/libwebp.7.dylib', 'dist/flux_api'], options);
            // pyinstaller failed to hook tcl & tk for precomiled python so hard code copy when
            await exec.exec('sudo', ['cp', '-R', `/Library/Frameworks/Python.framework/Versions/${pythonVersion}/lib/tcl8.6`, 'dist/flux_api/tcl/'], options);
            await exec.exec('sudo', ['cp', '-R', `/Library/Frameworks/Python.framework/Versions/${pythonVersion}/lib/tk8.6`, 'dist/flux_api/tk'], options);
        } else {
            throw `Unsupported OS: ${os.platform()}`
        }
        await exec.exec('./dist/flux_api/flux_api', ['--test', '--without_pcl'], options);

        if (os.platform() === 'win32') {
            await exec.exec('mv', ['dist/flux_api', `${process.env.TMP}\\flux_api_swap`], options);
        } else {
            await exec.exec('mv', ['dist/flux_api', `${process.env.HOME}/flux_api_swap`], options);
        }
    } catch (error) {
        core.setFailed(error.message);
    }
}
main();
