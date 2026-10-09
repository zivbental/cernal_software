/** Built SPA browser contracts with isolated HTTP fixtures; no user records. */
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
import { readFile } from 'node:fs/promises';
import { resolve, extname } from 'node:path';
import { chromium } from 'playwright';
const root = resolve(import.meta.dirname, '../../src/static/app');
const server = createServer(async (req, res) => {
  try {
    const path = req.url.startsWith('/static/app/assets/') ? req.url.split('?')[0].replace('/static/app', '') : '/index.html';
    const body = await readFile(root + path);
    res.setHeader('Content-Type', ({'.js':'application/javascript','.css':'text/css','.svg':'image/svg+xml'})[extname(path)] ?? 'text/html');
    res.end(body);
  } catch { res.writeHead(404).end(); }
});
await new Promise((done) => server.listen(0, '127.0.0.1', done));
const origin = `http://127.0.0.1:${server.address().port}`;
const browser = await chromium.launch();
const page = await browser.newPage();
const errors=[];
page.on('pageerror', (error) => errors.push(error.message));
let failSubmit=true, submitStatus=null, empty=false, historyError=false;
let notes=[];
let detailGate=null, detailError=false;
const dataset={id:"mock-data",name:"Wizard fixture",validation_status:"VALID",size_bytes:1000,validation_report:{rows:2,columns:[],errors:[],warnings:[]}};
const queries=[];
const submissions=[];
const families=['toehold','prokaryotic_toehold','eukaryotic_toehold','toehold_and','crispr'];
const version={app_version:'test', engine:'LocalEngine', engine_version:'test', reviewer_login_enabled:false,
 gate_families:families.map(name=>({name,label:name,description:name,available:!['toehold_and','crispr'].includes(name)})),
 supported_hosts:['ecoli','yeast','human','c_acnes'],family_hosts:{toehold:['ecoli','c_acnes'],prokaryotic_toehold:['ecoli','c_acnes'],eukaryotic_toehold:['human','yeast']},supported_outputs:['gfp','mcherry','luciferase','ampr','kanr','other'],output_hosts:{gfp:['ecoli','yeast','human','c_acnes'],mcherry:['ecoli','yeast','human','c_acnes'],luciferase:['ecoli','yeast','human','c_acnes'],other:['ecoli','yeast','human','c_acnes'],ampr:['ecoli'],kanr:['ecoli']},backbone_hosts:{psb1c3:['ecoli']},input_modes:['de','direct','gene'],limits:{},constraints:{},scoring_profiles:['default'],available_backbones:[{key:'psb1c3',name:'pSB1C3',length_bp:2070}]};
const run={id:'mock-run',status:'COMPLETED',organism:'Human',engine_version:'test',seed:42,
 params_snapshot:{payload:{outputs:['gfp','other']}},warnings:['UNIQUE_RUN_WARNING: exports held'],counts:{candidates:7907,artifacts:0}};
