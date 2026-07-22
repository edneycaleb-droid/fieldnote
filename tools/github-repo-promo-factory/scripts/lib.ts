import fs from 'node:fs/promises';
import path from 'node:path';
import {PromoSchema, type Promo} from '../src/schema';

export const root=path.resolve(import.meta.dirname,'..');
export const generated=path.join(root,'public','generated');
export const parseRepo=(value:string)=>{
  const clean=value.replace(/^https?:\/\/github\.com\//,'').replace(/\.git$/,'').replace(/^\/+|\/+$/g,'');
  const [owner,repo,...rest]=clean.split('/');
  if(!owner||!repo||rest.length) throw new Error('Use OWNER/REPO or a GitHub repository URL.');
  return {owner,repo};
};
export const loadPromo=async(file:string):Promise<Promo>=>PromoSchema.parse(JSON.parse(await fs.readFile(file,'utf8')));
export const savePromo=async(p:Promo)=>{await fs.mkdir(generated,{recursive:true});const file=path.join(generated,`${p.owner}-${p.repo}.json`);await fs.writeFile(file,JSON.stringify(p,null,2)+'\n');return file;};
export const inputs=(file:string)=>JSON.stringify({});
