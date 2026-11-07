/* Interaction extensions. Model and legacy controls remain in canvas.html. */
'use strict';
const assetPattern = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const stage = $('stage');
const uxStyle = document.createElement('style');
uxStyle.textContent = `
body{height:100dvh;display:flex;flex-direction:column;overflow:hidden}header{height:auto;min-height:62px;flex-wrap:wrap;flex:none}.study-topnav,#draftRecovery{flex:none}.workspace{flex:1;min-height:0;height:auto}.status{max-width:calc(100% - 25px)}
.gallery-item{position:relative;min-width:0;background:#eef4fa;border-radius:8px;touch-action:none;cursor:grab}
.gallery-item img{display:block;min-height:48px;pointer-events:none}.gallery-actions{display:flex;justify-content:center;gap:2px;flex-wrap:wrap}
.gallery-actions button{font-size:12px;padding:4px 6px}.gallery-item.gallery-dragging{opacity:.55;outline:2px solid #2784bd}
.gallery-item.gallery-over{outline:3px solid #20a57e}.gallery-ghost{position:fixed;z-index:10010;pointer-events:none;max-width:120px;max-height:120px;background:white;border:2px solid #2784bd;border-radius:8px}
button:focus-visible,.node:focus-visible,#stage:focus-visible{outline:3px solid #256fbb;outline-offset:3px}button:disabled{opacity:.4;cursor:default}
#draftRecovery{padding:10px;background:#fff4cc;border-bottom:1px solid #d4ad44}#draftRecovery[hidden]{display:none}
#draftStatus{font-size:12px;color:#42617a}dialog{max-width:min(850px,90vw);max-height:85dvh;border:1px solid #bdd0e2;border-radius:14px;padding:20px}dialog::backdrop{background:#142b4999}
#compositionPreview .preview-images{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}#compositionPreview img{width:100%;max-height:300px;object-fit:contain}
@media(max-width:760px){aside{width:155px;padding:9px}header{padding:7px;gap:5px}header input{width:140px}header button{padding:7px}header h1{font-size:16px}}
`;
document.head.append(uxStyle);

function uxButton(label, action, aria) {
    const button = document.createElement('button');
    button.textContent = label;
    if (aria) button.setAttribute('aria-label', aria);
    button.onclick = event => { event.stopPropagation(); action(); };
    return button;
}
function focusCard(id) {
    [...document.querySelectorAll('.node')].find(el => el.dataset.id === id)?.focus({preventScroll:true});
}
function galleryAssets(node) { return node.image_assets || (node.asset_id ? [node.asset_id] : []); }
function editGallery(node, from, to) {
    const assets = [...galleryAssets(node)];
    if (from < 0 || from >= assets.length || (to !== null && (to < 0 || to >= assets.length || from === to))) return;
    snapshot();
    const [asset] = assets.splice(from, 1);
    if (to !== null) assets.splice(to, 0, asset);
    node.image_assets = assets;
    delete node.asset_id;
    draw(); focusCard(node.id);
    status(to === null ? 'Образ убран из карточки. Файл сохранён; действие можно отменить.' : 'Порядок образов изменён.');
}

