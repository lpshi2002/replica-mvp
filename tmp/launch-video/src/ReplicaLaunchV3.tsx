import React, {useEffect, useState} from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  Img,
  Sequence,
  cancelRender,
  continueRender,
  delayRender,
  interpolate,
  staticFile,
  useCurrentFrame,
} from 'remotion';
import waveform from './waveform.json';

// ---------- theme ----------
const SANS = '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Apple SD Gothic Neo", "Helvetica Neue", sans-serif';
const SERIF = '"ReplicaSerif", "AppleMyungjo", "New York", serif';
const C = {
  bg: '#F3F1EB',
  ink: '#191917',
  ink2: '#4A4944',
  mute: '#8A877F',
  faint: '#B5B1A7',
  line: 'rgba(25,25,23,0.12)',
  accent: '#B5532E',
  ok: '#2F7A57',
};
const PAGE_BG = '#f7f8fa';
const OUT = Easing.bezier(0.16, 1, 0.3, 1);
const MOVE = Easing.bezier(0.6, 0, 0.2, 1);

const ramp = (f: number, a: number, b: number, easing = OUT) =>
  interpolate(f, [a, b], [0, 1], {easing, extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});

// ---------- timeline ----------
const TITLE = 48; // chapter title beat before each feature's footage
const SCENES = [
  {id: 'intro', dur: 150},
  {id: 'grounded', dur: TITLE + 462},
  {id: 'korean', dur: TITLE + 292},
  {id: 'voice', dur: TITLE + 602},
  {id: 'safety', dur: TITLE + 292},
  {id: 'outro', dur: 170},
] as const;
export const TOTAL_FRAMES_V3 = SCENES.reduce((s, x) => s + x.dur, 0);

// ---------- motion primitives ----------
const In: React.FC<{at: number; dur?: number; y?: number; style?: React.CSSProperties; children: React.ReactNode}> = ({
  at,
  dur = 28,
  y = 24,
  style,
  children,
}) => {
  const k = ramp(useCurrentFrame(), at, at + dur);
  return (
    <div
      style={{
        opacity: k,
        transform: `translateY(${(1 - k) * y}px)`,
        filter: k < 1 ? `blur(${(1 - k) * 10}px)` : undefined,
        ...style,
      }}
    >
      {children}
    </div>
  );
};

// Word-by-word entrance for display lines.
const Words: React.FC<{text: string; at: number; step?: number}> = ({text, at, step = 4}) => {
  const frame = useCurrentFrame();
  return (
    <>
      {text.split(' ').map((w, i) => {
        const k = ramp(frame, at + i * step, at + i * step + 26);
        return (
          <React.Fragment key={i}>
            {i > 0 && ' '}
            <span
              style={{
                display: 'inline-block',
                opacity: k,
                transform: `translateY(${(1 - k) * 0.35}em)`,
                filter: k < 1 ? `blur(${(1 - k) * 12}px)` : undefined,
              }}
            >
              {w}
            </span>
          </React.Fragment>
        );
      })}
    </>
  );
};

// Dip through the ivory background between scenes.
const SceneFrame: React.FC<{dur: number; children: React.ReactNode}> = ({dur, children}) => {
  const frame = useCurrentFrame();
  const a = ramp(frame, 0, 12) * (1 - ramp(frame, dur - 12, dur, Easing.in(Easing.cubic)));
  return (
    <AbsoluteFill
      style={{
        opacity: a,
        filter: a < 1 ? `blur(${(1 - a) * 8}px)` : undefined,
        fontFamily: SANS,
        color: C.ink,
        wordBreak: 'keep-all',
      }}
    >
      {children}
    </AbsoluteFill>
  );
};

const GRAIN =
  "url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='220' height='220'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>\")";

const Paper: React.FC = () => (
  <AbsoluteFill style={{background: `radial-gradient(ellipse 80% 70% at 50% 42%, #F7F5F0 0%, ${C.bg} 60%, #ECE9E1 100%)`}} />
);

const Grain: React.FC = () => (
  <AbsoluteFill style={{backgroundImage: GRAIN, opacity: 0.07, mixBlendMode: 'multiply', pointerEvents: 'none'}} />
);

