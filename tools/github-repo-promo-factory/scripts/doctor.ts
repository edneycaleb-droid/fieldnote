import {spawnSync} from 'node:child_process';
const checks=[['node',['--version']],['npx',['remotion','versions']]] as const;let failed=false;
for(const [cmd,args] of checks){const bin=process.platform==='win32'&&cmd==='npx'?'npx.cmd':cmd;const r=spawnSync(bin,[...args],{encoding:'utf8'});const ok=r.status===0;console.log(`${ok?'PASS':'FAIL'} ${cmd}: ${(r.stdout||r.stderr).trim()}`);failed ||= !ok;}
console.log(`${process.env.GITHUB_TOKEN?'PASS':'INFO'} GITHUB_TOKEN: ${process.env.GITHUB_TOKEN?'configured':'not set; public API only'}`);
console.log(`${process.env.WANGP_API_URL?'PASS':'INFO'} WANGP_API_URL: ${process.env.WANGP_API_URL||'prompt-only mode'}`);if(failed)process.exit(1);
