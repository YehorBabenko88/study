/* Reviewed scene revisions, persisted local job references, and reusable results. */
(() => {
  let revision=null, job=null, pollEpoch=0, dirty=false, busy=false;
  const terminal=new Set(['complete','failed','cancelled','timed_out','interrupted','no_image']);
  const output=$('generationStatus');
  const tell=text=>output.textContent=text;
  const remember=()=>{compositionUIState={...compositionUIState,composition_id:revision?.composition_id||compositionUIState.composition_id,revision_id:revision?.revision_id||compositionUIState.revision_id,job_id:job?.job_id||null};scheduleDraft()};
  const call=async(path,body)=>{
    const response=await fetch(path,body===undefined?undefined:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok&&!(data.job_id&&data.status))throw Error(data.error?.message||data.detail||data.reason||(typeof data.error==='string'?data.error:'Запрос не выполнен'));
    return data;
  };
  function parameters(){const values={};for(const [key,id] of [['seed','compositionSeed'],['width','compositionWidth'],['height','compositionHeight'],['steps','compositionSteps']]){const value=Number($(id).value);if(!Number.isSafeInteger(value)||$(id).value.trim()==='')throw Error('Параметр '+key+' должен быть целым числом');values[key]=value}return values}
  function controls(){
    const active=job&&!terminal.has(job.status);
    $('generateComposite').disabled=busy;
    $('saveCompositionRevision').disabled=busy||!revision;
    $('generateReviewedComposition').disabled=busy||!revision||dirty||!!active;
    $('cancelCompositionJob').disabled=busy||!active;
    $('resumeCompositionRequest').hidden=!(revision&&!job&&compositionUIState.request_id&&compositionUIState.request_revision_id===revision.revision_id);
    $('attachCompositionResult').disabled=job?.status!=='complete'||!job?.result?.outputs?.length;
  }
  function markDirty(){dirty=true;if(revision){compositionUIState.reviewEdits={...(compositionUIState.reviewEdits||{}),[revision.revision_id]:{prompt:$('compositionPrompt').value,values:['compositionSeed','compositionWidth','compositionHeight','compositionSteps'].map(id=>$(id).value)}};scheduleDraft()}tell('Есть правки. Сохрани новую версию перед генерацией.');controls()}
  $('compositionPrompt').addEventListener('input',markDirty);
  for(const id of ['compositionSeed','compositionWidth','compositionHeight','compositionSteps'])$(id).addEventListener('input',markDirty);
  function renderRevision(value){
    revision=value;dirty=false;job=null;pollEpoch++;
    $('compositionReview').hidden=false;
    $('sceneDescription').textContent=value.source_description||'';
    $('sceneSources').textContent='Элементов в сцене: '+(value.selected_node_ids?.length||0)+' · исходные карточки сохранены';
    $('compositionPrompt').value=value.effective_prompt||value.user_prompt||value.suggested_prompt||'';
    for(const [key,id,fallback] of [['seed','compositionSeed',0],['width','compositionWidth',512],['height','compositionHeight',512],['steps','compositionSteps',20]])$(id).value=value.parameters?.[key]??fallback;
    const edit=compositionUIState.reviewEdits?.[value.revision_id];if(edit){$('compositionPrompt').value=edit.prompt;['compositionSeed','compositionWidth','compositionHeight','compositionSteps'].forEach((id,i)=>$(id).value=edit.values[i]);dirty=true}
    $('compositionVersion').textContent='Версия '+value.version+' · '+value.revision_id;
    $('compositionResult').replaceChildren();
    $('compositionJobs').replaceChildren();
    for(const item of [...(value.jobs||[])].reverse()){const button=document.createElement('button');button.textContent='Задание: '+item.status;button.onclick=()=>openJob(item.job_id);$('compositionJobs').append(button)}
    remember();controls();
  }
  function insertResult(explicit=false){
    if(job?.status!=='complete'||!job.result?.outputs?.length)return;
    const intent=compositionUIState.autoAttachIntents?.[job.job_id];
    if(!explicit&&(!intent||intent.board_id!==boardId||!intent.source_node_ids.every(id=>nodes.some(n=>n.id===id))))return;
    const applied=compositionUIState.appliedOutputs||{};
    let added=0;
    for(const item of job.result.outputs){
      if(typeof item.asset_id!=='string'||!/^[0-9a-f-]{36}$/i.test(item.asset_id))continue;
      const key=job.job_id+':'+item.asset_id;
      if(nodes.some(n=>n.generation_job_id===job.job_id&&n.image_assets?.includes(item.asset_id))){applied[key]=true;continue}
      if(applied[key]&&!explicit)continue;
      if(!added)snapshot();
      const pos=screenToWorld($('stage').getBoundingClientRect().left+70,$('stage').getBoundingClientRect().top+80);
      const generated={id:ids(),type:'image',text:'Сцена · версия '+revision.version,x:pos.x+added*30,y:pos.y+added*30,image_assets:[item.asset_id],composition_id:revision.composition_id,generation_revision_id:revision.revision_id,generation_job_id:job.job_id,generation_provenance:{sha256:item.sha256||null,selected_node_ids:revision.selected_node_ids||[],reference_images_transmitted:false}};
      nodes.push(generated);
      for(const id of revision.selected_node_ids||[])if(nodes.some(n=>n.id===id))edges.push({from:id,to:generated.id,relation:'association'});
      applied[key]=true;added++;
    }
    compositionUIState.appliedOutputs=applied;if(compositionUIState.autoAttachIntents)delete compositionUIState.autoAttachIntents[job.job_id];
    if(added){draw();tell('Результат добавлен. Исходные карточки сохранены. Сохрани доску для постоянного хранения.')}
    remember();
  }
  function renderJob(value,allowAuto=false){
    job=value;if(terminal.has(value.status)){compositionUIState.request_id=null;compositionUIState.request_revision_id=null;compositionUIState.pendingGeneration=null;compositionUIState.pendingGeneration=null}remember();controls();$('compositionResult').replaceChildren();
    if(value.status==='complete'){
      for(const asset of value.result?.outputs||[]){if(!/^[0-9a-f-]{36}$/i.test(asset.asset_id||''))continue;const img=document.createElement('img');img.src='/v1/board-assets/'+asset.asset_id;img.alt='Результат сцены, версия '+revision.version;img.style.cssText='max-width:100%;max-height:220px';$('compositionResult').append(img)}
      tell('Генерация завершена. Результат доступен в истории.');if(allowAuto)insertResult();
    }else tell('Генерация: '+value.status+(value.result?.error?' · '+(value.result.error.message||value.result.error):''));
  }
  async function watch(id,allowAuto=false){
    const epoch=++pollEpoch;
    for(let attempt=0;attempt<180;attempt++){
      if(epoch!==pollEpoch)return;
      const value=await call('/v1/compositions/jobs/'+encodeURIComponent(id));
      if(epoch!==pollEpoch)return;
      renderJob(value,allowAuto);if(terminal.has(value.status))return;
      await new Promise(resolve=>setTimeout(resolve,1000));
    }
    tell('Ожидание приостановлено. Задание сохранено; открой его снова в истории.');
  }
  async function openJob(id,allowAuto=false){if(!allowAuto){if(compositionUIState.autoAttachIntents)delete compositionUIState.autoAttachIntents[id];compositionUIState.pendingGeneration=null;scheduleDraft()}try{await watch(id,allowAuto)}catch(error){tell('Статус недоступен: '+error.message+' · задание сохранено для повторного открытия.')}}
  async function openComposition(id,wantedRevision,wantedJob,allowAuto=false){
    const result=await call('/v1/compositions/'+encodeURIComponent(id));
    const versions=[...(result.items||[])].sort((a,b)=>b.version-a.version);
    const selectedVersion=versions.find(v=>v.revision_id===wantedRevision)||versions[0];
    if(!selectedVersion)throw Error('Версии сцены не найдены');
    $('compositionVersions').replaceChildren();
    for(const value of versions){const option=document.createElement('option');option.value=value.revision_id;option.textContent='Версия '+value.version;$('compositionVersions').append(option)}
    $('compositionVersions').value=selectedVersion.revision_id;
    renderRevision(selectedVersion);
    const pending=compositionUIState.pendingGeneration;
    const matching=(selectedVersion.jobs||[]).find(item=>item.request_id===compositionUIState.request_id);
    const pendingHere=compositionUIState.request_id&&compositionUIState.request_revision_id===selectedVersion.revision_id;
    const recent=wantedJob||(pendingHere?matching?.job_id:(selectedVersion.jobs||[]).at(-1)?.job_id);
    if(allowAuto&&recent&&matching&&pending){compositionUIState.autoAttachIntents={...(compositionUIState.autoAttachIntents||{}),[recent]:pending};remember();writeDraft()}
    if(recent)await openJob(recent,allowAuto);else controls();
  }
  async function history(){const result=await call('/v1/compositions');$('compositionHistory').replaceChildren();const blank=document.createElement('option');blank.value='';blank.textContent='Выбери сцену';$('compositionHistory').append(blank);for(const value of result.items||[]){const option=document.createElement('option');option.value=value.composition_id;option.textContent='Версия '+value.version+' · '+String(value.source_description||value.composition_id).slice(0,80);$('compositionHistory').append(option)}}
  $('generateComposite').onclick=async()=>{
    const root=nodes.find(n=>n.id===selected);if(!root)return tell('Сначала выбери карточку');
    busy=true;controls();tell('Сборка связанной сцены…');
    try{const value=await call('/v1/compositions',{graph:{nodes,edges},roots:[root.id],direction:'both'});renderRevision(value);compositionUIState.request_id=null;compositionUIState.request_revision_id=null;compositionUIState.pendingGeneration=null;tell('Сцена собрана. Проверь описание, промпт и параметры перед генерацией.');await history()}catch(error){tell('Сцена не собрана: '+error.message)}finally{busy=false;controls()}
  };
  $('saveCompositionRevision').onclick=async()=>{if(!revision)return;busy=true;controls();try{const value=await call('/v1/compositions/revisions/'+encodeURIComponent(revision.revision_id),{user_prompt:$('compositionPrompt').value,parameters:parameters()});if(compositionUIState.reviewEdits)delete compositionUIState.reviewEdits[revision.revision_id];renderRevision(value);compositionUIState.request_id=null;compositionUIState.request_revision_id=null;compositionUIState.pendingGeneration=null;remember();tell('Новая версия сохранена. Генерация использует показанный промпт и параметры.');await history()}catch(error){tell('Версия не сохранена: '+error.message)}finally{busy=false;controls()}};
  $('generateReviewedComposition').onclick=async()=>{if(!revision||dirty)return;busy=true;controls();try{compositionUIState.request_id=compositionUIState.request_revision_id===revision.revision_id&&compositionUIState.request_id?compositionUIState.request_id:ids();compositionUIState.request_revision_id=revision.revision_id;
    compositionUIState.pendingGeneration=compositionUIState.pendingGeneration||{board_id:boardId,source_node_ids:[...(revision.selected_node_ids||[])]};remember();writeDraft();
    const value=await call('/v1/compositions/revisions/'+encodeURIComponent(revision.revision_id)+'/generate',{request_id:compositionUIState.request_id});
    compositionUIState.autoAttachIntents={...(compositionUIState.autoAttachIntents||{}),[value.job_id]:compositionUIState.pendingGeneration};renderJob(value,true);writeDraft();busy=false;controls();if(!terminal.has(value.status))await openJob(value.job_id,true)}catch(error){tell('Запуск не подтверждён: '+error.message+'. Проверь историю или восстанови запуск.')}finally{busy=false;controls()}};
  $('cancelCompositionJob').onclick=async()=>{if(!job)return;busy=true;controls();try{const value=await call('/v1/compositions/jobs/'+encodeURIComponent(job.job_id)+'/cancel',{});pollEpoch++;renderJob(value);tell('Генерация: '+value.status+(value.status==='complete'?' · результат уже завершён':' · отмена обработана'));}catch(error){tell('Отмена не подтверждена: '+error.message)}finally{busy=false;controls()}};
  $('resumeCompositionRequest').onclick=()=>$('generateReviewedComposition').click();
  $('attachCompositionResult').onclick=()=>insertResult(true);
  $('refreshCompositions').onclick=()=>history().catch(error=>tell('История недоступна: '+error.message));
  $('compositionHistory').onchange=()=>{if($('compositionHistory').value)openComposition($('compositionHistory').value).catch(error=>tell(error.message))};
  $('compositionVersions').onchange=()=>{if(revision)openComposition(revision.composition_id,$('compositionVersions').value).catch(error=>tell(error.message))};
  async function resume(){const state={...compositionUIState};if(state.composition_id)try{await openComposition(state.composition_id,state.revision_id,state.job_id,true)}catch(error){tell('Сцена сохранена локально, но пока недоступна: '+error.message)}history().catch(()=>{});}
  window.addEventListener('composition-board-loaded',()=>{pollEpoch++;revision=null;job=null;dirty=false;$('compositionReview').hidden=true;$('compositionResult').replaceChildren();$('compositionJobs').replaceChildren();controls()});
  window.addEventListener('composition-draft-ready',resume);
  if(draftReady)resume();controls();
})();