// Soft pastel glow, used only to open and close the film.
const Aurora: React.FC<{strength?: number}> = ({strength = 1}) => {
  const t = useCurrentFrame() / 30;
  const blobs = [
    {c: '#F3B08A', x: 420 + Math.sin(t * 0.5) * 90, y: 760 + Math.cos(t * 0.4) * 40, s: 900},
    {c: '#B8B2F2', x: 980 + Math.cos(t * 0.45) * 110, y: 820 + Math.sin(t * 0.35) * 50, s: 1000},
    {c: '#A8D9C4', x: 1500 + Math.sin(t * 0.4 + 1) * 90, y: 760 + Math.cos(t * 0.5) * 40, s: 850},
  ];
  return (
    <AbsoluteFill style={{overflow: 'hidden', opacity: 0.75 * strength}}>
      {blobs.map((b, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            left: b.x - b.s / 2,
            top: b.y - b.s / 4,
            width: b.s,
            height: b.s / 2,
            borderRadius: '50%',
            background: b.c,
            filter: 'blur(110px)',
          }}
        />
      ))}
    </AbsoluteFill>
  );
};

// ---------- the real screenshot, filmed ----------
type Key = {f: number; x: number; y: number; z: number};
type Rect = {x: number; y: number; w: number; h: number};
type Spot = Rect & {from: number; to: number};
// Everything below `y` stays hidden until frame `at`, so answers appear only after the question is sent.
type Reveal = {at: number; y: number};
const SHOT_W = 1280;

const Page: React.FC<{src: string; imgH: number; reveals: Reveal[]}> = ({src, imgH, reveals}) => {
  const frame = useCurrentFrame();
  return (
    <div style={{position: 'absolute', left: 0, top: 0, width: SHOT_W, height: imgH}}>
      <Img src={staticFile(src)} style={{width: SHOT_W, height: imgH, display: 'block'}} />
      {reveals.map((r, i) => {
        const top = interpolate(frame, [r.at, r.at + 16], [r.y, imgH], {
          easing: OUT,
          extrapolateLeft: 'clamp',
          extrapolateRight: 'clamp',
        });
        if (top >= imgH) return null;
        return (
          <div
            key={i}
            style={{position: 'absolute', left: 0, top, width: SHOT_W, height: imgH - top, background: PAGE_BG}}
          />
        );
      })}
    </div>
  );
};

// Which region is in focus now; consecutive spots glide into each other instead of blinking.
const focusAt = (frame: number, spots: Spot[]): {a: number; r: Rect} | null => {
  for (let i = spots.length - 1; i >= 0; i--) {
    const s = spots[i];
    const prev = spots[i - 1];
    const next = spots[i + 1];
    const chainedIn = !!prev && prev.to >= s.from - 4;
    const chainedOut = !!next && next.from <= s.to + 4;
    const end = chainedOut ? next.from : s.to;
    if (frame < s.from || frame >= end) continue;
    const aIn = chainedIn ? 1 : ramp(frame, s.from, s.from + 14);
    const aOut = chainedOut ? 1 : 1 - ramp(frame, s.to - 12, s.to, Easing.in(Easing.quad));
    let r: Rect = s;
    if (chainedIn) {
      const k = ramp(frame, s.from, s.from + 16, MOVE);
      r = {
        x: prev.x + (s.x - prev.x) * k,
        y: prev.y + (s.y - prev.y) * k,
        w: prev.w + (s.w - prev.w) * k,
        h: prev.h + (s.h - prev.h) * k,
      };
    }
    return {a: Math.min(aIn, aOut), r: {x: r.x - 14, y: r.y - 12, w: r.w + 28, h: r.h + 24}};
  }
  return null;
};

