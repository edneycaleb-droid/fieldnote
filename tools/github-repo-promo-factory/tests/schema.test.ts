import {describe,expect,it} from 'vitest';
import {PromoSchema} from '../src/schema';
import defaultPromo from '../src/default-promo.json';
describe('promo schema',()=>{it('accepts the bundled demo',()=>expect(PromoSchema.parse(defaultPromo).repo).toBe('fieldnote'));it('rejects unsafe accents',()=>expect(()=>PromoSchema.parse({...defaultPromo,accent:'red'})).toThrow());});
