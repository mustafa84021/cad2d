"""trimesh ile görselleştirme: sahne kurma, GLB/OBJ dışa aktarma, HTML izleyici.

Not: ``trimesh.SceneViewer`` ekran ister (X11/Wayland).  VS Code içinde ya da
headless ortamda çalışırken bunun yerine ``export_glb`` + ``write_html_viewer``
kullanın; GLB'yi tarayıcıda açmak etkileşimli inceleme için yeterlidir.
"""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

import numpy as np
import trimesh

__all__ = ["scene", "export_glb", "write_html_viewer", "screenshot", "show"]


def scene(meshes: dict[str, trimesh.Trimesh]) -> trimesh.Scene:
    """İsimli mesh sözlüğünden trimesh sahnesi kurar."""
    s = trimesh.Scene()
    for name, m in meshes.items():
        m.metadata["name"] = name
        s.add_geometry(m, geom_name=name)
    return s


def export_glb(s: trimesh.Scene, path: str | Path) -> Path:
    """Sahneyi tek bir .glb dosyasına yazar (binary glTF)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data = s.export(file_type="glb")
    p.write_bytes(data)
    return p


def export_obj(s: trimesh.Scene, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(s.export(file_type="obj"), encoding="utf-8")
    return p


def screenshot(s: trimesh.Scene, path: str | Path,
               resolution: tuple[int, int] = (1600, 1200)) -> Path | None:
    """Offscreen ekran görüntüsü (pyglet + OSMesa/EGL gerektirir)."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    try:
        png = s.save_image(resolution=resolution, visible=False)
    except Exception as exc:  # noqa: BLE001
        print(f"[uyarı] ekran görüntüsü alınamadı ({exc.__class__.__name__}): {exc}")
        print("        headless ortamda bunun yerine export_glb + write_html_viewer kullanın.")
        return None
    with open(p, "wb") as f:
        f.write(png)
    return p


def show(s: trimesh.Scene) -> None:
    """Etkileşimli pencere (masaüstü gerektirir)."""
    s.show()


# --------------------------------------------------------------- HTML izleyici
_HTML = """<!doctype html>
<html lang="tr">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
  html,body {{ margin:0; height:100%; background:{bg}; color:#e6e6e6;
              font:13px/1.45 system-ui, -apple-system, "Segoe UI", sans-serif; }}
  #app {{ position:fixed; inset:0; }}
  #hud {{ position:fixed; top:12px; left:12px; background:rgba(20,22,26,.82);
          border:1px solid #333a44; border-radius:10px; padding:10px 14px;
          max-width:330px; backdrop-filter:blur(6px); }}
  #hud h1 {{ margin:0 0 6px; font-size:14px; font-weight:600; }}
  #hud table {{ border-collapse:collapse; width:100%; }}
  #hud td {{ padding:1px 0; font-variant-numeric:tabular-nums; }}
  #hud td:last-child {{ text-align:right; color:#9fb4c7; }}
  .sw {{ display:inline-block; width:9px; height:9px; border-radius:2px;
         margin-right:6px; vertical-align:middle; }}
  #hud .hint {{ margin-top:8px; color:#8a97a6; font-size:11px; }}
  #err {{ position:fixed; inset:0; display:none; place-items:center; padding:40px;
          text-align:center; color:#ff9b9b; }}
</style>
</head>
<body>
<div id="app"></div>
<div id="hud">
  <h1>{title}</h1>
  <table>{legend}</table>
  <div class="hint">sol tuş: döndür &nbsp;·&nbsp; tekerlek: yakınlaş &nbsp;·&nbsp; sağ tuş: kaydır<br>
  klavye: <b>1/2/3</b> görünüm &nbsp;·&nbsp; <b>w</b> tel-kafes &nbsp;·&nbsp; <b>f</b> çerçevele</div>
</div>
<div id="err"></div>

<script type="importmap">
{{ "imports": {{
  "three": "https://unpkg.com/three@0.160.0/build/three.module.js",
  "three/addons/": "https://unpkg.com/three@0.160.0/examples/jsm/"
}} }}
</script>
<script type="module">
import * as THREE from 'three';
import {{ OrbitControls }} from 'three/addons/controls/OrbitControls.js';
import {{ GLTFLoader }}    from 'three/addons/loaders/GLTFLoader.js';

const app = document.getElementById('app');
const renderer = new THREE.WebGLRenderer({{ antialias:true }});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(innerWidth, innerHeight);
renderer.outputColorSpace = THREE.SRGBColorSpace;
app.appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('{bg}');

const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.01, 5000);
camera.position.set({cx:.2f}, {cy:.2f}, {cz:.2f});

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.08;

scene.add(new THREE.HemisphereLight(0xdfe8f5, 0x2b2f36, 1.15));
const key = new THREE.DirectionalLight(0xffffff, 1.6);
key.position.set(60, 120, 80); scene.add(key);
const fill = new THREE.DirectionalLight(0x9fc4ff, 0.5);
fill.position.set(-80, 40, -60); scene.add(fill);

const grid = new THREE.GridHelper({grid}, {griddiv}, 0x3a4250, 0x272d36);
grid.position.y = -0.01; scene.add(grid);

const BOX = new THREE.Box3();
let root = null;

new GLTFLoader().load('{glb}', (gltf) => {{
  root = gltf.scene;
  root.traverse(o => {{
    if (o.isMesh) {{
      o.castShadow = o.receiveShadow = true;
      if (o.material) {{ o.material.side = THREE.DoubleSide; }}
    }}
  }});
  scene.add(root);

  // GLB Y-up; mimari Z-up'a çevir
  root.rotation.x = -Math.PI / 2;

  BOX.setFromObject(root);
  const size = BOX.getSize(new THREE.Vector3());
  const mid  = BOX.getCenter(new THREE.Vector3());
  controls.target.copy(mid);
  const d = Math.max(size.x, size.y, size.z) || 1;
  camera.position.set(mid.x + d*0.9, mid.y + d*0.75, mid.z + d*1.1);
  camera.near = d/500; camera.far = d*60; camera.updateProjectionMatrix();
  controls.update();
  frame();
}}, undefined, (e) => {{
  const el = document.getElementById('err');
  el.style.display = 'grid';
  el.textContent = 'GLB yüklenemedi: ' + e;
}});

let wire = false;
addEventListener('keydown', (e) => {{
  const k = e.key.toLowerCase();
  if (k === 'w' && root) {{
    wire = !wire;
    root.traverse(o => {{ if (o.isMesh) o.material.wireframe = wire; }});
  }} else if (k === 'f' && root) {{
    BOX.setFromObject(root);
    const size = BOX.getSize(new THREE.Vector3());
    const mid  = BOX.getCenter(new THREE.Vector3());
    controls.target.copy(mid);
    const d = Math.max(size.x, size.y, size.z) || 1;
    camera.position.set(mid.x + d*0.9, mid.y + d*0.75, mid.z + d*1.1);
    controls.update();
  }} else if (k === '1') {{ camera.position.set(0.001, 0, 400); controls.target.set(0,0,0); }}
  else if (k === '2') {{ camera.position.set(0, 400, 0.001); controls.target.set(0,0,0); }}
  else if (k === '3') {{ camera.position.set(400, 0, 0.001); controls.target.set(0,0,0); }}
}});

addEventListener('resize', () => {{
  camera.aspect = innerWidth/innerHeight; camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
}});

function frame() {{ requestAnimationFrame(frame); controls.update(); renderer.render(scene, camera); }}
</script>
</body>
</html>
"""