const otherRun={...run,id:'other-run',params_snapshot:{top_n:10,payload:{outputs:['gfp']}}};
const candidate=(rank)=>({id:`candidate-${rank}`,run_id:'mock-run',rank,engine_ref:`cand-${rank}`,overall_score:0.7,gate_family:'eukaryotic_toehold',logic_type:'SINGLE',summary:`Candidate ${rank}`,warnings:['UNIQUE_CANDIDATE_WARNING'],is_rejected:false,rejection_reason:'',output:'GFP'});
await page.route('**/api/**', async route=>{
 const url=new URL(route.request().url()), path=url.pathname;
 let body=[];
 if(path==='/api/auth/me') body={id:1,username:'browser-test',is_staff:false};
 else if(path==='/api/auth/csrf') return route.fulfill({status:204,headers:{'set-cookie':'csrftoken=test; Path=/'}});
 else if(path==='/api/version') body=version;
 else if(path==='/api/datasets') body=[dataset];
 else if(path.endsWith('/preview')) body={rows:[],total_rows:0,truncated:false};
 else if(path==='/api/reference-genes/resolve') body={gene_id:'TEST_GENE',gene_symbol:'TestGene',sequence:'AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA',transcript_id:'TEST_TRANSCRIPT',selection_method:'fixture'};
 else if(path==='/api/runs' && route.request().method()==='POST') {
   submissions.push(route.request().postDataJSON());
   if(submitStatus) return route.fulfill({status:submitStatus,json:{error:{message:`Injected submission ${submitStatus}`}}});
   if(failSubmit) return route.abort('failed');
   body={...run,status:'QUEUED'};
 } else if(path==='/api/runs') {
   if(historyError) return route.fulfill({status:500,json:{error:{message:'Injected history failure'}}});
   body=[];
 } else if(path==='/api/runs/mock-run/detail') {
   if(detailGate) await detailGate;
   if(detailError) return route.fulfill({status:500,json:{error:{message:'Injected frozen configuration failure'}}});
   body=run;
 } else if(path==='/api/runs/mock-run') body=run;
 else if(path==='/api/runs/other-run' || path==='/api/runs/other-run/detail') body=otherRun;
 else if(path==='/api/runs/mock-run/candidates' || path==='/api/runs/other-run/candidates') {
   queries.push(url.searchParams);
   const offset=Number(url.searchParams.get('offset')??0), count=empty?0:Math.min(7907,Number(url.searchParams.get('top_n')??7907));
   const output=url.searchParams.get('output')??'all outputs';
   const sort=url.searchParams.get('sort')??'rank';
   body={count,items:Array.from({length:Math.min(50,Math.max(0,count-offset))},(_,i)=>({
     ...candidate(offset+i+1),
     // Make query completion observable in the rendered rows, even when page counts match.
     summary:`Candidate ${offset+i+1} · ${output} · ${sort}`,
   }))};
 } else if(path.endsWith('/annotations')) {
   if(route.request().method()==='POST') notes.push({id:'review-note',author:'browser-test',created_at:'2026-10-08T00:00:00Z',...route.request().postDataJSON()});
   body=route.request().method()==='POST'?notes.at(-1):notes;
 } else if(path==='/api/annotations/review-note') { notes=[]; return route.fulfill({status:204}); }
 else if(path.startsWith('/api/candidates/') && !path.endsWith('/annotations')) {
   const rank=Number(path.split('-').at(-1));
   body={...candidate(rank),triggers:{features:[{gene_id:'ENSG-test',transcript_id:'ENST-test'}]},design:{switch_sequence:'ACGU',structure:'....',plasmid_segments:[],logic_graph:{genes:[],output:'GFP'}},metrics:[{name:'predicted_success_rate',raw_value:0.9,normalized_value:0.9,weight:1,direction:'HIGHER_BETTER'},{name:'orthogonality',raw_value:null,normalized_value:null,weight:1,direction:'HIGHER_BETTER'}]};
 }
 return route.fulfill({json:body});
});
try {
 await page.goto(origin+'/compile');
 await page.getByRole('heading',{name:'Biological Compiler'}).waitFor();
 await page.getByRole('button',{name:'Direct Trigger mRNA'}).click();
 const sequence=page.getByRole('textbox',{name:'Trigger sequence'});
 await sequence.fill('>ACTG header\nACGUNNNNACGU');
 assert.equal(await sequence.inputValue(),'>ACTG header\nACGUNNNNACGU');
 await page.getByText("Invalid nucleotide 'N' at position 5",{exact:false}).waitFor();
 assert(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled());
 await sequence.fill('>record\nAACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA');
 assert(!(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled()));
 assert(!(await page.getByRole('button',{name:/mCherry/}).isDisabled()));
 assert(!(await page.getByRole('button',{name:/Luciferase/}).isDisabled()));
 assert(await page.getByRole('button',{name:/Apoptosis inducer/}).isDisabled());
 await page.getByRole('button',{name:'Compile & Optimize'}).click();
 await page.getByRole('alert').filter({hasText:'Failed to fetch'}).waitFor();
 assert.equal(await sequence.inputValue(),'>record\nAACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA');
 assert.deepEqual(submissions.at(-1).params.budget,{max_designs:20});
 assert.equal(submissions.at(-1).params.top_n,25);
 await page.getByRole('button',{name:'Advanced Options',exact:true}).click();
 const maxDesigns=page.getByLabel('Evaluation budget (validated gate designs)',{exact:true});
 const topN=page.getByLabel('Results to display (top ranked)',{exact:true});
 assert.equal(await maxDesigns.inputValue(),'20');
 assert.equal(await topN.inputValue(),'25');
 for(const [input,normal] of [[maxDesigns,'20'],[topN,'25']]) {
   for(const invalid of ['', '0', '-1', '1.5', '1001']) {
     await input.fill(invalid);
     assert(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled(),`Invalid limit ${invalid} must block submission`);
   }
   for(const boundary of ['1','1000']) {
     await input.fill(boundary);
     assert(!(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled()),`Boundary ${boundary} must be accepted`);
   }
   await input.fill(normal);
 }
 await maxDesigns.fill('13');
 await topN.fill('7');
 for(const status of [401,403,404,422,429,500]) {
   submitStatus=status;
   await page.getByRole('button',{name:'Compile & Optimize'}).click();
   await page.getByRole('alert').filter({hasText:`Injected submission ${status}`}).waitFor();
 }
 assert.equal(submissions.at(-1).params.budget.max_designs,13);
 assert.equal(submissions.at(-1).params.top_n,7);
 submitStatus=null;
 await sequence.fill('>one\nACGU\n>two\nACGU');
 await page.getByText('Paste one FASTA record at a time.',{exact:true}).waitFor();
 await sequence.fill('AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA');
 await page.getByRole('button',{name:'Custom Upload your own GenBank file'}).click();
 await page.getByLabel('Backbone GenBank file').setInputFiles({name:'fixture.gb',mimeType:'text/plain',buffer:Buffer.from('LOCUS fixture circular\nORIGIN\n 1 acgtacgtacgt\n//')});
 const insertion=page.getByLabel('Insertion boundary (0-based)');
 assert(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled());
 for(const value of ['-1','1.5']) {
   await insertion.fill(value);
   assert(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled());
 }
 await insertion.fill('0');
 assert(!(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled()));
 await page.getByLabel('Optimize payload codons for the selected host (optional)').check();
 await page.getByRole('button',{name:'Compile & Optimize'}).click();
 await page.getByRole('alert').filter({hasText:'Failed to fetch'}).waitFor();
 assert.equal(submissions.at(-1).params.backbone.insertion_index,0);
 assert.equal(submissions.at(-1).params.payload.optimize_codons,true);
 await page.getByRole('button',{name:'None Switch, promoter, terminator and payload only — no origin or marker.'}).click();
 await page.getByRole('button',{name:/AmpR/}).click();
 for(const name of ['E. coli','Yeast','Human','C. acnes']) {
   await page.getByRole('button',{name,exact:name!=='C. acnes'}).first().click();
   await page.getByRole('button',{name:'Direct Trigger mRNA'}).click();
   assert.equal(await page.getByRole('button',{name:/AmpR/}).isDisabled(),name!=='E. coli');
   assert.equal(await page.getByRole('button',{name:/KanR/}).isDisabled(),name!=='E. coli');
   assert.equal(await page.getByRole('button',{name:/pSB1C3/}).count(),name==='E. coli'?1:0);
   assert(!(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled()),`${name} direct readiness`);
   await page.getByRole('button',{name:'Specific Gene'}).click();
   await page.getByLabel('Gene ID or symbol').fill('TEST_GENE');
   await page.getByRole('button',{name:'Resolve reference transcript'}).click();
   await page.getByRole('status').filter({hasText:'TEST_TRANSCRIPT'}).waitFor();
   assert(!(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled()),`${name} gene readiness`);
   await page.getByRole('button',{name:'Differential Expression'}).click();
   await page.getByRole('button',{name:'Upload Your Own',exact:true}).click();
   await page.getByRole('button',{name:/Wizard fixture/}).click();
   assert(!(await page.getByRole('button',{name:'Compile & Optimize'}).isDisabled()),`${name} DE readiness`);
 }
 await page.getByRole('button',{name:'Public Dataset',exact:true}).click();
 await page.getByRole('button',{name:'C. acnes',exact:false}).first().click();
 await page.getByRole('button',{name:'Differential Expression'}).click();
 await page.getByText('No curated public datasets are available',{exact:false}).waitFor();
 await page.goto(origin+'/runs/mock-run');
 await page.getByRole('heading',{name:'Computational Design Results'}).waitFor();
 await page.getByText('Run warnings (1)').click();
 await page.getByText('UNIQUE_RUN_WARNING: exports held').waitFor();
 await page.getByText('Candidate warnings (1)').click();
 await page.getByText('UNIQUE_CANDIDATE_WARNING').waitFor();
 await page.getByText('Binding heuristic',{exact:false}).first().waitFor();
 await page.getByText('Unmeasured',{exact:true}).waitFor();
 await page.getByRole('textbox',{name:'Review note',exact:true}).fill('Retain this research candidate');
 await page.getByLabel('Review decision').selectOption('SHORTLISTED');
 await page.getByRole('button',{name:'Save review'}).click();
 await page.getByText('SHORTLISTED · browser-test',{exact:false}).waitFor();
 await page.getByRole('button',{name:'Delete note'}).click();
 await page.getByText('Retain this research candidate',{exact:true}).waitFor({state:'hidden'});
 for(let i=0;i<4;i++) { await page.getByRole('button',{name:'Next',exact:true}).click(); await page.getByText(`Page ${i+2} of 159`,{exact:true}).waitFor(); }
 await page.getByText('cand-201',{exact:true}).first().waitFor();
 await page.getByRole('button',{name:'Last',exact:true}).click();
 await page.getByText('cand-7907',{exact:true}).waitFor();
 assert(queries.some(query=>query.get('offset')==='200'));
 assert(queries.some(query=>query.get('offset')==='7900'));
 await page.getByRole('button',{name:'Custom',exact:true}).click();
 await page.getByText('Page 1 of 159',{exact:true}).waitFor();
 assert(queries.some(query=>query.get('output')==='Custom'&&!query.get('offset')));
 // Legacy runs without top_n keep the complete paginated view.
 assert.equal(await page.getByLabel('Result view',{exact:true}).inputValue(),'all');
 assert(!queries.at(-1).has('top_n'));
 // Historical freeform params must not create an invalid query or hide old results.
 for(const invalid of [null,'25',0,1001,1.5]) {
   run.params_snapshot.top_n=invalid;
   await page.reload();
   await page.getByText('Page 1 of 159',{exact:true}).waitFor();
   assert.equal(await page.getByLabel('Result view',{exact:true}).inputValue(),'all');
   assert(!queries.at(-1).has('top_n'));
 }
 // A configured display cap is global, even with server-side filters and sorting.
 run.params_snapshot.top_n=75;
 let releaseDetail;
 detailGate=new Promise(resolve=>{releaseDetail=resolve;});
 const beforeDelayedDetail=queries.length;
 await page.reload();
 await page.getByRole('heading',{name:'Computational Design Results'}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Last',exact:true}).count(),0);
 assert.equal(queries.length,beforeDelayedDetail,'No unbounded candidate query while configuration is pending');
 releaseDetail();
 detailGate=null;
 await page.getByText('Page 1 of 2',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('Result view',{exact:true}).inputValue(),'top');
 assert.equal(queries.at(-1).get('top_n'),'75');
 await page.getByRole('button',{name:'Next',exact:true}).click();
 await page.getByText('Page 2 of 2',{exact:true}).waitFor();
 await page.getByText('cand-75',{exact:true}).waitFor();
 assert.equal(await page.getByText('cand-76',{exact:true}).count(),0);
 assert(await page.getByRole('button',{name:'Next',exact:true}).isDisabled());
 await page.getByRole('button',{name:'Custom',exact:true}).click();
 // Page counts alone can match before the new query has rendered. Waiting for its
 // row avoids opening Precision Filters just before a loading remount closes it.
 await page.getByText('Candidate 1 · Custom · rank',{exact:true}).waitFor();
 await page.getByText('Page 1 of 2',{exact:true}).waitFor();
 assert.equal(queries.at(-1).get('top_n'),'75');
 assert.equal(queries.at(-1).get('output'),'Custom');
 const precisionFilters=page.getByRole('button',{name:'Precision Filters',exact:true});
 if(await precisionFilters.getAttribute('aria-expanded')!=='true') await precisionFilters.click();
 const sortBy=page.getByRole('combobox',{name:'Sort by',exact:true});
 await sortBy.waitFor();
 await sortBy.selectOption('engine_ref');
 await page.getByText('Candidate 1 · Custom · engine_ref',{exact:true}).waitFor();
 assert.equal(queries.at(-1).get('sort'),'engine_ref');
 assert.equal(queries.at(-1).get('top_n'),'75');
 assert.equal(queries.at(-1).get('output'),'Custom');
 await page.getByLabel('Result view',{exact:true}).selectOption('all');
 await page.getByText('Page 1 of 159',{exact:true}).waitFor();
 assert(!queries.at(-1).has('top_n'));
 await page.getByRole('button',{name:'Last',exact:true}).click();
 await page.getByText('cand-7907',{exact:true}).waitFor();
 await page.getByLabel('Result view',{exact:true}).selectOption('top');
 await page.getByText('Page 1 of 2',{exact:true}).waitFor();
 const showRejected=page.getByLabel('Show rejected candidates',{exact:false});
 if(await precisionFilters.getAttribute('aria-expanded')!=='true') await precisionFilters.click();
 await showRejected.check();
 await page.getByText('Page 1 of 159',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('Result view',{exact:true}).inputValue(),'all');
 assert.equal(queries.at(-1).get('include_rejected'),'true');
 assert(!queries.at(-1).has('top_n'));
 // Same route, different run: client-side navigation must reset view, filters and page.
 await page.getByRole('button',{name:'Last',exact:true}).click();
 await page.getByText('Page 159 of 159',{exact:true}).waitFor();
 const navigateRun=async(id)=>page.evaluate((runId)=>{
   window.history.pushState({},'',`/runs/${runId}`);
   window.dispatchEvent(new PopStateEvent('popstate'));
 },id);
 await navigateRun('other-run');
 await page.getByRole('option',{name:'Top 10 accepted results',exact:true}).waitFor({state:'attached'});
 await page.getByText('Page 1 of 1',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('Result view',{exact:true}).inputValue(),'top');
 assert.equal(queries.at(-1).get('top_n'),'10');
 assert(!queries.at(-1).has('include_rejected'));
 assert(!queries.at(-1).has('offset'));
 await navigateRun('mock-run');
 await page.getByRole('option',{name:'Top 75 accepted results',exact:true}).waitFor({state:'attached'});
 await page.getByText('Page 1 of 2',{exact:true}).waitFor();
 assert.equal(await page.getByLabel('Result view',{exact:true}).inputValue(),'top');
 detailError=true;
 const beforeFailedDetail=queries.length;
 await page.reload();
 const detailAlert=page.getByRole('alert').filter({hasText:'Could not load the frozen run configuration'});
 await detailAlert.waitFor();
 assert.equal(queries.length,beforeFailedDetail,'No unbounded candidate query when configuration fails');
 assert.equal(await page.getByRole('button',{name:'Last',exact:true}).count(),0);
 detailError=false;
 await detailAlert.getByRole('button',{name:'Retry',exact:true}).click();
 await page.getByText('Page 1 of 2',{exact:true}).waitFor();
 assert.equal(queries.at(-1).get('top_n'),'75');
 empty=true;
 await page.reload();
 await page.getByText('No candidate is selected.',{exact:false}).waitFor();
 assert.equal(await page.locator('.animate-spin').count(),0);
 historyError=true;
 await page.goto(origin+'/dashboard');
 await page.getByRole('alert').filter({hasText:'Could not load run history'}).waitFor();
 assert.deepEqual(errors,[]);
 console.log('Browser contracts passed: paste integrity, capability rejection, offline retry, four-host/three-mode wizard readiness, HTTP401/403/404/422/429/500, catalog empty, custom vector insertion boundary, review save/delete, warning/proxy labels, evaluation/display defaults and validation, independent payload limits, global top-N paging/filtering/sorting, full/rejected/legacy access, candidate 201/7907, global output filter, empty completion and history error.');
} catch(error) {
 // These contracts contain only isolated synthetic fixtures, never user records.
 console.error('Browser contract failure URL:',page.url());
 console.error('Recent candidate queries:',queries.slice(-12).map(query=>Object.fromEntries(query)));
 console.error('Page errors:',errors);
 console.error('Rendered fixture text:',(await page.locator('body').innerText({timeout:1000}).catch(()=>'(unavailable)')).slice(-8000));
 throw error;
} finally { await browser.close(); await new Promise(done=>server.close(done)); }
