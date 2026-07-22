$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
git pull --ff-only
npm install
npm run typecheck
npm test
npm run doctor