let galleryDrag = null;
function cancelGallery() {
    if (!galleryDrag) return;
    galleryDrag.ghost.remove(); galleryDrag = null;
    document.querySelectorAll('.gallery-dragging,.gallery-over').forEach(el => el.classList.remove('gallery-dragging','gallery-over'));
}
function renderGallery(node, el) {
    if (!galleryAssets(node).length) return;
    el.querySelector('.image-gallery')?.remove(); el.querySelector('.image-count')?.remove();
    // A legacy primary asset becomes the same editable gallery, without mutating data on draw.
    if (node.asset_id) el.querySelectorAll(':scope > img').forEach(img => { if (img.src.includes('/v1/board-assets/')) img.remove(); });
    const gallery = document.createElement('div'); gallery.className = 'image-gallery';
    galleryAssets(node).forEach((asset, index) => {
        const item = document.createElement('div'); item.className = 'gallery-item'; item.dataset.index = index;
        const image = document.createElement('img'); image.src = '/v1/board-assets/' + asset;
        image.alt = 'Образ ' + (index+1); image.draggable = false;
        item.append(image);
        const controls = document.createElement('div'); controls.className = 'gallery-actions';
        const prev = uxButton('←', () => editGallery(node,index,index-1), `Переместить образ ${index+1} влево`);
        const next = uxButton('→', () => editGallery(node,index,index+1), `Переместить образ ${index+1} вправо`);
        prev.disabled = index===0; next.disabled = index===galleryAssets(node).length-1;
        controls.append(prev,next,uxButton('×', () => editGallery(node,index,null), `Удалить образ ${index+1}`));
        item.append(controls);
        item.addEventListener('dblclick', event => event.stopPropagation());
        item.addEventListener('pointerdown', event => {
            if (event.button!==0 || event.target.closest('button')) return;
            event.preventDefault(); event.stopPropagation();
            const ghost = image.cloneNode(); ghost.className = 'gallery-ghost';
            ghost.style.left = event.clientX+12+'px'; ghost.style.top = event.clientY+12+'px';
            document.body.append(ghost); item.classList.add('gallery-dragging');
            galleryDrag = {node,index,target:index,ghost,item}; item.setPointerCapture(event.pointerId);
        });
        item.addEventListener('pointermove', event => {
            if (galleryDrag?.item!==item) return;
            galleryDrag.ghost.style.left = event.clientX+12+'px'; galleryDrag.ghost.style.top = event.clientY+12+'px';
            galleryDrag.target = null;
            gallery.querySelectorAll('.gallery-item').forEach(candidate => {
                const r=candidate.getBoundingClientRect(), over=event.clientX>=r.left&&event.clientX<r.right&&event.clientY>=r.top&&event.clientY<r.bottom;
                candidate.classList.toggle('gallery-over',over);
                if(over) galleryDrag.target=Number(candidate.dataset.index);
            });
        });
        item.addEventListener('pointerup', () => {
            if(galleryDrag?.item!==item) return;
            const to=galleryDrag.target; cancelGallery(); if(to!==null) editGallery(node,index,to);
        });
        item.addEventListener('pointercancel',cancelGallery);
        gallery.append(item);
    });
    el.insertBefore(gallery,el.querySelector('.footer'));
}

// Use actual painted DOM geometry, including transformed scale, image heights and stacking order.
nodeAtCanvas = function(x,y,exclude) {
    const r=stage.getBoundingClientRect();
    if(x<r.left||x>=r.right||y<r.top||y>=r.bottom) return undefined;
    for(const hit of document.elementsFromPoint(x,y)) {
        const el=hit.closest('.node');
        if(el && el.dataset.id!==exclude) return nodes.find(n=>n.id===el.dataset.id);
    }
};

let batchDepth=0;
const legacySnapshot=snapshot;
snapshot=function(){ if(!batchDepth) legacySnapshot(); };
function atomic(action) {
    const before=JSON.stringify({nodes,edges}); snapshot(); batchDepth++;
    try { action(); } finally {
        batchDepth--;
        if(before===JSON.stringify({nodes,edges})) undoStack.pop();
    }
}
for(const id of ['split','syllables','speechGraph']) {
    // Async speechGraph has its own awaits; its grouping is implemented at the add loop.
    if(id==='speechGraph') continue;
    const control=$(id), handler=control.onclick;
    control.onclick=function(event){atomic(()=>handler.call(control,event));};
}

