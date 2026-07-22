import {spawn} from 'node:child_process';
import path from 'node:path';
import {Command} from 'commander';
import {root} from './lib';
const program=new Command().requiredOption('-r, --repo <repo>').option('--accent <hex>','#58f6d2').option('--background-video <path>').option('--skip-gif');program.parse();const o=program.opts();
const run=(args:string[],capture=false)=>new Promise<string>((resolve,reject)=>{let output='';const c=spawn(process.execPath,args,{cwd:root,stdio:capture?['inherit','pipe','inherit']:'inherit'});if(capture)c.stdout?.on('data',d=>output+=d);c.on('exit',x=>x===0?resolve(output.trim()):reject(new Error(`Stage failed: ${args[2]}`)));});
const args=['--import','tsx','scripts/ingest.ts','--repo',o.repo,'--accent',o.accent];if(o.backgroundVideo)args.push('--background-video',o.backgroundVideo);const file=(await run(args,true)).split('\n').at(-1)!;const render=['--import','tsx','scripts/render.ts','--input',path.resolve(file)];if(o.skipGif)render.push('--skip-gif');await run(render);
