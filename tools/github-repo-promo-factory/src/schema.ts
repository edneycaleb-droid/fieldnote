import {z} from 'zod';

export const PromoSchema = z.object({
  owner: z.string(),
  repo: z.string(),
  url: z.string().url(),
  description: z.string(),
  stars: z.number().int().nonnegative(),
  forks: z.number().int().nonnegative(),
  openIssues: z.number().int().nonnegative(),
  language: z.string(),
  topics: z.array(z.string()).max(8),
  features: z.array(z.string()).min(3).max(5),
  tagline: z.string(),
  accent: z.string().regex(/^#[0-9a-fA-F]{6}$/),
  backgroundVideo: z.string().optional(),
});

export type Promo = z.infer<typeof PromoSchema>;