function cancelNodeDrag() {
    if(drag?.kind==='node') {
        const node=nodes.find(n=>n.id===drag.id);
        if(node){node.x=drag.x;node.y=drag.y;}
        offset={...drag.offset};
        drag=null; stage.classList.remove('drag-active');
        $('world').style.transform=`translate(${offset.x}px,${offset.y}px) scale(${scale})`; draw();
    } else if(drag?.kind==='pan') { offset={x:drag.x,y:drag.y};drag=null;stage.classList.remove('panning');renderTransform(); }
}
function markDropTarget(target) {
    document.querySelectorAll('.node').forEach(el=>el.classList.toggle('drop-target',el.dataset.id===target?.id));
}
document.addEventListener('pointermove',event=>{
    if(drag?.kind!=='node')return;
    const node=nodes.find(n=>n.id===drag.id);
    if(node?.type==='image'&&galleryAssets(node).length)markDropTarget(nodeAtCanvas(event.clientX,event.clientY,node.id));
});
function finishNodeDrag(node,event) {
    if(drag?.kind!=='node'||drag.id!==node.id)return;
    const current=drag;
    const moved=Math.hypot(node.x-current.x,node.y-current.y)>3;
    const target=moved&&node.type==='image'&&galleryAssets(node).length?nodeAtCanvas(event.clientX,event.clientY,node.id):null;
    drag=null;
    if(target){
        node.x=current.x;node.y=current.y;
        batchDepth++;
        try {for(const asset of galleryAssets(node))attachImage(target,asset);}finally{batchDepth--;}
    }else if(moved&&detachOnFling(node,node.x-current.x,node.y-current.y,Date.now()-current.started)){
        status('Связи разорваны быстрым движением от соседних карточек.');
    }
    if(current.before!==JSON.stringify({nodes,edges})){
        undoStack.push(current.before);if(undoStack.length>40)undoStack.shift();redoStack=[];
    }
    stage.classList.remove('drag-active');markDropTarget(null);draw();scheduleDraft();
}
document.addEventListener('keydown',event=>{
    if(event.key==='Escape'){ cancelGallery();cancelNodeDrag();linkMode=false;linkStart=null; }
},true);
window.addEventListener('blur',()=>{cancelGallery();cancelNodeDrag();});

