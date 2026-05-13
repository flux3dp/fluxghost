#!/bin/bash
#cd to script folder
cd $(dirname $0)
cd ..
rm -rf ./fluxghost.tar.gz
STASHED=false
if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$(git ls-files --others --exclude-standard)" ]; then
  git stash -u
  STASHED=true
fi
uv run ./tools/type_hint_remover.py fluxghost
cd ..
tar -zcvf ./fluxghost/fluxghost.tar.gz --exclude="__pycache__" --exclude="lib/" --exclude="tools/" --exclude="dist/" --exclude="build/" --exclude="debug-imgs/" --exclude="tests/" --exclude="test-file/" --exclude="node_modules/" --exclude="*.yml" --exclude="*.spec" --exclude=".git/" --exclude=".github/" --exclude=".vscode/" --exclude=".venv/" --exclude=".claude"  --exclude="*.pyc" --exclude=".DS_Store" --exclude=".certs/" ./fluxghost
cd fluxghost
git reset --hard
if [ "$STASHED" = true ]; then
  git stash pop
fi
