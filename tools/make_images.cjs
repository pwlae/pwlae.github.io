// Makes the link-preview image and the home screen icons. Run once, by hand,
// only when the photo or the title changes (the outputs are committed):
//
//   node tools/make_images.cjs path/to/tube-photo.jpg
//
// The photo is the public-domain original from Wikimedia Commons:
// https://commons.wikimedia.org/wiki/File:Why_London_Underground_is_nicknamed_The_Tube.jpg
// (download the 1920px version). Needs ffmpeg for the JPEG step.
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');
const puppeteer = require('puppeteer');

const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'images');
const cur = JSON.parse(fs.readFileSync(path.join(ROOT, 'curriculum.json'), 'utf8'));
const photo = process.argv[2];
if (!photo) { console.error('usage: node tools/make_images.cjs <photo.jpg>'); process.exit(1); }
const photoUrl = 'data:image/jpeg;base64,' + fs.readFileSync(photo).toString('base64');
const font = "system-ui,-apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif";

const card = `<body style="margin:0;width:1200px;height:630px;font-family:${font};background:#fff">
  <div style="height:430px;background:url(${photoUrl}) center 50%/cover"></div>
  <div style="height:200px;padding:28px 56px;box-sizing:border-box;border-top:6px solid #111">
    <div style="font-size:64px;font-weight:700;color:#111;line-height:1.1">${cur.title}</div>
    <div style="font-size:30px;color:#444;margin-top:14px">Algorithms from zero, one commute at a time.</div>
  </div></body>`;

// The same "{}" mark as the favicon. Kept inside the middle 60% so it
// survives the circle/squircle masks phones apply ("maskable").
const icon = size => `<body style="margin:0;width:${size}px;height:${size}px;background:#111;display:flex;
  align-items:center;justify-content:center;color:#fff;font:700 ${Math.round(size * 0.36)}px ui-monospace,Menlo,Consolas,monospace">{}</body>`;

(async () => {
  const b = await puppeteer.launch({ executablePath: process.env.PUPPETEER_EXECUTABLE_PATH || '/snap/bin/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage();
  const shot = async (html, w, h, file) => {
    await p.setViewport({ width: w, height: h, deviceScaleFactor: 1 });
    await p.setContent(html, { waitUntil: 'load' });
    await p.screenshot({ path: file });
  };
  const tmp = path.join(OUT, 'og.png');
  await shot(card, 1200, 630, tmp);
  for (const s of [512, 192, 180]) await shot(icon(s), s, s, path.join(OUT, `icon-${s}.png`));
  await b.close();
  execFileSync('ffmpeg', ['-loglevel', 'error', '-y', '-i', tmp, '-q:v', '5', path.join(OUT, 'og.jpg')]);
  fs.unlinkSync(tmp);
  for (const f of ['og.jpg', 'icon-512.png', 'icon-192.png', 'icon-180.png'])
    console.log(f, fs.statSync(path.join(OUT, f)).size, 'bytes');
})();