const legacyDraw=draw;
draw=function(renderAll=false){
    const focused=document.activeElement?.closest('.node')?.dataset.id;
    legacyDraw(renderAll);
    document.querySelectorAll('.node').forEach(el=>{
        const node=nodes.find(n=>n.id===el.dataset.id);
        el.tabIndex=0;el.setAttribute('role','group');el.setAttribute('aria-label',node.type+': '+node.text);
        renderGallery(node,el);
        el.querySelector('.footer button').onclick=()=>{
            if(window.parent!==window) window.parent.postMessage({kind:'study-keyboard-transfer',payload:{kind:'node',id:node.id,type:node.type,text:node.text,asset_id:galleryAssets(node)[0]||null}},location.origin);
            else status('Открой «Две панели», чтобы передать карточку в 3D Lab.');
        };
        el.addEventListener('keydown',event=>{
            if(event.target!==el) return;
            if(event.key==='Enter'||event.key===' '){event.preventDefault();select(node);return;}
            if(event.key==='Delete'){event.preventDefault();select(node);$('remove').click();return;}
            const delta={ArrowLeft:[-1,0],ArrowRight:[1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[event.key];
            if(delta){event.preventDefault();snapshot();const step=event.shiftKey?50:10;node.x+=delta[0]*step;node.y+=delta[1]*step;selected=node.id;draw();focusCard(node.id);}
        });
    });
    if(focused) focusCard(focused);
    queueMicrotask(scheduleDraft);
};

// A split-pane drag paints the source card continuously; the model changes once on drop.
window.addEventListener('message',event=>{
    if(event.origin!==location.origin||event.source!==window.parent||event.data?.kind!=='study-node-preview') return;
    const d=event.data, node=nodes.find(n=>n.id===d.id), el=[...document.querySelectorAll('.node')].find(el=>el.dataset.id===d.id);
    if(!node||!el)return;
    el.classList.toggle('dragging',!!d.active);
    el.style.left=(node.x+(d.active?d.dx/scale:0))+'px';el.style.top=(node.y+(d.active?d.dy/scale:0))+'px';
});

// Preview never creates nodes or edges, and uses the same source selection as the legacy composition.
const preview=uxButton('Предпросмотр композиции',()=>{
    const base=nodes.find(n=>n.id===selected);if(!base)return status('Выбери карточку');
    const neighbors=edges.filter(e=>e.from===base.id||e.to===base.id).map(e=>nodes.find(n=>n.id===(e.from===base.id?e.to:e.from))).filter(Boolean);
    const assets=[...new Set([base,...neighbors].slice(0,12).flatMap(galleryAssets))].slice(0,12);
    if(!assets.length)return status('В карточке и её соседях пока нет изображений');
    const images=$('previewImages');images.replaceChildren();
    assets.forEach((asset,i)=>{const img=document.createElement('img');img.src='/v1/board-assets/'+asset;img.alt='Образ композиции '+(i+1);images.append(img);});
    $('compositionPreview').showModal();
});
preview.id='previewComposition';$('composeImages').before(preview);
const dialog=document.createElement('dialog');dialog.id='compositionPreview';dialog.setAttribute('aria-labelledby','previewTitle');
dialog.innerHTML='<h2 id="previewTitle">Предпросмотр композиции</h2><p>Порядок образов сохранён. Исходные карточки остаются на доске.</p><div id="previewImages" class="preview-images"></div>';
dialog.append(uxButton('Создать композицию',()=>{dialog.close();$('composeImages').click();}),uxButton('Закрыть',()=>dialog.close()));document.body.append(dialog);

// Viewport controls: anchored zoom, genuine fit, wheel pan with Ctrl/Meta zoom.
stage.tabIndex=0;stage.setAttribute('aria-label','Доска: стрелки — прокрутка, плюс и минус — масштаб, Home — показать всё');
$('zin').setAttribute('aria-label','Увеличить масштаб');$('zout').setAttribute('aria-label','Уменьшить масштаб');
$('title').maxLength=100;
function fitBoard(){
    if(!nodes.length)return;
    draw(true); // Measure virtualized cards before choosing a viewport scale.
    const dimensions=nodes.map(n=>{const el=[...document.querySelectorAll('.node')].find(el=>el.dataset.id===n.id);return {x:n.x,y:n.y,w:el?.offsetWidth||250,h:el?.offsetHeight||180};});
    const minX=Math.min(...dimensions.map(n=>n.x)),minY=Math.min(...dimensions.map(n=>n.y));
    const width=Math.max(...dimensions.map(n=>n.x+n.w))-minX,height=Math.max(...dimensions.map(n=>n.y+n.h))-minY;
    scale=Math.max(.2,Math.min(3,(stage.clientWidth-40)/width,(stage.clientHeight-40)/height));
    offset={x:(stage.clientWidth-width*scale)/2-minX*scale,y:(stage.clientHeight-height*scale)/2-minY*scale};renderTransform();
}
$('fit').onclick=fitBoard;
stage.addEventListener('wheel',event=>{
    event.preventDefault();event.stopImmediatePropagation();
    if(event.ctrlKey||event.metaKey){const old=scale;scale=Math.min(3,Math.max(.2,scale*Math.exp(-event.deltaY*.002)));const r=stage.getBoundingClientRect(),x=event.clientX-r.left,y=event.clientY-r.top;offset.x=x-(x-offset.x)*scale/old;offset.y=y-(y-offset.y)*scale/old;}
    else {offset.x-=event.shiftKey?event.deltaY:event.deltaX;offset.y-=event.shiftKey?event.deltaX:event.deltaY;}
    renderTransform();
},{passive:false,capture:true});
stage.addEventListener('keydown',event=>{
    if(event.target!==stage)return;
    const deltas={ArrowLeft:[60,0],ArrowRight:[-60,0],ArrowUp:[0,60],ArrowDown:[0,-60]};
    if(deltas[event.key]){event.preventDefault();offset.x+=deltas[event.key][0];offset.y+=deltas[event.key][1];renderTransform();}
    else if(['+','=','-','Home'].includes(event.key)){event.preventDefault();if(event.key==='Home')fitBoard();else zoom(event.key==='-'?.8:1.2);}
});
const unlink=uxButton('Убрать связи выбранной карточки',()=>{if(!selected)return;atomic(()=>{edges=edges.filter(e=>e.from!==selected&&e.to!==selected);draw();});});
$('connect').after(unlink);

// Local drafts: explicit recovery, optimistic revision checking, no destructive cleanup.
const draftPrefix='study.canvas.draft.v1:';
let draftKey=null,draftRaw=null,draftBlocked=false,draftTimer=null,lastDraftState=null,newDraftSlot='new';
try {newDraftSlot=sessionStorage.getItem('study.canvas.newDraftSlot')||'new';} catch { /* optional tab-local copy selection */ }
const draftStatus=document.createElement('span');draftStatus.id='draftStatus';draftStatus.setAttribute('role','status');document.querySelector('header').append(draftStatus);
const recovery=document.createElement('section');recovery.id='draftRecovery';recovery.hidden=true;recovery.setAttribute('aria-label','Восстановление черновика');
const recoveryText=document.createElement('span');recovery.append(recoveryText);
const restoreButton=uxButton('Восстановить черновик',()=>restoreDraft(false));restoreButton.id='restoreDraft';
const copyButton=uxButton('Восстановить как новую доску',()=>restoreDraft(true));
const keepButton=uxButton('Продолжить с текущей доской',()=>{
    try {if(draftRaw!==null)localStorage.setItem(draftKey+':backup:'+Date.now(),draftRaw);draftRaw=localStorage.getItem(draftKey);draftBlocked=false;recovery.hidden=true;lastDraftState=null;flushDraft();}
    catch{draftStatus.textContent='Не удалось сохранить резервную копию. Черновик не изменён.';}
});
const downloadButton=uxButton('Скачать сохранённый черновик',()=>{
    if(draftRaw===null)return;
    const url=URL.createObjectURL(new Blob([draftRaw],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='study-draft.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
recovery.append(restoreButton,copyButton,keepButton,downloadButton);document.querySelector('.workspace').before(recovery);
function boardState(){return {title:$('title').value,boardId,nodes:nodes.map(({_dragStarted,...node})=>node),edges,view:{scale,offset}};}
function validDraft(raw){
    const d=JSON.parse(raw), b=d.board;
    if(d.version!==1||!b||typeof b.title!=='string'||b.title.length>100||!(b.boardId===null||assetPattern.test(b.boardId))||!Array.isArray(b.nodes)||b.nodes.length>10000||!Array.isArray(b.edges)||b.edges.length>30000)throw Error('format');
    const ids=new Set();
    for(const n of b.nodes){
        if(!n||typeof n.id!=='string'||n.id.length>80||ids.has(n.id)||!['letter','word','syllable','image','sentence','note','action'].includes(n.type)||typeof n.text!=='string'||n.text.length>5000||!['x','y'].every(k=>Number.isFinite(n[k])&&Math.abs(n[k])<=100000))throw Error('node');
        ids.add(n.id);
        if(n.asset_id!==undefined&&!assetPattern.test(n.asset_id))throw Error('asset');
        if(n.scene_id!==undefined&&(n.type!=='image'||!assetPattern.test(n.scene_id)))throw Error('scene');
        if(n.image_assets!==undefined&&(!Array.isArray(n.image_assets)||n.image_assets.length>12||new Set(n.image_assets).size!==n.image_assets.length||!n.image_assets.every(a=>typeof a==='string'&&assetPattern.test(a))))throw Error('gallery');
    }
    if(!b.edges.every(e=>e&&ids.has(e.from)&&ids.has(e.to)&&['association','part_of','sequence','meaning','sound','action'].includes(e.relation||'association')))throw Error('edge');
    if(!b.view||!Number.isFinite(b.view.scale)||b.view.scale<.2||b.view.scale>3||!Number.isFinite(b.view.offset?.x)||!Number.isFinite(b.view.offset?.y))throw Error('view');
    return d;
}
function showRecovery(raw,conflict=false){
    draftRaw=raw;draftBlocked=true;recovery.hidden=false;
    let valid=true;try{validDraft(raw);}catch{valid=false;}
    restoreButton.disabled=!valid;copyButton.disabled=!valid;
    recoveryText.textContent=valid?(conflict?'Черновик изменён в другой вкладке. Выбери версию. ':'Найден локальный черновик. Восстановить его? '):'Черновик повреждён или имеет неизвестный формат. Исходная запись сохранена. ';
    draftStatus.textContent='Автосохранение приостановлено до выбора версии';
}
function activateDraftKey(){
    const key=draftPrefix+(boardId||newDraftSlot);if(key===draftKey)return;
    draftKey=key;draftBlocked=false;lastDraftState=null;recovery.hidden=true;
    try{draftRaw=localStorage.getItem(key);if(draftRaw!==null)showRecovery(draftRaw);}
    catch{draftBlocked=true;draftStatus.textContent='Локальное хранилище недоступно. Используй «Сохранить».';}
}
function scheduleDraft(){
    activateDraftKey();clearTimeout(draftTimer);
    if(!draftBlocked&&!drag)draftTimer=setTimeout(flushDraft,450);
}
function flushDraft(){
    activateDraftKey();if(draftBlocked||drag)return;
    try{
        const state=JSON.stringify(boardState());if(state===lastDraftState)return;
        const current=localStorage.getItem(draftKey);
        if(current!==draftRaw){showRecovery(current,true);return;}
        const raw=JSON.stringify({version:1,savedAt:new Date().toISOString(),board:JSON.parse(state)});validDraft(raw);
        // Backup is written first: quota failures never destroy the previous good version.
        if(draftRaw!==null)localStorage.setItem(draftKey+':previous',draftRaw);
        localStorage.setItem(draftKey,raw);draftRaw=raw;lastDraftState=state;draftStatus.textContent='Черновик сохранён на этом устройстве';
    }catch{draftStatus.textContent='Черновик не сохранён: проверь место в браузере. Используй «Сохранить».';}
}
function restoreDraft(asCopy){
    try{
        const d=validDraft(draftRaw).board;
        // Preserve current in-memory work before replacing it.
        localStorage.setItem(draftKey+':before-restore:'+Date.now(),JSON.stringify({version:1,savedAt:new Date().toISOString(),board:boardState()}));
        nodes=d.nodes;edges=d.edges;$('title').value=d.title;boardId=asCopy?null:d.boardId;
        scale=d.view.scale;offset={...d.view.offset};selected=null;undoStack=[];redoStack=[];
        if(asCopy){
            newDraftSlot='copy-'+ids();
            sessionStorage.setItem('study.canvas.newDraftSlot',newDraftSlot);
            draftKey=draftPrefix+newDraftSlot;draftRaw=null;
        }
        draftBlocked=false;recovery.hidden=true;lastDraftState=null;renderTransform();status('Черновик восстановлен. Серверная доска не перезаписана.');
    }catch{draftStatus.textContent='Восстановление не выполнено. Черновик сохранён без изменений.';}
}
$('title').addEventListener('input',scheduleDraft);
window.addEventListener('pagehide',flushDraft);
document.addEventListener('visibilitychange',()=>{if(document.hidden)flushDraft();});
window.addEventListener('storage',event=>{if(event.key===draftKey&&event.newValue!==draftRaw)showRecovery(event.newValue,true);});
// Flush the departing board before a board-list click starts its asynchronous load.
$('boards').addEventListener('click',flushDraft,true);
$('save').addEventListener('click',flushDraft,true);

// PDF processing contract shared with Agent D: errors are recoverable, empty pages are explicit.
const pdfRetry=uxButton('Повторить OCR ошибочных страниц',()=>processPDF(true));pdfRetry.id='pdfRetry';
$('pdfNext').after(pdfRetry);
function describePDF(job){
    const progress=`${job.next_page??0}/${job.page_count??'?'} страниц`;
    if(job.status==='ocr_error')return `Ошибка OCR · ${progress}. Проверь Tesseract и немецкий язык (deu), затем нажми «Повторить OCR». Исходный PDF сохранён.`;
    if(job.status==='unavailable')return 'Обработка PDF недоступна: '+(job.reason||'проверь зависимости');
    if(job.status==='failed')return 'Обработка не завершена: '+(job.error||'неизвестная ошибка');
    if(Number.isInteger(job.retry_pages)&&job.retry_pages>0)return progress+` · Требуют OCR: ${job.retry_pages}. Нажми «Повторить OCR» ещё раз; успешные страницы сохранены.`;
    return progress+' · '+(job.status==='complete'?'обработка завершена':job.status);
}
async function processPDF(retry){
    const id=$('documentList').value;if(!id)return;
    $('pdfNext').disabled=true;pdfRetry.disabled=true;$('pdfStatus').textContent=retry?'Повторное распознавание...':'Обработка страниц...';
    try{
        const result=await post('/v1/documents/'+encodeURIComponent(id)+'/process',retry?{batch:2,ocr:true,retry:true}:{batch:2,ocr:$('pdfOcr').checked});
        await refreshDocuments();$('documentList').value=id;$('pdfStatus').textContent=describePDF(result);
    }catch(error){$('pdfStatus').textContent='PDF: '+error.message;}
    finally{$('pdfNext').disabled=false;pdfRetry.disabled=false;}
}
$('pdfNext').onclick=()=>processPDF(false);
$('pdfPage').onclick=async()=>{
    const id=$('documentList').value;if(!id)return;
    try{
        const index=Number($('pageNumber').value)-1;
        if(!Number.isInteger(index)||index<0)throw Error('Укажи номер страницы от 1');
        const page=await api('/v1/documents/'+encodeURIComponent(id)+'/pages/'+index);
        if(['ocr_error','ocr_unavailable'].includes(page.method))return $('pdfStatus').textContent='Ошибка OCR этой страницы. Нажми «Повторить OCR». Исходник сохранён.';
        if(!page.text?.trim())return $('pdfStatus').textContent=page.method==='ocr_no_text'?'OCR завершён: текст на странице не найден. Проверь качество исходного скана.':'На странице нет текстового слоя. Включи OCR или нажми «Повторить OCR».';
        const words=page.text.trim().split(/\s+/u);if(words.length>500)throw Error('Страница содержит более 500 слов: разбей на части');
        const pos=screenToWorld(stage.getBoundingClientRect().left+110,stage.getBoundingClientRect().top+100);
        atomic(()=>{
            const parent={id:ids(),type:'sentence',text:'Страница '+(index+1),x:pos.x,y:pos.y};nodes.push(parent);let previous=null;
            words.forEach((text,i)=>{const node={id:ids(),type:'word',text,x:pos.x+(i%5)*205,y:pos.y+150+Math.floor(i/5)*115};nodes.push(node);edges.push({from:parent.id,to:node.id,relation:'part_of'});if(previous)edges.push({from:previous.id,to:node.id,relation:'sequence'});previous=node;});draw();
        });
        $('pdfStatus').textContent=`Страница ${index+1} добавлена: ${words.length} карточек.`;
    }catch(error){$('pdfStatus').textContent='PDF: '+error.message;}
};
draw();activateDraftKey();
