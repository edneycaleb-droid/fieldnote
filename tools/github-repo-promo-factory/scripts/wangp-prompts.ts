import fs from 'node:fs/promises';import path from 'node:path';import {Command} from 'commander';import {loadPromo,root} from './lib';
const c=new Command().requiredOption('-i, --input <json>');c.parse();const p=await loadPromo(path.resolve(c.opts().input));const prompts=[
`Cinematic macro shot of a futuristic developer workstation representing ${p.repo}, dark graphite surfaces, ${p.accent} accent light, slow controlled dolly-in, volumetric atmosphere, no text, no logos, 16:9`,
`Abstract data streams assembling into a secure autonomous software system, ${p.accent} and deep blue light, smooth orbital camera move, premium technology commercial, no text, 16:9`,
`Glowing network nodes coordinating automatically inside a dark command center, restrained cinematic camera push, realistic reflections, ${p.accent} highlights, no text, 16:9`
];const dir=path.join(root,'out',`${p.owner}-${p.repo}`);await fs.mkdir(dir,{recursive:true});await fs.writeFile(path.join(dir,'wangp-prompts.json'),JSON.stringify({modelRecommendations:['HunyuanVideo-1.5','Wan 2.2 I2V','LTX-2 distilled'],prompts},null,2)+'\n');console.log(path.join(dir,'wangp-prompts.json'));