_INDEX = """<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><title>{title}</title>
<style>
 body {{ margin:0; background:#15181d; color:#e6e6e6;
         font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif; }}
 header {{ padding:26px 30px 10px; border-bottom:1px solid #262c34; }}
 h1 {{ margin:0 0 4px; font-size:19px; font-weight:600; }}
 .sub {{ color:#8a97a6; font-size:12.5px; }}
 main {{ padding:22px 30px 60px; display:grid; gap:16px;
         grid-template-columns:repeat(auto-fill,minmax(300px,1fr)); }}
 a.card {{ display:block; text-decoration:none; color:inherit; background:#1b2027;
           border:1px solid #2b323b; border-radius:12px; padding:16px 18px;
           transition:.15s; }}
 a.card:hover {{ border-color:#4d9fe0; transform:translateY(-2px); }}
 a.card h2 {{ margin:0 0 6px; font-size:15px; font-weight:600; }}
 a.card .meta {{ color:#8a97a6; font-size:12px; }}
 .sw {{ display:inline-block; width:9px; height:9px; border-radius:2px;
        margin-right:5px; }}
 .legend {{ margin-top:10px; font-size:11.5px; color:#9fb4c7; }}
</style></head><body>
<header><h1>{title}</h1>
<div class="sub">Her karta tıklayın; three.js ile etkileşimli 3B model açılır
(sol tuş döndür · tekerlek yakınlaş · <b>w</b> tel-kafes · <b>f</b> çerçevele)</div>
</header><main>{cards}</main></body></html>
"""

_CARD = """<a class="card" href="{html}">
  <h2>{name}</h2>
  <div class="meta">{glb}</div>
  <div class="legend">{legend}</div>
</a>"""


def write_index(
    path: str | Path,
    entries: Sequence[tuple[str, str, dict]],
    title: str = "Kat paftaları",
) -> Path:
    """``[(ad, glb_dosya_adı, {parça: renk}), ...]`` -> kart dizini HTML."""
    cards = ""
    for name, glb, legend in entries:
        leg = " ".join(f'<span class="sw" style="background:{c}"></span>{p}'
                       for p, c in legend.items())
        cards += _CARD.format(html=Path(glb).with_suffix(".html").name,
                              name=name, glb=glb, legend=leg)
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(_INDEX.format(title=title, cards=cards), encoding="utf-8")
    return p


def write_html_viewer(
    glb_path: str | Path,
    html_path: str | Path,
    legend: dict[str, str] | None = None,
    title: str = "3B Model",
    grid: float = 100.0,
    grid_div: int = 20,
) -> Path:
    """GLB'yi three.js ile açan tek dosyalık HTML yazar.

    Args:
        glb_path:  .glb dosyası (HTML'in yanında olmalı)
        html_path: yazılacak .html
        legend:    {parça adı: '#rrggbb'} -> sağ üstte renk açıklaması
    """
    rows = ""
    for name, col in (legend or {}).items():
        rows += (f'<tr><td><span class="sw" style="background:{col}"></span>'
                 f'{name}</td></tr>')
    html = _HTML.format(
        title=title, glb=Path(glb_path).name, legend=rows,
        bg="#15181d", grid=grid, griddiv=grid_div,
        cx=60.0, cy=60.0, cz=80.0,
    )
    p = Path(html_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p
