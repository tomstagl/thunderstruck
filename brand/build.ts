#!/usr/bin/env tsx
// thunderstruck's brand, built the way cctop's is: one hand-drawn mark, the wordmark outlined
// from IBM Plex Sans Condensed Bold, every raster rendered from the SVG. Run from studio-master
// (for fontkit + sharp):
//   cd ../studio-master && NODE_PATH=$PWD/node_modules ./node_modules/.bin/tsx ../thunderstruck/brand/build.ts
//
// The mark, "past the limit": an amplifier's level meter whose needle is a lightning bolt, pegged
// past the red zone, pivoting on Claude's spark. The tool's function (where load pushes code past
// what it was built to take) fused with its name (a strike of lightning, a dial turned past its
// limit), in Claude terracotta. Original geometry only, and no copy of Anthropic's mark.
import { writeFileSync, mkdirSync, readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import fontkit from 'fontkit';
import sharp from 'sharp';

const ROOT = dirname(fileURLToPath(import.meta.url));
const SVG = join(ROOT, 'svg'), PNG = join(ROOT, 'png');
mkdirSync(SVG, { recursive: true });
mkdirSync(PNG, { recursive: true });

// ---- palette, shared with cctop so the two read as one family
const TERRA = '#D97757', INK_MARK = '#111111', ON_DARK = '#D6DEE8', CHAR = '#0E1318', PAPER = '#F1F3F6', INK = '#1A212C', MUTED = '#8B95A7';

// ---- primitives
const f = (n: number) => n.toFixed(1);
const poly = (pts: number[][]) => 'M' + pts.map(([x, y]) => `${f(x)} ${f(y)}`).join(' L') + ' Z';
// a warm burst of round-capped rays: Claude's visual language, original geometry
function burst(cx: number, cy: number, ri: number, lens: number[], w: number, color: string, rot: number): string {
  let d = '';
  lens.forEach((len, k) => {
    if (!len) return;
    const a = ((rot + (k * 360) / lens.length) * Math.PI) / 180;
    d += `M${f(cx + ri * Math.cos(a))} ${f(cy + ri * Math.sin(a))} L${f(cx + len * Math.cos(a))} ${f(cy + len * Math.sin(a))} `;
  });
  const rays = d ? `<path d="${d.trim()}" stroke="${color}" stroke-width="${w}" stroke-linecap="round" fill="none"/>` : '';
  return `<circle cx="${f(cx)}" cy="${f(cy)}" r="${f(ri + w / 2)}" fill="${color}"/>${rays}`;
}

// ---- the mark
type Ink = { mark: string; terra: string };
type Gauge = { P: number[]; ticks: number[]; red: number; r: number[]; rr: number[]; w: number; bolt: number[][]; hub: [number, number[], number]; needle: number };
function gauge(c: Ink, g: Gauge): string {
  const ray = (a: number, r0: number, r1: number) => {
    const t = (a * Math.PI) / 180;
    return `M${f(g.P[0] + r0 * Math.cos(t))} ${f(g.P[1] + r0 * Math.sin(t))} L${f(g.P[0] + r1 * Math.cos(t))} ${f(g.P[1] + r1 * Math.sin(t))}`;
  };
  const cool = g.ticks.slice(0, g.ticks.length - g.red).map((a) => ray(a, g.r[0], g.r[1])).join(' ');
  const hot = g.ticks.slice(g.ticks.length - g.red).map((a) => ray(a, g.rr[0], g.rr[1])).join(' ');
  return `
  <path d="${cool}" stroke="${c.mark}" stroke-width="${g.w}" stroke-linecap="round" fill="none"/>${hot ? `
  <path d="${hot}" stroke="${c.terra}" stroke-width="${g.w}" stroke-linecap="round" fill="none"/>` : ''}
  <path fill="${c.terra}" transform="translate(${g.P[0]} ${g.P[1]}) rotate(${g.needle - 90})" d="${poly(g.bolt)}"/>
  ${burst(g.P[0], g.P[1], g.hub[0], g.hub[1], g.hub[2], c.terra, g.needle)}`;
}
// the needle is drawn pointing down (+y) from the pivot and rotated onto the needle angle
const MARK: Gauge = {
  P: [114, 162], ticks: [-180, -160, -140, -120, -100, -80, -60, -40], red: 2, r: [74, 100], rr: [64, 104], w: 12,
  bolt: [[6, 28], [-14, 68], [4, 68], [-8, 124], [26, 54], [9, 54], [22, 28]],
  hub: [9, [0, 24, 18, 24, 18, 24, 18, 24], 10], needle: -10, // pegged past the last tick
};
// simplified for 16 px: three thick ticks on a quarter arc, a chunky needle angled up past them, a solid hub
const FAV: Gauge = {
  P: [33, 50], ticks: [-180, -135, -90], red: 0, r: [17, 29], rr: [0, 0], w: 7,
  bolt: [[0, 4], [-9, 20], [1, 20], [-3, 33], [12, 13], [4, 13], [9, 4]],
  hub: [3, [0, 0, 0, 0, 0, 0, 0, 0], 6], needle: -30,
};
const LIGHT: Ink = { mark: INK_MARK, terra: TERRA }, DARK: Ink = { mark: ON_DARK, terra: TERRA }, MONO: Ink = { mark: 'currentColor', terra: 'currentColor' };
const markBody = (c: Ink = LIGHT) => gauge(c, MARK);

// ---- wordmark outlines (IBM Plex, SIL OFL), so no SVG depends on an installed font
const font = fontkit.openSync(join(ROOT, 'fonts/PlexSansCondensed-Bold.ttf')) as any;
const mono = fontkit.openSync(join(ROOT, 'fonts/PlexMono-Medium.ttf')) as any;
function outline(fnt: any, text: string, size: number) {
  const run = fnt.layout(text); const s = size / fnt.unitsPerEm; let x = 0; const parts: string[] = [];
  for (let i = 0; i < run.glyphs.length; i++) {
    parts.push(run.glyphs[i].path.scale(s, -s).translate(x + run.positions[i].xOffset * s, 0).toSVG());
    x += run.positions[i].xAdvance * s;
  }
  return { d: parts.join(' '), width: x, ascent: fnt.ascent * s, capHeight: (fnt.capHeight || fnt.ascent * 0.7) * s };
}
const svgDoc = (w: number, h: number, body: string, attrs = '') =>
  `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}"${attrs}>${body}\n</svg>\n`;
const inner = (svg: string) => svg.replace(/^<svg[^>]*>/, '').replace(/<\/svg>\s*$/, '');

const files: Record<string, string> = {};
// 1. mark, transparent, for light grounds
files['thunderstruck-mark.svg'] = svgDoc(256, 256, markBody());
// 2. mark for dark grounds, transparent
files['thunderstruck-mark-dark.svg'] = svgDoc(256, 256, markBody(DARK));
// 3. app icon tile
files['thunderstruck-icon.svg'] = svgDoc(256, 256, `<rect width="256" height="256" rx="56" fill="${CHAR}"/><g transform="translate(22 22) scale(0.86)">${markBody(DARK)}</g>`);
// 4. one colour (currentColor): terminal splash, stamps, single-colour print
files['thunderstruck-mark-mono.svg'] = svgDoc(256, 256, markBody(MONO), ` color="${INK}"`);
// 5. favicons
files['favicon.svg'] = svgDoc(64, 64, gauge(LIGHT, FAV));
files['favicon-dark.svg'] = svgDoc(64, 64, gauge(DARK, FAV));
// 6. horizontal lockup
const wm = outline(font, 'thunderstruck', 112);
const gap = 24, hW = Math.round(256 + gap + wm.width + 12);
const wmY = 128 + wm.capHeight / 2 + 4; // optical centre against the mark
const horiz = (c: Ink, ink: string) => svgDoc(hW, 256, markBody(c) + `<path transform="translate(${256 + gap} ${f(wmY)})" fill="${ink}" d="${wm.d}"/>`);
files['thunderstruck-lockup-horizontal-light.svg'] = horiz(LIGHT, INK);
files['thunderstruck-lockup-horizontal-dark.svg'] = horiz(DARK, PAPER);
// 7. vertical lockup (the README header)
const wmV = outline(font, 'thunderstruck', 72);
const vW = Math.round(Math.max(256, wmV.width) + 24), vH = 256 + 8 + Math.round(wmV.capHeight) + 24;
const vert = (c: Ink, ink: string) => svgDoc(vW, vH, `<g transform="translate(${f((vW - 256) / 2)} 0)">${markBody(c)}</g><path transform="translate(${f((vW - wmV.width) / 2)} ${f(256 + 8 + wmV.capHeight)})" fill="${ink}" d="${wmV.d}"/>`);
files['thunderstruck-lockup-vertical-light.svg'] = vert(LIGHT, INK);
files['thunderstruck-lockup-vertical-dark.svg'] = vert(DARK, PAPER);
// 8. wordmark alone
const wmDoc = (ink: string) => svgDoc(Math.round(wm.width) + 8, Math.round(wm.ascent) + 32, `<path transform="translate(4 ${f(wm.ascent)})" fill="${ink}" d="${wm.d}"/>`);
files['thunderstruck-wordmark-light.svg'] = wmDoc(INK);
files['thunderstruck-wordmark-dark.svg'] = wmDoc(PAPER);
// 9. OpenGraph / social card 1200×630
const ogWm = outline(font, 'thunderstruck', 120);
const tag1 = outline(mono, 'Find the thundering herd', 30), tag2 = outline(mono, 'before it finds you.', 30);
const cmd = outline(mono, '/plugin install thunderstruck@thunderstruck', 24);
files['thunderstruck-og.svg'] = svgDoc(1200, 630, `
  <rect width="1200" height="630" fill="${CHAR}"/>
  <g transform="translate(70 135) scale(1.3)">${markBody(DARK)}</g>
  <path transform="translate(450 ${f(200 + ogWm.capHeight)})" fill="${PAPER}" d="${ogWm.d}"/>
  <path transform="translate(452 352)" fill="${MUTED}" d="${tag1.d}"/>
  <path transform="translate(452 394)" fill="${MUTED}" d="${tag2.d}"/>
  <path d="M452 436 H1130" stroke="#2A3644" stroke-width="2"/>
  <path transform="translate(452 486)" fill="${TERRA}" d="${cmd.d}"/>`);
// 10. GitHub social preview / README banner 1280×400
files['thunderstruck-banner.svg'] = svgDoc(1280, 400, `
  <rect width="1280" height="400" fill="${CHAR}"/>
  <g transform="translate(${f((1280 - hW) / 2)} 72)">${inner(files['thunderstruck-lockup-horizontal-dark.svg'])}</g>`);

for (const [name, svg] of Object.entries(files)) writeFileSync(join(SVG, name), svg);

// ---- an .ico holding PNG images (valid since Windows Vista and in every current browser)
function ico(pngs: Buffer[], sizes: number[]): Buffer {
  const head = Buffer.alloc(6 + 16 * pngs.length);
  head.writeUInt16LE(0, 0); head.writeUInt16LE(1, 2); head.writeUInt16LE(pngs.length, 4);
  let offset = head.length;
  pngs.forEach((p, i) => {
    const e = 6 + 16 * i, s = sizes[i] >= 256 ? 0 : sizes[i];
    head.writeUInt8(s, e); head.writeUInt8(s, e + 1); head.writeUInt8(0, e + 2); head.writeUInt8(0, e + 3);
    head.writeUInt16LE(1, e + 4); head.writeUInt16LE(32, e + 6); head.writeUInt32LE(p.length, e + 8); head.writeUInt32LE(offset, e + 12);
    offset += p.length;
  });
  return Buffer.concat([head, ...pngs]);
}

const rasters: [string, string, number][] = [
  ['thunderstruck-mark.svg', 'thunderstruck-mark-512.png', 512], ['thunderstruck-mark.svg', 'thunderstruck-mark-256.png', 256],
  ['thunderstruck-icon.svg', 'icon-1024.png', 1024], ['thunderstruck-icon.svg', 'icon-512.png', 512], ['thunderstruck-icon.svg', 'icon-192.png', 192], ['thunderstruck-icon.svg', 'apple-touch-icon.png', 180],
  ['favicon.svg', 'favicon-64.png', 64], ['favicon.svg', 'favicon-32.png', 32], ['favicon.svg', 'favicon-16.png', 16], ['favicon-dark.svg', 'favicon-dark-32.png', 32],
  ['thunderstruck-lockup-horizontal-light.svg', 'lockup-horizontal-light.png', 1200], ['thunderstruck-lockup-horizontal-dark.svg', 'lockup-horizontal-dark.png', 1200],
  ['thunderstruck-lockup-vertical-light.svg', 'lockup-vertical-light.png', 640], ['thunderstruck-lockup-vertical-dark.svg', 'lockup-vertical-dark.png', 640],
  ['thunderstruck-og.svg', 'og-image.png', 1200], ['thunderstruck-banner.svg', 'banner.png', 1280], ['thunderstruck-mark-mono.svg', 'mark-mono-256.png', 256],
];
(async () => {
  const render = (src: string, w: number) => sharp(readFileSync(join(SVG, src)), { density: 600 }).resize({ width: w }).png({ compressionLevel: 9 });
  for (const [src, out, w] of rasters) await render(src, w).toFile(join(PNG, out));
  writeFileSync(join(PNG, 'favicon.ico'), ico(await Promise.all([16, 32, 48].map((s) => render('favicon.svg', s).toBuffer())), [16, 32, 48]));

  // contact sheet for review: light half, dark half
  const sheet = svgDoc(1400, 900, `<rect width="1400" height="900" fill="#FFFFFF"/><rect x="700" width="700" height="900" fill="${CHAR}"/>
    <g transform="translate(40 30)">${markBody()}</g>
    <g transform="translate(360 30)">${inner(files['thunderstruck-mark-mono.svg'])}</g>
    <g transform="translate(740 30)">${markBody(DARK)}</g>
    <g transform="translate(1080 30) scale(0.62)">${inner(files['thunderstruck-lockup-vertical-dark.svg'])}</g>
    <g transform="translate(40 330) scale(0.62)">${inner(files['thunderstruck-lockup-horizontal-light.svg'])}</g>
    <g transform="translate(740 330) scale(0.62)">${inner(files['thunderstruck-lockup-horizontal-dark.svg'])}</g>
    <g transform="translate(40 540) scale(0.9)">${inner(files['thunderstruck-icon.svg'])}</g>
    <g transform="translate(300 600)">${inner(files['favicon.svg'])}</g>
    <g transform="translate(390 616) scale(0.5)">${inner(files['favicon.svg'])}</g>
    <g transform="translate(440 624) scale(0.25)">${inner(files['favicon.svg'])}</g>
    <g transform="translate(500 616) scale(0.5)">${inner(files['favicon-dark.svg']).replace('<path', `<rect x="-8" y="-8" width="80" height="80" rx="12" fill="${CHAR}"/><path`)}</g>
    <g transform="translate(740 560) scale(0.5)">${inner(files['thunderstruck-og.svg'])}</g>`);
  writeFileSync(join(ROOT, 'contact-sheet.svg'), sheet);
  await sharp(Buffer.from(sheet), { density: 200 }).resize({ width: 1400 }).png({ compressionLevel: 9 }).toFile(join(ROOT, 'contact-sheet.png'));
  console.log('wrote', Object.keys(files).length, 'svg +', rasters.length + 1, 'png/ico');
})();
