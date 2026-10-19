/** Real HTTP/session/SQLite queue/worker/LocalEngine browser lane in temporary storage.
 * Run from repo root after a production frontend build and locked uv sync.
 */
import assert from 'node:assert/strict';
import { spawn, spawnSync } from 'node:child_process';
import { createServer } from 'node:net';
import { mkdtempSync, openSync, closeSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { resolve, join } from 'node:path';
import { setTimeout as delay } from 'node:timers/promises';
import { chromium } from 'playwright';
const cwd=resolve(import.meta.dirname,'../..');
const dir=mkdtempSync(join(tmpdir(),'cernal-browser-queue-'));
const env={...process.env, PYTHONPATH:join(cwd,'src'), DATABASE_URL:`sqlite:///${dir}/test.sqlite3`,MEDIA_ROOT:join(dir,'media'),REVIEWER_LOGIN_ENABLED:'false',CERNAL_SUPERVISED_CHILD:'1'};
const logs=openSync(join(dir,'processes.log'),'a');
const command=(args)=>{
 const result=spawnSync('uv',['run','--offline','--no-sync','python','manage.py',...args],{cwd,env,encoding:'utf8'});
 if(result.status!==0) throw new Error(`${args[0]} failed: ${result.stderr}\n${result.stdout}`);
};
const processes=[];
let browser;
try {
 command(['migrate','--noinput']);
 command(['createcachetable']);
 command(['shell','-c',"from django.contrib.auth import get_user_model; get_user_model().objects.create_user(username='isolated-browser',password='temporary-browser-password',is_active=True)"]);
 const reservation=createServer();
 await new Promise(done=>reservation.listen(0,'127.0.0.1',done));
 const port=reservation.address().port;
 await new Promise(done=>reservation.close(done));
 const origin=`http://127.0.0.1:${port}`;
 for(const args of [['runserver',`127.0.0.1:${port}`,'--noreload'],['qcluster']])
  processes.push(spawn('uv',['run','--offline','--no-sync','python','manage.py',...args],{cwd,env,stdio:['ignore',logs,logs],detached:process.platform!=='win32'}));
 for(let attempt=0;;attempt++) {
  if(processes.some(proc=>proc.exitCode!==null)) throw new Error(`Server/worker exited; inspect ${dir}/processes.log`);
  try { const response=await fetch(origin+'/api/health'); if(response.ok) break; } catch { /* starting */ }
  if(attempt>=60) throw new Error(`Local server did not start; inspect ${dir}/processes.log`);
  await delay(500);
 }
 browser=await chromium.launch();
 const page=await browser.newPage();
 const errors=[];
 page.on('pageerror',error=>errors.push(error.message));
 await page.goto(origin+'/login');
 await page.getByLabel('Username').fill('isolated-browser');
 await page.getByLabel('Password').fill('temporary-browser-password');
 await page.getByRole('button',{name:'Sign in',exact:true}).click();
 await page.waitForURL('**/dashboard');
 await page.goto(origin+'/compile');
 await page.getByRole('button',{name:'Direct Trigger mRNA'}).click();
 await page.getByRole('textbox',{name:'Trigger sequence'}).fill('AACUUGUUGGCCCAGUGUGAAUCGCUUAAGGGUUAA');
 await page.getByRole('button',{name:'None',exact:false}).last().click();
 assert.equal(await page.getByRole('button',{name:/Advanced Options/}).count(),0);
 const submitted=page.waitForResponse(response=>response.url().endsWith('/api/runs')&&response.request().method()==='POST');
 await page.getByRole('button',{name:'Compile & Optimize'}).click();
 const response=await submitted;
 assert.equal(response.status(),202,await response.text());
 const run=await response.json();
 assert.deepEqual(run.params_snapshot.budget,{max_designs:null});
 assert.equal(run.params_snapshot.top_n,20);
 assert.equal(run.params_snapshot.constraints.max_circuit_gates,1);
 assert.equal(response.request().postDataJSON().scoring_profile,'ranking');
 assert.equal(run.params_snapshot.scoring,undefined);
 assert(['QUEUED','RUNNING'].includes(run.status),`Must genuinely enqueue, got ${run.status}`);
 await page.waitForURL('**/runs/*');
 await page.getByRole('heading',{name:'Computational Design Results'}).waitFor({timeout:180000});
 const state=await page.request.get(origin+`/api/runs/${run.id}`);
 const terminal=await state.json();
 assert.equal(terminal.status,'COMPLETED');
 const candidates=await (await page.request.get(origin+`/api/runs/${run.id}/candidates?top_n=20`)).json();
 assert.equal(candidates.count,terminal.counts.candidates);
 assert(candidates.items.every(candidate=>candidate.rank && !candidate.is_rejected));
 assert(terminal.counts.candidates>0,'The verified productive real fixture must produce candidates');
 await page.getByText('Score decomposition',{exact:true}).waitFor();
 assert.deepEqual(errors,[]);
 console.log(`Real queued browser lane passed: ${run.id}, ${terminal.counts.candidates} candidates; HTTP login/submission, database queue, separate qcluster, real LocalEngine. Release adapter remains unconfigured/held.`);
} finally {
 if(browser) await browser.close();
 for(const proc of processes) {
  if(process.platform==='win32') proc.kill();
  else { try { process.kill(-proc.pid,'SIGTERM'); } catch { /* already exited */ } }
 }
 await delay(300);
 for(const proc of processes) {
  if(process.platform!=='win32') { try { process.kill(-proc.pid,'SIGKILL'); } catch { /* already exited */ } }
 }
 closeSync(logs);
 if(process.env.CERNAL_KEEP_QA_STORAGE) console.log(`Isolated QA storage retained: ${dir}`);
 else rmSync(dir,{recursive:true,force:true});
}
