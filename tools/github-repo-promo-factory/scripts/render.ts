import fs from 'node:fs/promises';
import path from 'node:path';
import {spawn} from 'node:child_process';
import {Command} from 'commander';
import {loadPromo,root} from './lib';

const program=new Command().requiredOption('-i, --input <json>').option('--skip-gif').option('--quality <n>','18');program.parse();
const o=program.opts<{input:string;skipGif?:boolean;quality:string}>(); const p=await loadPromo(path.resolve(o.input));
const out=path.join(root,'out',`${p.owner}-${p.repo}`);await fs.mkdir(out,{recursive:true});
const run=(args:string[])=>new Promise<void>((resolve,reject)=>{const child=spawn(process.platform==='win32'?'npx.cmd':'npx',args,{cwd:root,stdio:'inherit'});child.on('exit',c=>c===0?resolve():reject(new Error(`Command failed (${c}): npx ${args.join(' ')}`)));});
const props=JSON.stringify(p);
await run(['remotion','render','src/index.ts','PromoLandscape',path.join(out,'promo-landscape.mp4'),'--props',props,'--codec','h264','--crf',o.quality]);
await run(['remotion','render','src/index.ts','PromoVertical',path.join(out,'promo-vertical.mp4'),'--props',props,'--codec','h264','--crf',o.quality]);
if(!o.skipGif) await run(['remotion','render','src/index.ts','PromoGif',path.join(out,'readme.gif'),'--props',props,'--codec','gif']);
await fs.writeFile(path.join(out,'manifest.json'),JSON.stringify({source:p.url,generatedAt:new Date().toISOString(),outputs:['promo-landscape.mp4','promo-vertical.mp4',...(o.skipGif?[]:['readme.gif'])]},null,2)+'\n');
console.log(out);
