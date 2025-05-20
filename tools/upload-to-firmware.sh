source 'environment.config'
rsync -avh --exclude '*.so' --exclude '__pycache__/' --exclude '*.pyc' --exclude '.vscode/' --exclude 'tools/' --exclude '.git/' --exclude '.github/' --exclude 'build/' --exclude 'dist/' --exclude 'node_modules/' --exclude 'lib/' --exclude 'tests/' ../ linaro@"$device_ip":~/fluxghost
