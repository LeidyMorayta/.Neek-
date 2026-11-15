(() => {
  const state = { lang:'es', text:0, layer:0, year:2025, exp:['r0'], view:null, drawer:false,
    parcels:[{id:'demo',kind:'demo'}], sel:'demo', draw:null, picker:false, matrixMode:false, matrixText:'', notice:null, mes:6, // parcelas
    cur:0, stage:0, have:{} }; // rotación actual, etapa y materiales listos
  const INFO_VIEWS = ['nasa','about','mission'];
  const INFO_ICONS = ['satellite','people','target'];
  const texts = () => copy[state.lang];
  const API_BASE = (window.NEEK_API_BASE || '').replace(/\/$/, '');

  /* ---------- Constantes ---------- */
  const BEST = 1; // solo para los ejemplos históricos
  const ROT_SOURCES = [['SMAP','NDVI'],['SMAP','GPM','NDVI'],['NASA POWER','SoilGrids','SRTM']];
  const COND_META = [{icon:'drop',level:'attention'},{icon:'rain',level:'attention'},{icon:'leaf',level:'attention'},{icon:'soil',level:'attention'}];
  const FINDING_LEVELS = ['attention','attention','risk','good'];
  const LAYER_ICONS = ['drop','leaf','soil','leaf','rain','drop','soil','soil'];
  // Tendencia de ejemplo (índice 0–100) por capa, 2015 → 2025. Es decorativa.
  const HIST = [
    [58,55,60,52,49,54,47,50,46,52,56],
    [48,52,50,55,58,54,60,57,62,59,64],
    [22,18,25,20,16,19,14,17,12,15,11],
  ];

  /* ---------- Utilidades ---------- */
  const html = (strings, ...values) => { let r = strings[0]; values.forEach((v,i) => r += v + strings[i+1]); return r.replace(/>\s*\n\s*</g,'><').trim(); };
  const clamp = (n,min,max) => Math.min(max, Math.max(min, n));
  const icon = (name, size=22) => `<svg class="icon" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="square" stroke-linejoin="miter" aria-hidden="true">${ICONS[name]||''}</svg>`;
  const esc = (x) => String(x).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (str, n, b) => str.replace('{n}', n).replace('{b}', b);
  const tag = (t) => `<span class="tag">${t}</span>`;
  const statusBadge = (lvl, txt) => `<span class="status ${lvl}">${icon(lvl==='good'?'check':'warning',17)}${txt}</span>`;
  const button = (txt, ic, act, sec=false, extra='') => `<button class="button ${sec?'secondary':''} ${extra}" data-act="${act}">${ic?icon(ic):''}<span>${txt}</span></button>`;
  const eyebrow = (ic, txt) => `<span class="eyebrow">${icon(ic,20)}${txt}</span>`;
  const sectionTitle = (ic, ti, sub, tg) => `<div class="section-title"><div class="title-icon">${icon(ic,30)}</div><div>${tg?tag(tg):''}<h2>${ti}</h2><p>${sub}</p></div></div>`;
  const infoBlock = (ti, ic, txt) => `<div class="info-block">${icon(ic)}<div><b>${ti}</b><p>${txt}</p></div></div>`;

  /* ---------- Parcelas: dibujar, elegir y subir GeoJSON ---------- */
  let pid = 0;
  const parcel = () => state.parcels.find(p => p.id === state.sel);
  const pName = (p, t) => p.kind === 'demo' ? t.fieldName : p.name;
  const pMeta = (p, t) => p.kind === 'demo' ? t.metaDemo : p.kind === 'drawn' ? fmt(t.metaDrawn, p.ha.toLocaleString(state.lang, {maximumFractionDigits:2})) : fmt(t.metaGeo, p.ha.toLocaleString(state.lang, { maximumFractionDigits: 2 }));
  const noticeText = t => state.notice ? fmt(t.notices[state.notice[0]], state.notice[1]) : '';
  const setNotice = (key, n) => { state.notice = key ? [key, n] : null; const el = document.getElementById('notice'); if (el) el.textContent = noticeText(texts()); };

  // Convierte los anillos de un GeoJSON (lon/lat) al lienzo del mapa (700×440) y calcula el área
  const geoRings = (g, out = []) => {
    if (g.type === 'FeatureCollection') g.features.forEach(f => geoRings(f, out));
    else if (g.type === 'Feature') geoRings(g.geometry, out);
    else if (g.type === 'GeometryCollection') g.geometries.forEach(x => geoRings(x, out));
    else if (g.type === 'Polygon') out.push(g.coordinates[0]);
    else if (g.type === 'MultiPolygon') g.coordinates.forEach(c => out.push(c[0]));
    return out;
  };
  const fitRings = (raw) => {
    if (!raw.length || raw.some(r => !Array.isArray(r) || r.length < 4)) throw 'noPolygon';
    if (raw.some(r => r.some(c => !(Math.abs(c[0]) <= 180 && Math.abs(c[1]) <= 90)))) throw 'badCoords';
    const k = Math.cos(raw[0][0][1] * Math.PI / 180);
    const m = raw.map(r => { const step = Math.ceil(r.length / 400); return r.filter((_, i) => i % step === 0).map(c => [c[0] * 111320 * k, c[1] * 110540]); });
    const xs = m.flat().map(c => c[0]), ys = m.flat().map(c => c[1]);
    const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    if (x1 === x0 || y1 === y0) throw 'noPolygon';
    const sc = Math.min(560 / (x1 - x0), 360 / (y1 - y0));
    const area = r => Math.abs(r.reduce((a, c, i) => { const d = r[(i + 1) % r.length]; return a + c[0] * d[1] - d[0] * c[1]; }, 0) / 2);
    return { ha: m.reduce((a, r) => a + area(r), 0) / 10000, rings: m.map(r => r.map(c => [+(350 + (c[0] - (x0 + x1) / 2) * sc).toFixed(1), +(220 - (c[1] - (y0 + y1) / 2) * sc).toFixed(1)])) };
  };
  const addParcel = (p, key) => {
    const t = texts();
    p.month = state.mes;
    p.id = 'p' + (++pid); p.name = esc((p.name || '').trim()) || fmt(t.newName, state.parcels.length);
    state.parcels.push(p); state.sel = p.id; state.draw = null; state.picker = false; state.matrixMode = false; autoZoomParcel = true; state.cur=0; state.stage=0;
    setNotice(key, p.name); render(); requestAnalysis(p);
  };
  const loadGeo = async (file) => {
    if (!file) return;
    try {
      if (file.size > 1_000_000) throw 'badFile';
      const g = JSON.parse(await file.text());
      const raw = geoRings(g);
      if (!raw.length) throw 'noPolygon';
      const first = g.type === 'FeatureCollection' ? g.features[0] : g;
      const properties = first?.properties || {};
      const fitted = fitRings(raw);
      addParcel({kind:'geo', name:properties.name || properties.nombre || file.name.replace(/\.(geo)?json$/i,''), ...fitted, geojson:g}, 'uploaded');
    } catch (err) { setNotice(typeof err === 'string' ? err : 'badFile'); }
  };

  const matrixGeometry = (source) => {
    let pts;
    try {
      pts = JSON.parse(source);
    } catch (_) {
      pts = source.trim().split(/\n+/).map(row => row.trim().split(/[;,\s]+/).filter(Boolean).map(Number));
    }
    if (!Array.isArray(pts) || pts.length < 3 || pts.length > 500) throw 'badCoords';
    pts = pts.map(pt => {
      if (pt && !Array.isArray(pt) && typeof pt === 'object') return [Number(pt.longitud ?? pt.lon), Number(pt.latitud ?? pt.lat)];
      return pt;
    });
    if (pts.some(pt => !Array.isArray(pt) || pt.length!==2 || !pt.every(Number.isFinite))) throw 'badCoords';
    if (pts[0][0] !== pts[pts.length-1][0] || pts[0][1] !== pts[pts.length-1][1]) pts.push([...pts[0]]);
    return {type:'Polygon',coordinates:[pts]};
  };
  const mapPoint = () => false; // El dibujo geográfico ahora se registra con clics de Leaflet.

  const parcelHead = (t) => {
    const p = parcel(), d = state.draw, pk = state.picker;
    return `<div class="card-heading"><div>${eyebrow('map',t.where)}<h3>${pName(p,t)}</h3><p class="note">${pMeta(p,t)}</p></div>${p.busy ? tag(t.loadingAnalysis) : p.analysis ? statusBadge('attention',t.regionalAnalysis) : tag(say('Sin análisis','No analysis'))}</div>`;
  };
  const toolsRow = (t) => { const d = state.draw, pk = state.picker; return `<div class="parcel-tools" role="group" aria-label="${t.parcelTools}"><button class="${d?'active':''}" data-act="add" aria-pressed="${!!d}">${icon('plus',20)}${t.addParcel}</button><button class="${pk?'active':''}" data-act="pick" aria-expanded="${pk}">${icon('pin',20)}${t.selectParcel}</button><button data-act="upload">${icon('upload',20)}${t.uploadGeo}</button><button class="${state.matrixMode?'active':''}" data-act="matrix">${icon('pin',20)}${t.matrixBtn}</button></div>`; };
  const parcelPanel = (t) => toolsRow(t) + panelBody(t);
  const panelBody = (t) => {
    if (state.draw) {
      const n = state.draw.pts.length;
      return `<div class="panel"><b>${t.drawTitle}</b><p>${t.drawHelp}</p><label class="name-field"><span>${t.nameLabel}</span><input type="text" maxlength="40" data-act="pname" placeholder="${fmt(t.newName,state.parcels.length)}" value="${esc(state.draw.name)}"></label><p class="count">${fmt(t.drawCount,n)}</p><div class="panel-actions"><button data-act="undo" ${n?'':'disabled'}>${icon('undo',18)}${t.undo}</button><button class="primary" data-act="finish" ${n<3?'disabled':''}>${icon('check',18)}${t.finish}</button><button data-act="cancel">${t.cancel}</button></div></div>`;
    }
    if (state.matrixMode) {
      return `<div class="panel"><b>${t.matrixTitle}</b><p>${t.matrixHelp}</p><textarea id="coords" data-act="coords" rows="5" spellcheck="false" placeholder="-89.62, 20.85\n-89.60, 20.85\n-89.60, 20.83\n-89.62, 20.83">${esc(state.matrixText)}</textarea><div class="panel-actions"><button class="primary" data-act="matrix-apply">${icon('check',18)}${t.matrixBtn}</button><button data-act="matrix">${t.cancel}</button></div></div>`;
    }
    if (!state.picker) return '';
    const rows = state.parcels.map(p => {
      const on = p.id === state.sel, name = pName(p, t);
      return `<li class="pick ${on?'on':''}"><button data-act="sel" data-v="${p.id}" aria-pressed="${on}">${icon(on?'check':'pin',20)}<span><b>${name}</b><small>${pMeta(p,t)}</small></span>${on?`<em>${t.parcelCurrent}</em>`:''}</button>${p.kind==='demo'?'':`<button class="icon-button" data-act="del" data-v="${p.id}" aria-label="${t.deleteParcel}: ${name}">${icon('trash',18)}</button>`}</li>`;
    }).join('');
    return `<div class="panel"><b>${t.pickTitle}</b><ul class="pick-list">${rows}</ul>${state.parcels.length < 2 ? `<p class="note">${t.pickHint}</p>` : ''}</div>`;
  };
  const refreshParcel = (focus) => { render(focus); };

  /* ---------- Mapa satelital y delimitación real con Leaflet ---------- */
  let map = null, mapBorder = null, rememberedMapView = null, autoZoomParcel = false;
  let rasterOverlay = null;
  const LAYER_KEYS = ['moisture', 'vegetation', 'soil', 'change', 'rainfall', 'evapotranspiration', 'carbon', 'cec'];
  const rasterState = p => p.rasters?.[LAYER_KEYS[state.layer]];
  const paintRaster = () => {
    if (!map) return;
    if (rasterOverlay) { map.removeLayer(rasterOverlay); rasterOverlay = null; }
    const r = rasterState(parcel())?.data;
    if (!r) return;
    const [west,south,east,north] = r.bounds;
    if (r.image) {
      rasterOverlay = L.imageOverlay(r.image, [[south,west],[north,east]], {opacity:.8, className:'pixel-raster'}).addTo(map);
      return;
    }
    const canvas = document.createElement('canvas');
    canvas.width = r.width; canvas.height = r.height;
    const ctx = canvas.getContext('2d'), image = ctx.createImageData(r.width, r.height);
    r.values.flat().forEach((value, i) => {
      if (value === null) return;
      const v = clamp((value-r.minimum)/(r.maximum-r.minimum), 0, 1);
      const color = state.layer === 3 ? (v < .5 ? [210, Math.round(140+v*120), 75] : [50, Math.round(140+v*70), 190]) : [4,5].includes(state.layer) ? [35,90+Math.round(100*v),220] : state.layer === 0 ? [35, 90+Math.round(100*v), 220] :
        state.layer === 2 ? (v < .5 ? [220, 100+Math.round(v*220), 65] : [80, 170, 100+Math.round(v*130)]) :
        [Math.round(220*(1-v)+30*v), Math.round(65*(1-v)+180*v), 55];
      image.data.set([...color, 195], i*4);
    });
    ctx.putImageData(image, 0, 0);
    const [w,s,e,n] = r.bounds;
    rasterOverlay = L.imageOverlay(canvas.toDataURL(), [[s,w],[n,e]], {opacity:.85, interactive:false, className:'pixel-raster'}).addTo(map);
  };
  const requestRaster = async (force=false, key=LAYER_KEYS[state.layer]) => {
    const p = parcel();
    if (!p.geojson) { updateField(); return; }
    p.rasters ||= {};
    if (p.rasters[key] && !force) { if (key === LAYER_KEYS[state.layer]) { paintRaster(); updateField(); } return; }
    const entry = p.rasters[key] = {busy:true};
    updateField(); paintRaster();
    try {
      const response = await fetch(`${API_BASE}/capas/${key}`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({geojson:p.geojson,comparison_days:p.comparisonDays || 30})});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail));
      entry.data = data;
    } catch (error) { entry.error = error.message; }
    finally {
      entry.busy = false;
      if (parcel() === p && document.getElementById('legend')) render();
    }
  };
  const fieldMap = (t) => `<div class="map-viewport ${state.draw?'drawing':''}"><div id="sat-map" class="satellite-map" role="region" aria-label="${t.mapLabel}"></div><div class="map-caption">${icon('satellite',16)}${t.mapCredits}</div></div>`;
  const disposeMap = () => {
    if (!map) return;
    const c = map.getCenter();
    rememberedMapView = {center:[c.lat,c.lng],zoom:map.getZoom()};
    map.off(); map.remove(); map = null; rasterOverlay = null;
  };
  const initMap = () => {
    if (!document.getElementById('sat-map') || !window.L) return;
    const p = parcel();
    map = L.map('sat-map', {scrollWheelZoom:false, preferCanvas:true});
    const view = rememberedMapView || {center:[20.75,-89.05],zoom:8};
    map.setView(view.center,view.zoom);
    L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
      maxZoom:19, attribution:'Imágenes &copy; Esri, Maxar, Earthstar Geographics y comunidad GIS'
    }).addTo(map);
    fetch('yucatan_estado.geojson').then(r => r.ok ? r.json() : null).then(g => {
      if (g && map) mapBorder = L.geoJSON(g, {style:{color:'#F9E9C3',weight:2,fill:false,dashArray:'6 5'}, interactive:false}).addTo(map);
    }).catch(() => {});
    if (p.geojson) {
      const g = L.geoJSON(p.geojson, {style:{color:'#F7D97D',weight:3,fillColor:'#F2CC62',fillOpacity:0.2}}).addTo(map);
      if (!rememberedMapView) map.fitBounds(g.getBounds().pad(0.5),{maxZoom:17});
    }
    if (p.analysis?.parcela?.punto_muestreado) {
      const q = p.analysis.parcela.punto_muestreado;
      L.circleMarker([q.latitud,q.longitud],{radius:7,color:'#493326',fillColor:'#FFF4B9',fillOpacity:1})
        .addTo(map).bindPopup(`${esc(texts().soilSamplePopup)}: ${q.latitud}, ${q.longitud}<br>${esc(texts().soilSampleCaution)}`);
    }
    const pts = state.draw?.pts || [];
    if (pts.length) {
      L.polyline(pts.map(q => [q[1],q[0]]),{color:'#F9E9C3',weight:3,dashArray:'6 5'}).addTo(map);
      if (pts.length >= 3) L.polygon(pts.map(q => [q[1],q[0]]),{color:'#D57A36',fillOpacity:.23}).addTo(map);
      pts.forEach(q => L.circleMarker([q[1],q[0]],{radius:5,color:'#493326',fillColor:'#F5BE61',fillOpacity:1}).addTo(map));
    }
    map.on('click',e => {
      if (!state.draw) return;
      state.draw.pts.push([Number(e.latlng.lng.toFixed(6)), Number(e.latlng.lat.toFixed(6))]);
      refreshParcel();
    });
    if (autoZoomParcel && p.geojson) { map.fitBounds(L.geoJSON(p.geojson).getBounds().pad(.3), {maxZoom:17}); autoZoomParcel = false; }
    paintRaster();
    requestRaster();
    if (p.geojson) { requestRaster(false, 'moisture'); requestRaster(false, 'vegetation'); }
    setTimeout(() => map?.invalidateSize(), 0);
  };

  const requestAnalysis = async (p) => {
    if (!p || !p.geojson) return;
    const requestId = p.analysisRequest = (p.analysisRequest || 0) + 1;
    const month = p.month ?? state.mes;
    p.busy = true; p.error = null; p.analysis = null;
    render();
    try {
      const response = await fetch(`${API_BASE}/analizar-parcela`, {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({mes:month,geojson:p.geojson,manejo:managementFor(p)})
      });
      const result = await response.json();
      if (!response.ok) {
        const d = result.detail;
        throw new Error(typeof d === 'string' ? d : d?.faltantes?.join(' ') || d?.mensaje || JSON.stringify(d));
      }
      if (p.analysisRequest !== requestId) return;
      p.analysis = result;
      if (state.sel === p.id) { state.cur = 0; state.stage = 0; }
    } catch(err) { if (p.analysisRequest === requestId) p.error = err.message || String(err); }
    finally { if (p.analysisRequest === requestId) { p.busy = false; if (state.sel === p.id) render(); } }
  };

  /* ---------- Mapa, leyenda y gráfica histórica ---------- */
  const legendHtml = (t) => {
    const p = parcel(), result = p.analysis;
    if (p.geojson) {
      const r = rasterState(p);
      if (r?.busy) return `<span role="status">${t.layerLoading}</span>`;
      if (r?.error) return `<span role="status">${esc(r.error)}</span><button data-act="raster-retry">${t.layerRetry}</button>`;
      if (r?.data) {
        const d = r.data;
        return `<span><b>${esc(d.metric)}</b> · ${esc(d.source)} · ${esc(d.date || 'Mapa estático / Static map')} · ~${d.resolution_m} m<br>${d.legend ? `<img class="nasa-legend" src="${esc(d.legend)}" alt="Escala NASA SMAP (m³/m³)">` : `<span class="raster-scale ${state.layer === 2 ? 'ph-scale' : state.layer === 3 ? 'change-scale' : [4,5].includes(state.layer) ? 'water-scale' : ''}"></span> ${d.minimum} → ${d.maximum} · ${d.valid_pixels} píxeles / pixels${d.statistics ? ` · ${say('Media','Mean')}: ${d.statistics.mean}` : ''}`}<br>${esc(d.caution)}</span>`;
      }
    }
    if (state.layer === 2 && result?.suelo) {
      return `<span>${t.soilQualityPartial}: pH ${result.suelo.ph}, ${esc(result.suelo.textura)}. ${t.soilNotFertility}</span>`;
    }
    return `<span>${t.layerChoose}</span>`;
  };
  const histChart = (t) => {
    const v = HIST[state.layer], W = 400, H = 130, px = 24, py = 14, cur = state.year - 2015;
    const x = i => px + i * (W - 2*px) / 10;
    const y = n => H - py - n / 100 * (H - 2*py);
    const pts = v.map((n,i) => `${x(i).toFixed(1)},${y(n).toFixed(1)}`).join(' ');
    const dots = v.map((n,i) => i === cur ? '' : `<circle cx="${x(i).toFixed(1)}" cy="${y(n).toFixed(1)}" r="3.5" fill="#FFF9EF" stroke="#493326" stroke-width="2"/>`).join('');
    const marks = [0,5,10].map(i => `<text x="${x(i)}" y="${H+14}" text-anchor="${i===0?'start':i===10?'end':'middle'}" font-family="Nunito, sans-serif" font-weight="700" font-size="12" fill="#6B5446">${2015+i}</text>`).join('');
    return `<svg class="hist-chart" viewBox="0 0 ${W} ${H+20}" role="img" aria-label="${t.histLabel}"><line x1="${px}" y1="${H-py}" x2="${W-px}" y2="${H-py}" stroke="#DFCFAE" stroke-width="2"/><polygon points="${x(0)},${H-py} ${pts} ${x(10)},${H-py}" fill="#A8B99A" fill-opacity=".35"/><polyline points="${pts}" fill="none" stroke="#A84F36" stroke-width="3" stroke-linejoin="round" stroke-linecap="round"/><line x1="${x(cur)}" y1="${y(v[cur])}" x2="${x(cur)}" y2="${H-py}" stroke="#A84F36" stroke-width="2" stroke-dasharray="4 4"/>${dots}<circle cx="${x(cur)}" cy="${y(v[cur])}" r="7" fill="#E9BE61" stroke="#A84F36" stroke-width="3"/>${marks}</svg>`;
  };
  // Las capas sin datos parcelarios no se pintan como mapas medidos.
  const updateField = () => {
    const t = texts(), p = parcel();
    document.getElementById('legend').innerHTML = legendHtml(t);
    if (p.kind === 'demo' && document.getElementById('yr')) {
      document.getElementById('yr').textContent = state.year;
      document.getElementById('hist').innerHTML = histChart(t);
      document.getElementById('hist-layer').textContent = t.layers[state.layer];
    }
    document.querySelectorAll('.layer-chips button').forEach((b,i) => {
      b.classList.toggle('active',i===state.layer);b.setAttribute('aria-pressed',i===state.layer);
    });
  };

  /* ---------- Rotación actual: etapas y materiales ---------- */
  const haveCount = () => { const m = rotMaterials[state.lang][state.cur]?.materials || []; return [m.filter((_, j) => state.have[`${state.cur}-${j}`]).length, m.length]; };
  const updateHave = () => {
    const [a, b] = haveCount();
    document.getElementById('have-progress').textContent = fmt(texts().haveProgress, a, b);
    document.getElementById('have-bar').style.width = `${a / b * 100}%`;
  };
  const workPanel = (t, all) => {
    if (parcel().analysis) return `<article class="card work"><b>${t.workTitle}</b><p>${t.workRealNotice}</p></article>`;
    const seq = all[state.cur][1], stages = seq.split(' → '), st = state.stage, mats = rotMaterials[state.lang][state.cur].materials, [a, b] = haveCount();
    const steps = stages.map((x,j) => `<li class="${j<st?'done':j===st?'now':''}"><button data-act="stage" data-v="${j}" aria-current="${j===st?'step':'false'}"><i>${j<st?icon('check',16):j+1}</i>${x}</button></li>`).join('');
    const have = mats.map((m,j) => `<li><label><input type="checkbox" data-act="have" data-v="${j}" ${state.have[`${state.cur}-${j}`]?'checked':''}><span>${m}</span></label></li>`).join('');
    return `<article id="trabajo" class="card work"><div class="card-heading"><div>${eyebrow('tractor',t.current)}<h3>${t.workTitle}</h3></div><span class="current-badge">${seq}</span></div><div class="work-grid"><div><b>${t.stagesTitle}</b><ol class="stages">${steps}</ol><p>${t.stageNow}: <b>${stages[st]}</b> (${st+1}/${stages.length})</p><div class="panel-actions"><button data-act="prev" ${st?'':'disabled'}>${t.prevStage}</button><button class="primary" data-act="next" ${st<stages.length-1?'':'disabled'}>${t.nextStage}</button></div></div><div><b>${t.haveTitle}</b><p id="have-progress" class="note">${fmt(t.haveProgress,a,b)}</p><div class="bar"><i id="have-bar" style="width:${a/b*100}%"></i></div><ul class="check-list">${have}</ul></div></div></article>`;
  };

  const say = (es, en) => state.lang === 'es' ? es : en;
  let cropCatalog = [];
  const managementFor = p => p.management ||= {water_system:'sin_declarar',previous_crop:null,priorities:{soil_health:3,water_saving:3,pest_break:3}};
  const managementControls = p => {
    const m = managementFor(p);
    const select = (key, label, options, current) => `<label>${label}<select data-act="management" data-key="${key}">${options.map(([value,text]) => `<option value="${esc(value)}" ${String(current ?? '') === String(value) ? 'selected' : ''}>${esc(text)}</option>`).join('')}</select></label>`;
    const priority = (key, es, en) => select(key, say(es,en), [1,2,3,4,5].map(n=>[n,String(n)]), m.priorities[key]);
    return `<fieldset class="management-controls"><legend>${say('Manejo y prioridades de esta parcela','Management and priorities for this field')}</legend>
      ${select('water_system',say('Disponibilidad de agua','Water availability'),[['sin_declarar',say('Sin declarar','Not declared')],['temporal',say('Temporal (sin riego)','Rainfed')],['riego',say('Con riego','Irrigated')]],m.water_system)}
      ${select('previous_crop',say('Cultivo anterior','Previous crop'),[['',say('Desconocido','Unknown')],...cropCatalog.map(c=>[c.nombre,c.nombre])],m.previous_crop)}
      ${priority('soil_health','Prioridad: suelo (1–5)','Priority: soil (1–5)')}
      ${priority('water_saving','Prioridad: ahorrar agua (1–5)','Priority: save water (1–5)')}
      ${priority('pest_break','Prioridad: diversificar (1–5)','Priority: diversify (1–5)')}
      <p class="note">${say('Cambiar estas preferencias recalcula las rotaciones. Declarar riego no confirma que exista agua suficiente.','Changing these preferences recalculates rotations. Declaring irrigation does not confirm sufficient water supply.')}</p></fieldset>`;
  };
  const rankedCrops = p => [...(p.analysis?.cultivos || [])].sort((a,b) => {
    const order = {verde:0, amarillo:1, rojo:2, datos_insuficientes:3};
    return (order[a.estado] ?? 3)-(order[b.estado] ?? 3) || (b.puntaje_provisional ?? -1)-(a.puntaje_provisional ?? -1);
  });
  const vegetationSummary = p => {
    const d = p.rasters?.vegetation?.data;
    if (!d) return null;
    const values = d.values.flat().filter(v => v !== null && Number.isFinite(v));
    return values.length ? {mean:values.reduce((a,b)=>a+b,0)/values.length, count:values.length, date:d.date} : null;
  };
  const observations = p => {
    const r = p.analysis, best = rankedCrops(p).find(c => ['verde','amarillo'].includes(c.estado));
    const rotation = r.rotaciones.estrategias.find(x => x.tipo === 'sugerida');
    return [
      {level:'attention', text:say(`Suelo estimado: pH ${r.suelo.ph}, textura ${r.suelo.textura}.`, `Estimated soil: pH ${r.suelo.ph}, texture ${r.suelo.textura}.`),
       action:say('Confirma pH y textura con una muestra de campo antes de aplicar enmiendas.', 'Confirm pH and texture with a field sample before applying amendments.'), source:r.suelo.fuente},
      {level:best?.estado === 'verde' ? 'good' : 'attention', text:best ? say(`${best.cultivo} encabeza la aptitud preliminar: ${best.puntaje_provisional}/100; confianza ${best.confianza_datos}.`, `${best.cultivo} leads preliminary suitability: ${best.puntaje_provisional}/100; confidence ${best.confianza_datos}.`) : say('No hay cultivos recomendables con la evidencia actual.', 'No suitable crops can be recommended with the current evidence.'),
       action:best ? (best.recomendaciones?.[0] || say('Revisa las restricciones del cultivo.', 'Review crop restrictions.')) : say('Revisa las restricciones y los datos faltantes de los cultivos.', 'Review crop restrictions and missing data.'), source:say(`Modelo para mes ${r.mes_siembra} · clima regional + suelo de esta parcela`, `Model for month ${r.mes_siembra} · regional climate + this field’s soil`)},
      {level:'attention', text:rotation ? say(`Rotación propuesta: ${rotation.cultivos.join(' → ')}.`, `Proposed rotation: ${rotation.cultivos.join(' → ')}.`) : say('No hay una rotación evaluable para estas condiciones.', 'No rotation can be evaluated for these conditions.'),
       action:say('Comprueba historial, disponibilidad de agua y fechas de cada ciclo antes de elegir.', 'Check cropping history, water availability and dates for each cycle before choosing.'), source:r.rotaciones.historial_declarado ? say('Compatibilidad por ciclo e historial declarado','Suitability per cycle and declared history') : say('Compatibilidad por ciclo; sin historial declarado', 'Suitability per cycle; no declared history')},
      {level:'attention', text:r.suelo.profundidad_efectiva_cm == null ? say('Falta medir la profundidad efectiva; las recomendaciones siguen siendo provisionales.', 'Effective rooting depth is unknown; recommendations remain provisional.') : say(`Profundidad efectiva: ${r.suelo.profundidad_efectiva_cm} cm.`, `Effective rooting depth: ${r.suelo.profundidad_efectiva_cm} cm.`),
       action:say('Mide hasta roca o capa compactada y registra la evidencia de campo.', 'Measure depth to rock or a compacted layer and record field evidence.'), source:say('Verificación local pendiente', 'Local verification pending')}
    ];
  };
  const fieldSignals = p => {
    const r = p.analysis, t = texts(), moisture = p.rasters?.moisture, ndvi = p.rasters?.vegetation, veg = vegetationSummary(p);
    const crop = rankedCrops(p).find(c => c.componentes) || rankedCrops(p)[0];
    const phScore = crop?.componentes?.ph, textureScore = crop?.componentes?.texture;
    const suitability = score => score == null ? 'attention' : score >= 80 ? 'good' : score >= 50 ? 'attention' : 'risk';
    const cropContext = crop ? say(`Evaluado para ${crop.cultivo}`, `Evaluated for ${crop.cultivo}`) : say('Sin cultivo evaluable', 'No evaluable crop');
    const waiting = entry => entry?.busy ? t.layerLoading : entry?.error || t.notMeasured;
    const phRange = crop?.pH_evaluacion?.rango_optimo_fao;
    return [
      [say('pH de esta parcela', 'Field pH'), String(r.suelo.ph),
       phRange ? say(`${cropContext}: rango óptimo de catálogo ${phRange[0]}–${phRange[1]}; compatibilidad de pH ${phScore ?? '—'}/100. Confirma con análisis de suelo.`, `${cropContext}: catalog optimum ${phRange[0]}–${phRange[1]}; pH compatibility ${phScore ?? '—'}/100. Confirm with a soil test.`) : t.soilNotFertility,
       r.suelo.fuente, suitability(phScore), say('Estimación del suelo', 'Soil estimate'), 'soil'],
      [say('Textura de esta parcela', 'Field texture'), r.suelo.textura,
       say(`Arena ${r.suelo.arena_pct} %, limo ${r.suelo.limo_pct} %, arcilla ${r.suelo.arcilla_pct} %. ${cropContext}: compatibilidad de textura ${textureScore ?? '—'}/100.`, `Sand ${r.suelo.arena_pct} %, silt ${r.suelo.limo_pct} %, clay ${r.suelo.arcilla_pct} %. ${cropContext}: texture compatibility ${textureScore ?? '—'}/100.`),
       r.suelo.fuente, suitability(textureScore), say('Estimación del suelo', 'Soil estimate'), 'soil'],
      [t.vegetationLabel, veg ? `NDVI ${veg.mean.toFixed(2)}` : t.notMeasured,
       veg ? say(`Media de ${veg.count} píxeles válidos dentro del contorno; indica vigor/cobertura, no enfermedades.`, `Mean of ${veg.count} valid pixels within the field; indicates vigor/cover, not diseases.`) : waiting(ndvi),
       veg ? `Sentinel-2 · ${veg.date}` : 'Sentinel-2', 'attention', veg ? say('Observación satelital', 'Satellite observation') : t.notMeasured, 'leaf'],
      [say('Lluvia en la ubicación consultada', 'Rainfall at the queried location'), r.clima.lluvia_mediana_historica_ciclo_90d_mm == null ? t.notMeasured : `${r.clima.lluvia_mediana_historica_ciclo_90d_mm} mm`,
       say(`Mediana histórica de ciclos de 90 días desde el mes ${r.mes_siembra}. ${r.clima.ubicacion_consulta?.resolucion || 'Dato regional de referencia'}`, `Historical median of 90-day cycles starting in month ${r.mes_siembra}. Coarse climate grid: nearby fields may share values.`),
       `${r.clima.fuente}${r.clima.ubicacion_consulta?.latitud != null ? ` (${r.clima.ubicacion_consulta.latitud}, ${r.clima.ubicacion_consulta.longitud})` : ''} · ${r.clima.anios_utilizados.join(', ')}`, 'attention', say('Referencia regional', 'Regional reference'), 'rain'],
      ...(r.clima.reciente_30_dias ? [[say('Últimos 30 días disponibles','Latest 30 available days'), r.clima.reciente_30_dias.lluvia_acumulada_mm == null ? t.notMeasured : `${r.clima.reciente_30_dias.lluvia_acumulada_mm} mm`,
        say(`Periodo ${r.clima.reciente_30_dias.inicio} → ${r.clima.reciente_30_dias.fin}. Racha seca máxima: ${r.clima.reciente_30_dias.racha_seca_max_dias ?? '—'} días (<1 mm/día).`, `Period ${r.clima.reciente_30_dias.inicio} → ${r.clima.reciente_30_dias.fin}. Longest dry spell: ${r.clima.reciente_30_dias.racha_seca_max_dias ?? '—'} days (<1 mm/day).`),r.clima.fuente,'attention',say('Clima por ubicación','Climate by location'),'rain']] : []),
      ...(r.clima.et0_30_dias ? [[say('Demanda atmosférica estimada (ET₀)','Estimated atmospheric demand (ET₀)'),r.clima.et0_30_dias.et0_media_mm_dia == null ? t.notMeasured : `${r.clima.et0_30_dias.et0_media_mm_dia} mm/día`,
        say(`Referencia Hargreaves–Samani ${r.clima.et0_30_dias.inicio} → ${r.clima.et0_30_dias.fin}. No es consumo real del cultivo ni dosis de riego.`, `Hargreaves–Samani reference ${r.clima.et0_30_dias.inicio} → ${r.clima.et0_30_dias.fin}. Not actual crop water use or an irrigation dose.`),'NASA POWER + Hargreaves–Samani','attention',say('Estimación climática','Climate estimate'),'drop']] : []),
      [t.moistureLabel, say('Sin valor numérico', 'No numerical value'),
       moisture?.data ? say('Hay una imagen de humedad SMAP L4 a ~9 km. No se ha extraído un valor numérico para esta parcela; consulta el mapa como contexto regional.', 'A SMAP L4 moisture image at ~9 km is available. No numerical value has been extracted for this field; use the map as regional context.') : waiting(moisture),
       moisture?.data ? `${moisture.data.source} · ${moisture.data.date}` : 'NASA SMAP L4', 'attention', say('Contexto regional', 'Regional context'), 'drop']
    ];
  };

  /* ---------- Dashboard único ---------- */
  function renderDashboard(t) {
    // A. Saludo (el header con logo y controles va fuera del dashboard)
    const hero = `<section class="hero"><div class="hero-text">${tag(parcel().analysis ? t.regionalAnalysis : say('Crea tu parcela', 'Create your field'))}<h1>${t.greeting}</h1><p>${t.subgreeting}</p><div class="hero-pills"><span class="pill">${icon('map',18)}${pName(parcel(),t)}</span>${statusBadge('attention',parcel().busy ? t.loadingAnalysis : parcel().analysis ? say('Análisis preliminar','Preliminary analysis') : say('Pendiente de análisis','Awaiting analysis'))}</div></div><img src="ISOTIPO.svg" alt="" aria-hidden="true" class="hero-mark"></section>`;

    // B. Mi parcela: herramientas + mapa + capas + año | zonas vulnerables + histórico
    const chips = t.layers.map((lbl,i) => `<button class="${state.layer===i?'active':''}" data-act="layer" data-v="${i}" aria-pressed="${state.layer===i}">${icon(LAYER_ICONS[i],20)}${lbl}</button>`).join('');
    const p = parcel();
    const findings = p.analysis ? observations(p).map(o => `<p>${statusBadge(o.level,t[o.level] || t.attention)}<span>${esc(o.text)}</span><strong>${esc(o.action)}</strong><small>${esc(o.source)}</small></p>`).join('') : `<p role="status">${p.busy ? t.loadingAnalysis : p.error ? esc(p.error) : say('Crea una parcela y espera su análisis para ver cuatro hallazgos y acciones basados en sus datos.', 'Create a field and wait for its analysis to see four findings and actions based on its data.')}</p>`;
    const change = p.rasters?.change;
    const histPanel = `<article class="card hist"><b>${say('Cambio observado de vegetación','Observed vegetation change')}</b>${change?.data ? `<p>${esc(change.data.previous_date)} → ${esc(change.data.date)}</p><p><strong>Δ NDVI: ${change.data.statistics?.mean ?? '—'}</strong> · ${change.data.valid_pixels} ${say('píxeles comparables','comparable pixels')}</p><p class="note">${esc(change.data.caution)}</p>` : `<p class="note">${change?.busy ? t.layerLoading : change?.error ? esc(change.error) : say('Selecciona Cambio de vegetación para comparar escenas válidas de esta parcela a intervalos de 30, 60 o 90 días.','Select Vegetation change to compare valid scenes for this field at intervals of 30, 60 or 90 days.')}</p>`}</article>`;
    const slider = '';
    const analyzeControls = p.kind !== 'demo'
      ? `<div class="parcel-analysis-controls"><label>${t.plantMonth}<select data-act="mes" id="plant-month">${Array.from({length:12},(_,i)=>`<option value="${i+1}" ${state.mes===i+1?'selected':''}>${i+1}</option>`).join('')}</select></label><button class="button" data-act="analyze" ${p.busy?'disabled':''}>${icon('trend',18)}${p.busy?t.loadingAnalysis:t.analyzeBtn}</button></div><p class="note">${t.spatialWarning}</p>${p.error?`<p class="error-box" role="alert">${esc(p.error)}</p>`:''}` : `<p class="note">${t.demoPrompt}</p>`;
    const field = `<section id="parcela" class="block">${sectionTitle('map',t.fieldTitle,t.fieldSub,p.analysis?t.regionalAnalysis:say('Crea o selecciona una parcela','Create or select a field'))}<div class="map-layout"><div class="card map-workspace"><div id="p-head">${parcelHead(t)}</div><div class="layer-chips">${chips}</div>${state.layer === 3 && parcel().geojson ? `<label class="comparison-control">${say('Separación mínima entre escenas','Minimum interval between scenes')}<select data-act="comparison-days">${[30,60,90].map(n=>`<option value="${n}" ${(parcel().comparisonDays || 30) === n ? 'selected' : ''}>${n} ${say('días','days')}</option>`).join('')}</select></label>` : ''}<div id="p-map">${fieldMap(t)}</div><div id="legend" class="legend">${legendHtml(t)}</div><div id="p-panel">${parcelPanel(t)}</div><p id="notice" class="notice" role="status">${noticeText(t)}</p>${analyzeControls}${p.geojson ? managementControls(p) : ''}${slider}<input type="file" id="geo" accept=".geojson,.json,application/geo+json,application/json" hidden></div><aside class="side-stack"><article class="card findings">${eyebrow('trend',t.findings)}<h3>${t.findingsTitle}</h3>${findings}</article>${histPanel}</aside></div></section>`;

    // C. Fila central: condiciones del campo | acceso a rotaciones
    const result = p.analysis;
    const conditions = result ? fieldSignals(p) : [];
    const conds = conditions.map(([lbl,val,mean,source,level,badge,signalIcon]) => {
      const m = {icon:signalIcon, level};
      return `<li class="cond"><div class="indicator-icon ${m.level}">${icon(m.icon)}</div><div class="cond-body"><h4>${lbl}</h4><p>${esc(mean)}</p><small>${t.source}: ${esc(source)}</small></div><div class="cond-side"><strong>${esc(val)}</strong>${statusBadge(level,badge)}</div></li>`;
    }).join('');
    const middle = `<section id="condiciones" class="mid-row"><article class="card conditions"><div class="card-heading"><div>${eyebrow('heart',t.conditions)}<h2>${t.conditionsTitle}</h2><p>${esc(pName(p,t))}${result ? ` · ${result.parcela.superficie_ha} ha` : ''}</p></div>${tag(result?t.regionalAnalysis:say('Pendiente de análisis','Awaiting analysis'))}</div><ul class="cond-list">${conds}</ul>${!result ? `<p role="status">${p.busy ? t.loadingAnalysis : say('Las señales aparecerán después de analizar esta parcela.','Signals will appear after analyzing this field.')}</p>` : ''}</article><article class="card cta-card">${icon('rotate',44)}<h2>${t.ctaTitle}</h2><p>${t.ctaText}</p>${button(t.explore,'rotate','scroll:rotaciones',false,'big')}</article></section>`;
    const cropCards = result ? `<section class="block"><div class="section-title"><div class="title-icon">${icon('sprout',30)}</div><div><h2>${t.cropTitle}</h2><p>${t.cropIntro}</p></div></div><div class="crop-grid">${rankedCrops(p).map(c=>`<article class="crop-mini card"><b>${esc(c.cultivo)}</b><span class="status ${c.estado==='verde'?'good':c.estado==='rojo'?'risk':'attention'}">${esc(c.estado)}</span><span>${c.puntaje_provisional??'–'} / 100</span><small>${t.dataConfidence}: ${esc(c.confianza_datos)}</small><p>${esc(c.restricciones_criticas?.[0] || c.recomendaciones?.[0] || say('Faltan datos para evaluar este cultivo.','Missing data to evaluate this crop.'))}</p></article>`).join('')}</div></section>` : '';

    // D. Rotaciones: panel de trabajo + acordeón por cultivo
    const open = k => state.exp.includes(k) ? ' open' : '';
    const sub = (k, ic, title, body) => `<details class="sub" data-k="${k}"${open(k)}><summary>${icon(ic,22)}<span>${title}</span>${icon('chevron',20)}</summary><div class="sub-body">${body}</div></details>`;
    const all = result ? result.rotaciones.estrategias.map((r,i) => [
      r.tipo, r.cultivos.join(' → '), r.fundamento,
      r.beneficios_potenciales.join(' '), t.realMissing,
      r.riesgos_y_limitaciones.join(' '), t.realEvidence
    ]) : [];
    const bestIndex = result ? result.rotaciones.estrategias.findIndex(r => r.tipo === 'sugerida') : -1;
    let n = 0;
    const rots = all.map(([,seq,why,ben,miss,risk,ev],i) => {
      const mat = result ? null : rotMaterials[state.lang][i], isCur = i === state.cur;
      const bar = isCur ? `<span class="status good">${icon('check',17)}${result?t.planSelected:t.isCurrent}</span>` : button(result?t.setForReview:t.setCurrent,'check',`cur:${i}`,true);
      const strategy = result?.rotaciones.estrategias[i];
      const cycleDetails = strategy ? `<p>${say('Puntaje orientativo','Exploratory score')}: ${strategy.puntaje_orientativo ?? '—'}/100 · ${say('Ajuste por temporal','Rainfed adjustment')}: −${strategy.penalizacion_temporal || 0}</p><ul>${strategy.ciclos.map(c => `<li>${esc(c.cultivo)} · ${say('mes','month')} ${c.mes_inicio} · ${c.puntaje_cultivo ?? '—'}/100 · ${esc(c.estado)}</li>`).join('')}</ul>` : '';
      const whyBody = `<p>${esc(why)}</p>${cycleDetails}${infoBlock(t.evidence,'satellite',ev)}${infoBlock(t.benefits,'heart',ben)}<div class="source-chips">${(result?['NASA POWER','SoilGrids','FAO ECOCROP']:ROT_SOURCES[i]).map(tag).join('')}</div>`;
      const riskBody = `${infoBlock(t.missing,'info',miss)}${infoBlock(t.localRisk,'warning',risk)}`;
      const matBody = result ? `<p class="note">${t.realMaterialsUnavailable}</p>` : `<p class="lead">${t.materialsFor}: <b>${mat.crop}</b></p><ul class="check-list">${mat.materials.map(m => `<li>${icon('check',18)}<span>${m}</span></li>`).join('')}</ul><p class="note">${t.materialsNote}</p>`;
      return `<details class="rot ${isCur?'current':''} ${i===bestIndex?'best':''}" data-k="r${i}"${open('r'+i)}><summary><div class="rot-head"><span class="rot-label">${isCur?(result?t.planSelected:t.current):`${t.option} ${++n}`}</span><h3>${t.rotWith} ${seq}</h3>${i===bestIndex?`<b class="best-badge">${t.bestBalance}</b>`:''}${result?`<span class="status ${result.rotaciones.estrategias[i].estado==='verde'?'good':result.rotaciones.estrategias[i].estado==='rojo'?'risk':'attention'}">${result.rotaciones.estrategias[i].estado} · ${t.dataConfidence}: ${result.rotaciones.estrategias[i].confianza_datos}</span>`:''}</div>${icon('chevron',26)}</summary><div class="subs"><div class="rot-actions">${bar}</div>${isCur?workPanel(t, all):''}${sub(`r${i}-why`,'sprout',t.why,whyBody)}${sub(`r${i}-risk`,'warning',t.risksTitle,riskBody)}${sub(`r${i}-mat`,'tractor',t.materialsTitle,matBody)}</div></details>`;
    }).join('');
    const rotations = `<section id="rotaciones" class="block">${sectionTitle('rotate',t.rotationsTitle,t.rotationsSub,result?t.regionalAnalysis:say('Pendiente de análisis','Awaiting analysis'))}<div class="rot-list">${rots || `<p role="status">${!result ? (p.busy ? t.loadingAnalysis : say('Analiza una parcela para obtener rotaciones adaptadas a su suelo y mes de siembra.', 'Analyze a field to get rotations matched to its soil and planting month.')) : say('No se encontraron secuencias compatibles. Revisa las restricciones de los cultivos o cambia el mes de siembra.', 'No compatible sequences were found. Review crop restrictions or change the planting month.')}</p>`}</div>${result ? `<p class="note">${esc(result.rotaciones.advertencias[0])}</p><p class="note">${say('Calculadas para','Calculated for')} ${esc(pName(p,t))} · pH ${result.suelo.ph} · ${esc(result.suelo.textura)} · ${say('mes','month')} ${result.mes_siembra} · ${esc(result.rotaciones.sistema_hidrico || 'sin_declarar')} · ${say('prioridades suelo/agua/diversificación','soil/water/diversity priorities')}: ${Object.values(result.rotaciones.prioridades).join('/')}.</p>` : ''}<div class="decision-note">${icon('people',32)}<p>${t.suggestion}</p></div></section>`;

    return html`<main id="main" tabindex="-1" class="dashboard">${hero}${field}${middle}${cropCards}${rotations}</main>`;
  }

  /* ---------- Páginas aparte (menú "Más información") ---------- */
  const challengeBadge = (t) => `<section class="challenge"><div class="nasa-badge">${icon('satellite',30)}<span>NASA<br><b>SPACE APPS</b></span></div><div><span>${t.challenge}</span><h2>${t.challengeName}</h2><p>${t.challengeNote}</p></div></section>`;

  function nasa(t) {
    const cards = nasaCards(state.lang).map(([src,ti,me,us,up,ic]) => `<article class="card nasa-card"><div class="nasa-head"><span class="nasa-icon">${icon(ic,28)}</span>${tag(src)}</div><h2>${ti}</h2><dl><div><dt>${t.measures}</dt><dd>${me}</dd></div><div><dt>${t.useful}</dt><dd>${us}</dd></div><div><dt>${t.update}</dt><dd>${up}</dd></div></dl></article>`).join('');
    const fusion = t.fusion.map(([ti,txt]) => `<li><b>${ti}</b><p>${txt}</p></li>`).join('');
    const gloss = [t.evap,t.anomaly,t.ndvi,t.soilGloss].map(e => { const c = e.indexOf(':'); return `<p><b>${e.slice(0,c)}:</b>${e.slice(c+1)}</p>`; }).join('');
    return `${sectionTitle('satellite',t.nasaTitle,t.nasaSub)}<div class="nasa-grid">${cards}</div><article class="card together">${icon('satellite',36)}<div><h3>${t.together}</h3><p>${t.togetherText}</p></div></article><section class="grid-2 fusion-row"><article class="card">${eyebrow('rotate',t.fusionTitle)}<p class="lead">${t.fusionIntro}</p><ol class="fusion-steps">${fusion}</ol></article><article class="card">${eyebrow('satellite',t.satField)}<p class="lead">${t.satFieldText}</p><h3>${t.uncertaintyTitle}</h3><p class="uncertainty">${icon('people',24)}<span>${t.uncertainty}</span></p><ul class="plain-list">${t.uncertaintyList.map(x => `<li>${x}</li>`).join('')}</ul></article></section><section class="card glossary">${eyebrow('info',t.glossary)}${gloss}</section>`;
  }

  function about(t) {
    const team = ['Leidy Morayta','Angela Pimienta','Diego Valadez','Ricardo Castillo','María Suárez','Victor Romero'].map(n => `<article class="card person"><div class="avatar" aria-hidden="true">${n[0]}</div><h2>${n}</h2></article>`).join('');
    return `${sectionTitle('people',t.teamTitle,t.teamIntro)}<div class="team-grid">${team}</div><p class="university-line">${t.university}</p>${challengeBadge(t)}`;
  }

  function mission(t) {
    const ic = ['heart','satellite','people'];
    const group = (ti) => `<div class="group-title"><h2>${ti}</h2></div>`;
    const card = (head, ti, tx) => `<article class="card value">${head}<h3>${ti}</h3><p>${tx}</p></article>`;
    const how = t.how.map(([ti,tx],i) => card(`<span class="num">0${i+1}</span>`, ti, tx)).join('');
    const vals = t.values.map((ti,i) => card(icon(ic[i],34), ti, t.valueTexts[i])).join('');
    const next = t.next.map(([w,ti,tx]) => card(tag(w), ti, tx)).join('');
    const commits = t.commits.map(c => `<li>${icon('check',18)}<span>${c}</span></li>`).join('');
    return `<section class="mission-hero">${eyebrow('target',t.mission)}<p class="mission-text">“${t.missionText}”</p><p class="lead">${t.missionLead}</p></section>${group(t.howTitle)}<div class="values">${how}</div>${group(t.valuesTitle)}<div class="values">${vals}</div><section class="card">${eyebrow('heart',t.commitTitle)}<ul class="check-list">${commits}</ul></section>${group(t.nextTitle)}<div class="values">${next}</div>${challengeBadge(t)}`;
  }

  const infoPages = { nasa, about, mission };

  /* ---------- Header, panel lateral y render ---------- */
  const header = (t) => {
    const seg = (items, act, cur) => items.map(([v,lbl]) => `<button class="${cur===v?'active':''}" data-act="${act}" data-v="${v}" aria-pressed="${cur===v}">${lbl}</button>`).join('');
    return `<header class="header"><div class="header-inner"><button class="brand" data-act="home" aria-label="${APP_NAME} — ${t.goHome}"><img src="LOGO.svg" alt="${APP_NAME}" class="brand-logo"></button><div class="header-tools" role="group" aria-label="${t.accessibility}"><div class="seg" role="group" aria-label="${t.langLabel}">${seg([['es','ES'],['en','EN']],'lang',state.lang)}</div><div class="seg" role="group" aria-label="${t.textLabel}">${seg([[0,'A'],[1,'A+'],[2,'A++']],'text',state.text)}</div><button class="tool-button read-button" data-act="read" aria-label="${t.read}">${icon('volume',20)}<span>${t.read}</span></button></div></div></header>`;
  };

  const drawer = (t) => {
    const open = state.drawer;
    const links = INFO_VIEWS.map((p,i) => `<button class="drawer-link ${state.view===p?'active':''}" data-act="view" data-v="${p}">${icon(INFO_ICONS[i])}<span>${t.drawerNav[i]}</span>${icon('arrow',20)}</button>`).join('');
    return `<button class="fab" data-act="drawer" aria-haspopup="dialog" aria-expanded="${open}" aria-controls="drawer" aria-label="${t.more}">${icon('more',22)}<span>${t.more}</span></button><div id="scrim" class="scrim ${open?'open':''}" data-act="drawer-close"></div><aside id="drawer" class="drawer ${open?'open':''}" role="dialog" aria-modal="true" aria-labelledby="drawerTitle" ${open?'':'inert aria-hidden="true"'}><div class="drawer-head"><h2 id="drawerTitle">${t.drawerTitle}</h2><button class="icon-button" data-act="drawer-close" aria-label="${t.closeDrawer}">${icon('close')}</button></div><nav class="drawer-nav">${links}</nav></aside>`;
  };

  const setDrawer = (open) => {
    state.drawer = open;
    document.body.classList.toggle('drawer-open', open);
    const p = document.getElementById('drawer');
    p.classList.toggle('open', open);
    document.getElementById('scrim').classList.toggle('open', open);
    document.querySelectorAll('[data-act="drawer"]').forEach(b => b.setAttribute('aria-expanded', open));
    if (open) { p.removeAttribute('inert'); p.removeAttribute('aria-hidden'); p.querySelector('.icon-button').focus(); }
    else { p.setAttribute('inert',''); p.setAttribute('aria-hidden','true'); }
  };

  const goTo = (view) => {
    if ('speechSynthesis' in window) speechSynthesis.cancel();
    state.view = view;
    state.drawer = false;
    document.body.classList.remove('drawer-open');
    render();
    window.scrollTo(0, 0);
    document.getElementById('main').focus({ preventScroll: true });
  };

  function render(focus) {
    const t = texts(), y = window.scrollY;
    document.documentElement.lang = state.lang;
    document.documentElement.dataset.text = state.text;
    document.title = APP_NAME;
    const page = state.view
      ? `<main id="main" tabindex="-1" class="dashboard info-page">${button(t.back,'arrow','home',true,'back-button')}${infoPages[state.view](t)}</main>`
      : renderDashboard(t);
    disposeMap();
    if (autoZoomParcel) { rememberedMapView = null; autoZoomParcel = false; }
    document.getElementById('app').innerHTML = html`${header(t)}<div class="greca" aria-hidden="true"></div>${page}<div class="greca" aria-hidden="true"></div><footer>${icon('sprout')}<p>${t.footer}</p></footer>${drawer(t)}`;
    if (!state.view) initMap();
    window.scrollTo(0, state.view ? 0 : y);
    if (focus) { const el = document.querySelector(focus); if (el) el.focus({ preventScroll: true }); }
  }

  /* ---------- Eventos ---------- */
  const clickActions = {
    lang: v => { state.lang = v; if ('speechSynthesis' in window) speechSynthesis.cancel(); render(); },
    text: v => { state.text = +v; render(); },
    read: () => readPageAloud(),
    home: () => goTo(null),
    view: v => goTo(v),
    drawer: () => setDrawer(!state.drawer),
    'drawer-close': () => setDrawer(false),
    layer: v => { state.layer = +v; render(); },
    'raster-retry': () => requestRaster(true),
    add: () => { state.draw = state.draw ? null : { pts: [], name: '' }; state.picker = false; state.matrixMode = false; setNotice(); refreshParcel('[data-act="add"]'); },
    pick: () => { state.picker = !state.picker; state.draw = null; state.matrixMode=false; setNotice(); refreshParcel('[data-act="pick"]'); },
    upload: () => document.getElementById('geo').click(),
    matrix: () => { state.matrixMode = !state.matrixMode; state.draw = null; state.picker = false; refreshParcel(); },
    'matrix-apply': () => {
      try {
        const g = matrixGeometry(state.matrixText), fitted = fitRings(g.coordinates);
        addParcel({kind:'matrix',name:'',geojson:g,...fitted},'created');
      } catch(err) { setNotice(typeof err === 'string'?err:'badCoords'); }
    },
    analyze: () => requestAnalysis(parcel()),
    undo: () => { state.draw.pts.pop(); refreshParcel('[data-act="undo"]'); },
    cancel: () => { state.draw = null; refreshParcel('[data-act="add"]'); },
    finish: () => {
      if (state.draw.pts.length >= 3) {
        const pts = state.draw.pts, g = {type:'Polygon',coordinates:[[...pts,pts[0]]]};
        try { addParcel({kind:'drawn',name:state.draw.name,geojson:g,...fitRings(g.coordinates)},'created'); }
        catch(e) { setNotice(typeof e === 'string'?e:'badCoords'); }
      }
    },
    sel: id => { state.sel = id; state.mes = parcel().month ?? 6; state.picker = false; autoZoomParcel=true; state.cur=0; setNotice('selected', pName(parcel(), texts())); render('[data-act="pick"]'); },
    del: id => { const p = state.parcels.find(x => x.id === id); autoZoomParcel=true; state.parcels = state.parcels.filter(x => x.id !== id); if (state.sel === id) state.sel = 'demo'; setNotice('deleted', p.name); render('[data-act="pick"]'); },
    cur: v => { state.cur = +v; state.stage = 0; state.exp = [...new Set([...state.exp, 'r' + v])]; render(`.rot[data-k="r${v}"] summary`); },
    stage: v => { state.stage = +v; render(`[data-act="stage"][data-v="${v}"]`); },
    prev: () => clickActions.stage(state.stage - 1),
    next: () => clickActions.stage(state.stage + 1),
    scroll: id => {
      const calm = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      document.getElementById(id).scrollIntoView({ behavior: calm ? 'auto' : 'smooth' });
    },
  };

  function readPageAloud() {
    if (!('speechSynthesis' in window)) return;
    if (speechSynthesis.speaking) { speechSynthesis.cancel(); return; }
    const u = new SpeechSynthesisUtterance(document.getElementById('main').innerText);
    u.lang = state.lang === 'es' ? 'es-MX' : 'en-US';
    speechSynthesis.speak(u);
  }

  document.addEventListener('click', e => {
    if (mapPoint(e)) return;
    const tgt = e.target.closest('[data-act]');
    if (!tgt || tgt.tagName === 'INPUT') return;
    let a = tgt.dataset.act, v = tgt.dataset.v;
    if (a.includes(':')) [a, v] = a.split(':');
    if (clickActions[a]) clickActions[a](v);
  });

  document.addEventListener('keydown', e => {
    if (!state.drawer) return;
    if (e.key === 'Escape') { setDrawer(false); return; }
    if (e.key !== 'Tab') return;
    const btns = [...document.querySelectorAll('#drawer button')], first = btns[0], last = btns[btns.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  });

  document.addEventListener('input', e => {
    if (e.target.dataset.act === 'pname') { state.draw.name = e.target.value; return; }
    if (e.target.dataset.act === 'coords') { state.matrixText = e.target.value; return; }
    if (e.target.dataset.act !== 'year') return;
    state.year = +e.target.value;
    updateField();
  });

  document.addEventListener('change', e => {
    if (e.target.dataset.act === 'management') {
      const p = parcel(), m = managementFor(p), key = e.target.dataset.key;
      if (key in m.priorities) m.priorities[key] = Number(e.target.value);
      else m[key] = e.target.value || null;
      clearTimeout(p.managementTimer);
      p.managementTimer = setTimeout(() => requestAnalysis(p), 650);
      return;
    }
    if (e.target.dataset.act === 'comparison-days') {
      const p = parcel(); p.comparisonDays = Number(e.target.value);
      if (p.rasters) delete p.rasters.change;
      render(); return;
    }
    if (e.target.id === 'geo') { loadGeo(e.target.files[0]); e.target.value = ''; }
    else if (e.target.dataset.act === 'mes') { state.mes = Number(e.target.value); parcel().month = state.mes; if (parcel().geojson) requestAnalysis(parcel()); }
    else if (e.target.dataset.act === 'have') { state.have[`${state.cur}-${e.target.dataset.v}`] = e.target.checked; updateHave(); }
  });

  // Recuerda qué acordeones están abiertos para no cerrarlos al cambiar idioma o tamaño
  document.addEventListener('toggle', e => {
    const k = e.target.dataset && e.target.dataset.k;
    if (k === undefined) return;
    state.exp = e.target.open ? [...new Set([...state.exp, k])] : state.exp.filter(x => x !== k);
  }, true);

  render();
  fetch(`${API_BASE}/catalogo`).then(r => { if (!r.ok) throw new Error('catalogo'); return r.json(); }).then(data => { cropCatalog = data.cultivos; if (parcel().geojson && !parcel().busy && !state.draw) render(); }).catch(() => { cropCatalog = []; });
})();
