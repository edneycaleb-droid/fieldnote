import {Composition} from 'remotion';
import {PromoVideo} from './video';
import defaultPromo from './default-promo.json';
import {PromoSchema} from './schema';

export const RemotionRoot = () => (
  <>
    <Composition id="PromoLandscape" component={PromoVideo} durationInFrames={720} fps={30} width={1920} height={1080} schema={PromoSchema} defaultProps={defaultPromo}/>
    <Composition id="PromoVertical" component={PromoVideo} durationInFrames={720} fps={30} width={1080} height={1920} schema={PromoSchema} defaultProps={defaultPromo}/>
    <Composition id="PromoGif" component={PromoVideo} durationInFrames={240} fps={20} width={960} height={540} schema={PromoSchema} defaultProps={defaultPromo}/>
  </>
);
