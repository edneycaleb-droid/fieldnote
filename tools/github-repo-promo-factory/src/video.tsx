import React from 'react';
import {AbsoluteFill, Easing, Img, Sequence, interpolate, staticFile, useCurrentFrame, useVideoConfig} from 'remotion';
import {Video} from '@remotion/media';
import type {Promo} from './schema';

const font = 'Inter, ui-sans-serif, system-ui, sans-serif';
const clamp = {extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};

const Backdrop: React.FC<{accent: string; video?: string}> = ({accent, video}) => {
  const frame = useCurrentFrame();
  return <AbsoluteFill style={{background: '#05080d', overflow: 'hidden'}}>
    {video ? <Video muted loop src={staticFile(video)} style={{width: '100%', height: '100%', objectFit: 'cover', opacity: .24}}/> : null}
    <AbsoluteFill style={{background: `radial-gradient(circle at ${25 + frame / 30}% 20%, ${accent}38, transparent 35%), radial-gradient(circle at 80% 85%, #665cff33, transparent 40%), linear-gradient(145deg,#05080d,#0d1524)`}}/>
    <div style={{position:'absolute', inset:'6%', border:`1px solid ${accent}25`, borderRadius:42}}/>
  </AbsoluteFill>;
};

const Enter: React.FC<React.PropsWithChildren<{delay?: number}>> = ({children, delay=0}) => {
  const frame = useCurrentFrame();
  return <div style={{opacity: interpolate(frame-delay,[0,18],[0,1],{...clamp,easing:Easing.bezier(.16,1,.3,1)}), translate:`0 ${interpolate(frame-delay,[0,22],[70,0],clamp)}px`}}>{children}</div>;
};

const Shell: React.FC<React.PropsWithChildren<{accent:string}>> = ({children,accent}) => {
  const {width,height}=useVideoConfig();
  const vertical=height>width;
  return <AbsoluteFill style={{padding:vertical?'150px 84px':'110px 150px', color:'#f7fbff', fontFamily:font, justifyContent:'center'}}>{children}<div style={{position:'absolute',bottom:vertical?72:52,left:vertical?84:150,fontSize:vertical?28:24,letterSpacing:5,color:accent}}>EDNEYCALEB-DROID • OPEN SOURCE</div></AbsoluteFill>;
};

const Hero: React.FC<Promo> = (p) => <Shell accent={p.accent}><div style={{display:'flex',flexDirection:'column',gap:34,maxWidth:1500}}>
  <Enter><div style={{fontSize:34,letterSpacing:9,color:p.accent}}>GITHUB // FEATURED PROJECT</div></Enter>
  <Enter delay={8}><div style={{fontSize:130,fontWeight:900,lineHeight:.94,letterSpacing:-7,overflowWrap:'anywhere'}}>{p.repo}</div></Enter>
  <Enter delay={16}><div style={{fontSize:48,lineHeight:1.25,color:'#b9c6d8',maxWidth:1350}}>{p.description}</div></Enter>
  <Enter delay={24}><div style={{display:'flex',gap:24,flexWrap:'wrap'}}>{[p.language,...p.topics.slice(0,3)].map(x=><span key={x} style={{fontSize:30,padding:'14px 24px',border:`1px solid ${p.accent}70`,borderRadius:999,color:p.accent}}>{x}</span>)}</div></Enter>
  </div></Shell>;

const Features: React.FC<Promo> = (p) => <Shell accent={p.accent}><div style={{display:'flex',flexDirection:'column',gap:48}}>
  <Enter><div style={{fontSize:82,fontWeight:850}}>Built to ship. Built to last.</div></Enter>
  <div style={{display:'flex',flexDirection:'column',gap:22}}>{p.features.map((x,i)=><Enter key={x} delay={i*8}><div style={{display:'flex',alignItems:'center',gap:28,fontSize:46,fontWeight:650}}><span style={{color:p.accent,fontFamily:'monospace'}}>0{i+1}</span><span>{x}</span></div></Enter>)}</div>
  </div></Shell>;

const Stats: React.FC<Promo> = (p) => <Shell accent={p.accent}><div style={{display:'flex',flexDirection:'column',gap:52}}>
  <Enter><div style={{fontSize:82,fontWeight:850}}>Live repository intelligence</div></Enter>
  <div style={{display:'flex',gap:30,flexWrap:'wrap'}}>{[[p.stars,'STARS'],[p.forks,'FORKS'],[p.openIssues,'OPEN ISSUES']].map(([n,l],i)=><Enter key={String(l)} delay={i*8}><div style={{minWidth:310,padding:'38px 46px',background:'#ffffff0b',border:'1px solid #ffffff1d',borderRadius:28}}><div style={{fontSize:88,fontWeight:900,color:p.accent}}>{n}</div><div style={{fontSize:25,letterSpacing:5,color:'#aeb9c8'}}>{l}</div></div></Enter>)}</div>
  </div></Shell>;

const Final: React.FC<Promo> = (p) => <Shell accent={p.accent}><div style={{display:'flex',flexDirection:'column',gap:38,alignItems:'flex-start'}}>
  <Enter><div style={{fontSize:105,fontWeight:950,lineHeight:1,color:p.accent}}>{p.tagline}</div></Enter>
  <Enter delay={12}><div style={{fontSize:42,color:'#c4cfdd'}}>github.com/{p.owner}/{p.repo}</div></Enter>
  <Enter delay={20}><div style={{fontSize:32,padding:'18px 28px',background:p.accent,color:'#06100e',borderRadius:14,fontWeight:900}}>EXPLORE THE REPOSITORY →</div></Enter>
  </div></Shell>;

export const PromoVideo: React.FC<Promo> = (p) => {
  const {durationInFrames}=useVideoConfig();
  const short=durationInFrames<300;
  return <AbsoluteFill><Backdrop accent={p.accent} video={p.backgroundVideo}/>
    {short ? <><Sequence durationInFrames={90}><Hero {...p}/></Sequence><Sequence from={90} durationInFrames={80}><Features {...p}/></Sequence><Sequence from={170}><Final {...p}/></Sequence></> : <><Sequence durationInFrames={180}><Hero {...p}/></Sequence><Sequence from={180} durationInFrames={180}><Features {...p}/></Sequence><Sequence from={360} durationInFrames={150}><Stats {...p}/></Sequence><Sequence from={510}><Final {...p}/></Sequence></>}
  </AbsoluteFill>;
};
