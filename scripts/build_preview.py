"""Generate a self-contained, explicitly OFFLINE HTML preview; no build tools."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
html=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
css=(ROOT/'web'/'styles.css').read_text(encoding='utf-8')
model=(ROOT/'web'/'model.js').read_text(encoding='utf-8')
app=(ROOT/'web'/'app.js').read_text(encoding='utf-8')
seed=(ROOT/'web'/'seed.json').read_text(encoding='utf-8').replace('<','\\u003c').replace('>','\\u003e')
html=html.replace('<link rel="icon" href="favicon.svg" type="image/svg+xml">','<link rel="icon" href="/favicon.ico" type="image/x-icon">')
html=html.replace('<link rel="stylesheet" href="styles.css">','<style>'+css+'</style>')
html=html.replace('<script src="model.js" defer></script><script src="app.js" defer></script>','')
html=html.replace('</body>',f'<script>window.__PREVIEW_SEED__={seed};</script><script>{model}</script><script>{app}</script></body>')
(ROOT/'preview.html').write_text(html,encoding='utf-8')
(ROOT/'docs').mkdir(exist_ok=True)
(ROOT/'docs'/'index.html').write_text(html,encoding='utf-8')
print('Built preview.html (offline, self-contained).')