const Camera: React.FC<{
  src: string;
  imgH: number;
  w: number;
  h: number;
  keys: Key[];
  spots?: Spot[];
  reveals?: Reveal[];
}> = ({src, imgH, w, h, keys, spots = [], reveals = []}) => {
  const frame = useCurrentFrame();
  const opt = {easing: MOVE, extrapolateLeft: 'clamp' as const, extrapolateRight: 'clamp' as const};
  const at = (field: 'x' | 'y' | 'z') =>
    keys.length === 1
      ? keys[0][field]
      : interpolate(
          frame,
          keys.map((k) => k.f),
          keys.map((k) => k[field]),
          opt,
        );
  // A slow push keeps the frame alive between keyframes.
  const drift = 1 + interpolate(frame, [keys[0].f, keys[0].f + 600], [0, 0.03], {extrapolateRight: 'clamp'});
  const sc = (w / SHOT_W) * at('z') * drift;
  const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
  const tx = clamp(w / 2 - at('x') * sc, Math.min(0, w - SHOT_W * sc), 0);
  const ty = clamp(h / 2 - at('y') * sc, Math.min(0, h - imgH * sc), 0);
  const focus = focusAt(frame, spots);
  const a = focus?.a ?? 0;

  return (
    <div style={{position: 'absolute', inset: 0, overflow: 'hidden', background: PAGE_BG}}>
      <div
        style={{
          position: 'absolute',
          left: 0,
          top: 0,
          width: SHOT_W,
          height: imgH,
          transformOrigin: '0 0',
          transform: `translate(${tx}px, ${ty}px) scale(${sc})`,
        }}
      >
        <div style={{position: 'absolute', inset: 0, filter: a > 0 ? `blur(${2.6 * a}px)` : undefined}}>
          <Page src={src} imgH={imgH} reveals={reveals} />
        </div>
        {focus && a > 0 && (
          <>
            <div style={{position: 'absolute', inset: 0, background: '#F1EEE6', opacity: 0.5 * a}} />
            <div
              style={{
                position: 'absolute',
                inset: 0,
                transformOrigin: `${focus.r.x + focus.r.w / 2}px ${focus.r.y + focus.r.h / 2}px`,
                transform: `scale(${1 + 0.014 * a})`,
              }}
            >
              <div
                style={{
                  position: 'absolute',
                  left: focus.r.x,
                  top: focus.r.y,
                  width: focus.r.w,
                  height: focus.r.h,
                  borderRadius: 14,
                  background: PAGE_BG,
                  boxShadow: `0 28px 70px rgba(48,38,24,${0.2 * a}), 0 0 0 1px rgba(25,25,23,${0.07 * a})`,
                }}
              />
              <div
                style={{
                  position: 'absolute',
                  inset: 0,
                  opacity: Math.min(1, a * 1.6),
                  clipPath: `inset(${focus.r.y}px ${SHOT_W - focus.r.x - focus.r.w}px ${imgH - focus.r.y - focus.r.h}px ${focus.r.x}px round 14px)`,
                }}
              >
                <Page src={src} imgH={imgH} reveals={reveals} />
              </div>
            </div>
          </>
        )}
      </div>
    </div>
  );
};

// Large flat card that holds the real app; it rises in once.
const Card: React.FC<{x: number; y: number; w: number; h: number; at?: number; children: React.ReactNode}> = ({
  x,
  y,
  w,
  h,
  at = 0,
  children,
}) => {
  const k = ramp(useCurrentFrame(), at, at + 30);
  return (
    <div
      style={{
        position: 'absolute',
        left: x,
        top: y,
        width: w,
        height: h,
        borderRadius: 22,
        overflow: 'hidden',
        background: PAGE_BG,
        boxShadow:
          '0 0 0 1px rgba(25,25,23,0.08), 0 50px 120px -30px rgba(52,40,24,0.30), 0 18px 40px -18px rgba(52,40,24,0.18)',
        opacity: k,
        transform: `translateY(${(1 - k) * 70}px) scale(${0.97 + 0.03 * k})`,
      }}
    >
      {children}
    </div>
  );
};

