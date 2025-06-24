source 'environment.config'
rsync -avh --exclude '*.so' --exclude '__pycache__/' --exclude '*.pyc' --exclude '.vscode/' --exclude 'tools/' --exclude '.git/' --exclude '.github/' --exclude 'build/' --exclude 'dist/' --exclude 'node_modules/' --exclude 'lib/' --exclude '.venv/' --exclude 'tests/' ../ pi@"$device_ip":~/fluxghost