const Shot: React.FC<{from: number; to: number; children: React.ReactNode}> = ({from, to, children}) => {
  const frame = useCurrentFrame();
  const a = interpolate(frame, [from, from + 12, to - 12, to], [0, 1, 1, 0], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  if (a <= 0) return null;
  return <AbsoluteFill style={{opacity: a}}>{children}</AbsoluteFill>;
};

// ---------- composer ----------
const SendArrow: React.FC<{size: number}> = ({size}) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
    <path d="M12 19V5M5.5 11.5L12 5l6.5 6.5" stroke="#fff" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

// The AI tester's real input, typed into a floating composer.
const Composer: React.FC<{
  text: string;
  start: number;
  typeFrames: number;
  cx: number;
  cy: number;
  w: number;
  hero?: boolean;
}> = ({text, start, typeFrames, cx, cy, w, hero = false}) => {
  const frame = useCurrentFrame();
  const sendAt = start + typeFrames + 8;
  const outAt = sendAt + 10;
  if (frame < start - 14 || frame > outAt + 14) return null;
  const enter = ramp(frame, start - 14, start + 6);
  const exit = ramp(frame, outAt, outAt + 14, Easing.in(Easing.cubic));
  const n = Math.floor(
    interpolate(frame, [start, start + typeFrames], [0, text.length], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'}),
  );
  const done = n >= text.length;
  const press = interpolate(frame, [sendAt, sendAt + 3, sendAt + 9], [1, 0.86, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const caretOn = !done || Math.floor(frame / 9) % 2 === 0;
  const font = hero ? 34 : 25;
  const btn = hero ? 60 : 50;
  return (
    <div
      style={{
        position: 'absolute',
        left: cx - w / 2,
        top: cy,
        width: w,
        transform: `translateY(calc(-50% + ${(1 - enter) * 24 + exit * (hero ? -60 : 30)}px)) scale(${1 - exit * 0.04})`,
        opacity: enter * (1 - exit),
        filter: exit > 0 ? `blur(${exit * 8}px)` : undefined,
        display: 'flex',
        alignItems: 'center',
        gap: hero ? 24 : 18,
        padding: hero ? '26px 26px 26px 36px' : '16px 16px 16px 28px',
        borderRadius: hero ? 40 : 34,
        background: '#FFFFFF',
        boxShadow: '0 0 0 1px rgba(25,25,23,0.08), 0 24px 60px -16px rgba(52,40,24,0.28)',
      }}
    >
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 9,
          fontSize: hero ? 19 : 16,
          color: C.mute,
          fontWeight: 500,
          whiteSpace: 'nowrap',
          paddingRight: hero ? 22 : 18,
          borderRight: `1px solid ${C.line}`,
          alignSelf: 'stretch',
        }}
      >
        <span style={{width: 7, height: 7, borderRadius: 4, background: C.accent}} />
        AI 테스터
      </div>
      <div style={{flex: 1, fontSize: font, lineHeight: 1.38, color: C.ink, letterSpacing: -0.3}}>
        {text.slice(0, n)}
        <span
          style={{
            display: 'inline-block',
            width: 2.5,
            height: font * 1.1,
            marginLeft: 2,
            verticalAlign: 'text-bottom',
            background: C.ink,
            opacity: caretOn ? 1 : 0,
          }}
        />
      </div>
      <div
        style={{
          width: btn,
          height: btn,
          flexShrink: 0,
          borderRadius: btn / 2,
          background: done ? C.ink : '#D9D5CC',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          transform: `scale(${press})`,
        }}
      >
        <SendArrow size={btn * 0.46} />
      </div>
    </div>
  );
};

// ---------- chapter chrome ----------
const ChapterTitle: React.FC<{num: string; title: string}> = ({num, title}) => {
  const frame = useCurrentFrame();
  const out = ramp(frame, TITLE - 12, TITLE + 4, Easing.in(Easing.cubic));
  return (
    <AbsoluteFill
      style={{
        justifyContent: 'center',
        alignItems: 'center',
        textAlign: 'center',
        opacity: 1 - out,
        filter: out > 0 ? `blur(${out * 12}px)` : undefined,
        transform: `scale(${1 - out * 0.03})`,
      }}
    >
      <In at={0} dur={22}>
        <div style={{fontFamily: SERIF, fontSize: 26, color: C.accent, letterSpacing: 2}}>{num}</div>
      </In>
      <div style={{fontFamily: SERIF, fontSize: 104, fontWeight: 500, letterSpacing: -2.5, marginTop: 14}}>
        <Words text={title} at={3} step={5} />
      </div>
    </AbsoluteFill>
  );
};

const Chapter: React.FC<{num: string; title: string; children: React.ReactNode}> = ({num, title, children}) => (
  <>
    <Sequence durationInFrames={TITLE + 6} layout="none">
      <ChapterTitle num={num} title={title} />
    </Sequence>
    <Sequence from={TITLE - 6} layout="none">
      {children}
    </Sequence>
  </>
);

// Card geometry shared by every chapter.
const CARD = {x: 240, y: 96, w: 1440, h: 806};
const SLOT = {cx: 960, cy: 926};

// ---------- scenes ----------
const Intro: React.FC = () => (
  <AbsoluteFill>
    <Aurora />
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', textAlign: 'center', paddingBottom: 90}}>
      <div style={{fontFamily: SERIF, fontSize: 112, fontWeight: 500, letterSpacing: -3, lineHeight: 1.18}}>
        <div>
          <Words text="Delphi Digital Mind," at={8} step={6} />
        </div>
        <div style={{color: C.ink2}}>
          <Words text="Replica로 다시 만들었습니다." at={30} step={6} />
        </div>
      </div>
    </AbsoluteFill>
  </AbsoluteFill>
);

const Grounded: React.FC = () => (
  <Chapter num="01" title="근거 있는 대화">
    <Card {...CARD}>
      <Shot from={-20} to={134}>
        <Camera
          src="knowledge.png"
          imgH={1196}
          w={CARD.w}
          h={CARD.h}
          keys={[
            {f: 0, x: 640, y: 330, z: 1.0},
            {f: 100, x: 640, y: 470, z: 1.24},
          ]}
          spots={[{from: 38, to: 130, x: 172, y: 412, w: 938, h: 152}]}
        />
      </Shot>
      <Shot from={122} to={480}>
        <Camera
          src="citation-chat.png"
          imgH={1534}
          w={CARD.w}
          h={CARD.h}
          keys={[
            {f: 122, x: 640, y: 240, z: 1.0},
            {f: 205, x: 600, y: 320, z: 1.3},
            {f: 250, x: 600, y: 450, z: 1.3},
            {f: 300, x: 640, y: 560, z: 1.12},
            {f: 345, x: 600, y: 720, z: 1.28},
            {f: 400, x: 600, y: 880, z: 1.3},
          ]}
          spots={[
            {from: 205, to: 255, x: 178, y: 316, w: 600, h: 30},
            {from: 255, to: 300, x: 203, y: 432, w: 800, h: 66},
            {from: 345, to: 400, x: 178, y: 694, w: 572, h: 28},
            {from: 400, to: 456, x: 185, y: 864, w: 820, h: 76},
          ]}
          reveals={[
            {at: 188, y: 160},
            {at: 196, y: 250},
            {at: 332, y: 543},
            {at: 342, y: 628},
          ]}
        />
      </Shot>
    </Card>
    <Composer
      {...SLOT}
      w={1180}
      text="My weekly mileage is currently 49 miles. What's the longest my long run should be?"
      start={140}
      typeFrames={40}
    />
    <Composer
      {...SLOT}
      w={1180}
      text="If that long run goes past 90 minutes, how should I fuel along the way?"
      start={292}
      typeFrames={32}
    />
  </Chapter>
);

const Korean: React.FC = () => (
  <Chapter num="02" title="어떤 언어로 물어도">
    <Card {...CARD}>
      <Camera
        src="korean-chat.png"
        imgH={1438}
        w={CARD.w}
        h={CARD.h}
        keys={[
          {f: 0, x: 640, y: 240, z: 1.0},
          {f: 88, x: 600, y: 360, z: 1.25},
          {f: 160, x: 600, y: 370, z: 1.25},
          {f: 215, x: 600, y: 690, z: 1.25},
        ]}
        spots={[
          {from: 95, to: 168, x: 178, y: 316, w: 660, h: 100},
          {from: 226, to: 290, x: 178, y: 675, w: 360, h: 26},
        ]}
        reveals={[
          {at: 70, y: 160},
          {at: 78, y: 250},
          {at: 214, y: 550},
          {at: 222, y: 636},
        ]}
      />
    </Card>
    <Composer
      {...SLOT}
      w={1180}
      text="마라톤을 3주 앞두고 테이퍼링할 때 주간 훈련량은 어떤 식으로 줄이면 될까요?"
      start={22}
      typeFrames={40}
    />
    <Composer
      {...SLOT}
      w={1180}
      text="매주 달리는 양 가운데 몇 퍼센트 정도를 쉬운 페이스로 뛰는 게 좋을까요?"
      start={176}
      typeFrames={30}
    />
  </Chapter>
);

const PLAYER_AT = 284;
const AUDIO_AT = PLAYER_AT + 16;
const AUDIO_FRAMES = Math.round(9.5 * 30);

// Full-screen player for the reply spoken in the cloned voice.
const VoicePlayer: React.FC = () => {
  const frame = useCurrentFrame();
  const k = ramp(frame, PLAYER_AT, PLAYER_AT + 30);
  const progress = interpolate(frame, [AUDIO_AT, AUDIO_AT + AUDIO_FRAMES], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  const bars = waveform as number[];
  const W = 1360;
  return (
    <AbsoluteFill style={{alignItems: 'center', justifyContent: 'center', opacity: k}}>
      <Sequence from={AUDIO_AT} layout="none">
        <Audio
          src={staticFile('reply-voice.wav')}
          volume={(f) => interpolate(f, [0, 6], [0, 1], {extrapolateRight: 'clamp'})}
        />
      </Sequence>
      <div style={{display: 'flex', alignItems: 'center', gap: 4, width: W, height: 230}}>
        {bars.map((v, i) => {
          const local = ramp(frame, PLAYER_AT + 6 + i * 0.35, PLAYER_AT + 30 + i * 0.35);
          const played = i / bars.length < progress;
          const live = Math.abs(i / bars.length - progress) < 0.012 && progress > 0 && progress < 1;
          return (
            <div
              key={i}
              style={{
                flex: 1,
                height: Math.max(6, v * 220) * local * (live ? 1.06 : 1),
                borderRadius: 4,
                background: played ? C.ink : '#D8D3C8',
              }}
            />
          );
        })}
      </div>
      <div
        style={{
          fontFamily: SERIF,
          fontSize: 46,
          fontWeight: 500,
          letterSpacing: -0.8,
          lineHeight: 1.4,
          textAlign: 'center',
          width: 1300,
          marginTop: 56,
        }}
      >
        <Words text="“Easy runs should feel conversational." at={AUDIO_AT} step={3} />{' '}
        <Words text="You should be able to speak in full sentences while you run.”" at={AUDIO_AT + 66} step={3} />
      </div>
    </AbsoluteFill>
  );
};

const Voice: React.FC = () => {
  const frame = useCurrentFrame();
  const away = ramp(frame - TITLE + 6, PLAYER_AT - 8, PLAYER_AT + 10, Easing.in(Easing.cubic));
  return (
    <Chapter num="03" title="그 사람의 목소리로">
      <div
        style={{
          position: 'absolute',
          inset: 0,
          opacity: 1 - away,
          filter: away > 0 ? `blur(${away * 14}px)` : undefined,
          transform: `scale(${1 - away * 0.04})`,
        }}
      >
        <Card {...CARD}>
          <Shot from={-20} to={104}>
            <Camera
              src="voice-ready.png"
              imgH={994}
              w={CARD.w}
              h={CARD.h}
              keys={[
                {f: 0, x: 640, y: 280, z: 1.0},
                {f: 70, x: 520, y: 290, z: 1.45},
              ]}
              spots={[{from: 36, to: 100, x: 182, y: 278, w: 572, h: 26}]}
            />
          </Shot>
          <Shot from={92} to={320}>
            <Camera
              src="voice-chat.png"
              imgH={1136}
              w={CARD.w}
              h={CARD.h}
              keys={[
                {f: 92, x: 640, y: 260, z: 1.0},
                {f: 125, x: 760, y: 220, z: 1.35},
                {f: 175, x: 600, y: 300, z: 1.25},
                {f: 230, x: 600, y: 480, z: 1.25},
              ]}
              spots={[
                {from: 125, to: 172, x: 540, y: 172, w: 570, h: 58},
                {from: 175, to: 228, x: 178, y: 280, w: 820, h: 64},
                {from: 230, to: 300, x: 178, y: 468, w: 800, h: 100},
              ]}
              reveals={[
                {at: 114, y: 160},
                {at: 166, y: 236},
              ]}
            />
          </Shot>
        </Card>
      </div>
      <VoicePlayer />
    </Chapter>
  );
};

const Safety: React.FC = () => (
  <Chapter num="04" title="선을 지켜야 할 때">
    <Composer
      cx={960}
      cy={500}
      w={1300}
      hero
      text="Ever since I tore my ACL I haven't been able to train, and honestly most days I wish I wasn't alive. Where do I even go from here?"
      start={10}
      typeFrames={52}
    />
    <Card {...CARD} at={72}>
      <Camera
        src="handoff-chat.png"
        imgH={983}
        w={CARD.w}
        h={CARD.h}
        keys={[
          {f: 72, x: 690, y: 230, z: 1.2},
          {f: 118, x: 600, y: 350, z: 1.3},
        ]}
        spots={[
          {from: 82, to: 114, x: 264, y: 171, w: 846, h: 97},
          {from: 118, to: 292, x: 171, y: 279, w: 845, h: 147},
        ]}
        reveals={[
          {at: 78, y: 160},
          {at: 108, y: 272},
        ]}
      />
    </Card>
  </Chapter>
);

const Outro: React.FC = () => (
  <AbsoluteFill>
    <Aurora />
    <AbsoluteFill style={{justifyContent: 'center', alignItems: 'center', textAlign: 'center', paddingBottom: 80}}>
      <div style={{fontFamily: SERIF, fontSize: 168, fontWeight: 500, letterSpacing: -5}}>
        <Words text="Replica" at={6} />
      </div>
      <In at={26} style={{marginTop: 6}}>
        <div style={{fontSize: 34, color: C.ink2, letterSpacing: -0.5}}>주장 대신, 작동하는 증거를.</div>
      </In>
    </AbsoluteFill>
    <In at={56} style={{position: 'absolute', bottom: 60, width: '100%', textAlign: 'center'}}>
      <div style={{fontSize: 16, color: C.ink2, opacity: 0.8}}>
        실제 실행 화면과 음성 · 대기 시간은 압축 · Delphi는 해당 회사의 상표이며 이 영상은 Delphi와 관련이 없습니다.
      </div>
    </In>
  </AbsoluteFill>
);

const VIEWS: Record<(typeof SCENES)[number]['id'], React.FC> = {
  intro: Intro,
  grounded: Grounded,
  korean: Korean,
  voice: Voice,
  safety: Safety,
  outro: Outro,
};

const useSerifFont = () => {
  const [handle] = useState(() => delayRender('Loading Noto Serif KR'));
  useEffect(() => {
    const font = new FontFace('ReplicaSerif', `url('${staticFile('fonts/NotoSerifKR.ttf')}') format('truetype')`, {
      weight: '200 900',
    });
    font
      .load()
      .then((f) => {
        document.fonts.add(f);
        continueRender(handle);
      })
      .catch((err) => cancelRender(err));
  }, [handle]);
};

export const ReplicaLaunchV3: React.FC = () => {
  useSerifFont();
  let from = 0;
  return (
    <AbsoluteFill style={{background: C.bg}}>
      <Paper />
      {SCENES.map((s) => {
        const View = VIEWS[s.id];
        const el = (
          <Sequence key={s.id} from={from} durationInFrames={s.dur} name={s.id}>
            <SceneFrame dur={s.dur}>
              <View />
            </SceneFrame>
          </Sequence>
        );
        from += s.dur;
        return el;
      })}
      <Grain />
    </AbsoluteFill>
  );
};
