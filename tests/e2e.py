from playwright.sync_api import sync_playwright,expect
from pathlib import Path
import json,os
base=os.environ.get('ATLAS_TEST_URL','http://127.0.0.1:5173').rstrip('/')
exe=os.environ.get('ATLAS_BROWSER_EXECUTABLE')
Path('artifacts/e2e').mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(**({'executable_path':exe} if exe else {}))
 ctx=b.new_context(viewport={'width':390,'height':844},has_touch=True)
 page=ctx.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(base+'/test?mode=basic');page.get_by_label('学号').fill('20261018001');page.get_by_label('姓名').fill('验收用户');page.get_by_role('button',name='开始探索',exact=True).click()
 for i in range(99):
  if i==3:
   page.reload();expect(page.locator('.progress-label')).to_contain_text('第 4 / 99')
  if i==6:
   page.get_by_role('button',name='暂停',exact=True).click();expect(page.get_by_role('heading',name='先歇一会儿，再继续。')).to_be_visible();page.get_by_role('button',name='继续探索',exact=True).click()
  page.locator(f'[data-answer="{i%7-3}"]').click()
  if i+1 in [25,50,75]:page.get_by_role('button',name='继续下一小节',exact=True).click()
  elif i<98:expect(page.locator('.progress-label')).to_contain_text(f'第 {i+2} / 99')
  else:expect(page.get_by_role('button',name='生成我的报告',exact=True)).to_be_visible()
 page.get_by_role('button',name='生成我的报告',exact=True).click();expect(page.locator('.type-seal')).to_be_visible()
 page.get_by_role('button',name='四维分析',exact=True).click();expect(page.get_by_text('可能的优势：',exact=True)).to_have_count(4)
 with page.expect_download() as dl:page.get_by_role('button',name='下载摘要图片',exact=True).click()
 dl.value.save_as('artifacts/e2e/basic-summary.png')
 page.get_by_role('button',name='继续 300 题探索',exact=True).click();expect(page.locator('.check-row')).to_contain_text('仅补答 201 题')
 page.get_by_role('button',name='开始探索',exact=True).click();expect(page.locator('.progress-label')).to_contain_text('第 100 / 300')
 page.get_by_role('button',name='换设备',exact=True).click();expect(page.locator('dialog input')).not_to_have_value('')
 link=page.locator('dialog input').input_value();assert link.startswith(base+'/resume#')
 page.get_by_role('button',name='关闭续答窗口').click()
 ctx2=b.new_context(viewport={'width':820,'height':1180});other=ctx2.new_page();other.goto(link);expect(other.locator('.progress-label')).to_contain_text('第 100 / 300');assert '#' not in other.url
 # Force two clients to edit the same revision; only the later client must resolve conflict.
 other.locator('[data-answer="3"]').click();other.wait_for_timeout(1400)
 page.locator('[data-answer="-3"]').click();expect(page.get_by_text('另一设备保存了更新的答案。',exact=False).first).to_be_visible(timeout=6000)
 page.on('dialog',lambda dialog:dialog.accept())
 page.get_by_role('button',name='载入最新草稿').click()
 # Both devices may already show question 101; wait for the asynchronous restore itself.
 expect(page.get_by_role('button',name='载入最新草稿',exact=True)).not_to_be_visible()
 expect(page.locator('.progress-label')).to_contain_text('第 101 / 300')
 page.get_by_role('button',name='上一题',exact=True).click();expect(page.locator('[data-answer="3"]')).to_have_attribute('aria-pressed','true')
 page.get_by_role('button',name='换设备',exact=True).click();page.get_by_role('button',name='撤销链接',exact=True).click()
 # Continue all 201 extra questions through UI; basic answers remain untouched.
 for i in range(99,300):
  if i==145:
   ctx.set_offline(True);expect(page.get_by_text('你正在离线作答。',exact=False)).to_be_visible()
  if i>=120 and i<124:page.get_by_role('button',name='不适用 / 无相关经历',exact=True).click()
  else:page.locator(f'[data-answer="{(i+2)%7-3}"]').click()
  if i+1 in [120,140,160,180,200,220,240,260,280]:page.get_by_role('button',name='继续下一小节',exact=True).click()
  elif i<299:expect(page.locator('.progress-label')).to_contain_text(f'第 {i+2} / 300')
  else:expect(page.get_by_role('button',name='生成我的报告',exact=True)).to_be_visible()
  if i==145:ctx.set_offline(False)
 page.get_by_role('button',name='生成我的报告',exact=True).click();expect(page.locator('.report-meta')).to_contain_text('详细版')
 for label in ['四维分析','职业发展','社交关系','恋爱关系','30 天行动']:
  page.get_by_role('button',name=label,exact=True).click()
  assert page.locator('.report-section:visible').count()==1
 page.get_by_role('button',name='职业发展',exact=True).click();expect(page.get_by_text('当前回答不足以支持个性化判断',exact=False)).to_be_visible()
 for w in [320,360,390,600,768,820,1024,1440]:
  page.set_viewport_size({'width':w,'height':900});assert page.evaluate('document.documentElement.scrollWidth <= innerWidth'),w
 page.set_viewport_size({'width':390,'height':844});page.screenshot(path='artifacts/e2e/full-career-phone.png',full_page=True)
 page.emulate_media(media='print');page.pdf(path='artifacts/e2e/full-report.pdf',print_background=True)
 assert page.locator('.report-section:visible').count()==6
 page.emulate_media(media='screen');page.goto(base+'/history');expect(page.locator('.history-type')).to_have_count(2)
 page.goto(base+'/admin');page.get_by_label('密码',exact=True).fill(os.environ.get('ATLAS_ADMIN_TEST_PASSWORD','local-development-password-long16'));page.get_by_role('button',name='登录',exact=True).click();expect(page.get_by_role('heading',name='题目维护',exact=True)).to_be_visible()
 expect(page.get_by_role('heading',name='答题提交',exact=True)).to_be_visible();expect(page.locator('.submission-section')).to_contain_text('验收用户');expect(page.locator('.submission-section tbody tr')).to_have_count(2)
 with page.expect_download() as dl:page.locator('.submission-section tbody tr').first.get_by_role('button',name='导出',exact=True).click()
 exported=json.loads(Path(dl.value.path()).read_text());assert exported['studentId']=='20261018001' and exported['studentName']=='验收用户' and len(exported['answers']) in [99,300]
 page.locator('.submission-section tbody tr').first.get_by_role('button',name='查看',exact=True).click();expect(page.get_by_role('heading',name='作答记录 · 300 题',exact=False).first).to_be_visible()
 expect(page.locator('.submission-detail .report-hero')).to_be_visible();page.get_by_role('button',name='返回列表',exact=True).click()
 page.get_by_role('button',name='报告预览',exact=True).click();expect(page.get_by_text('以下使用模拟答案预览',exact=False)).to_be_visible()
 print('PASS: automatic advance across 99 + 201 questions, reload, pause, offline, QR recovery, conflict, revoke, report chapters, NA, PNG, PDF, history, admin preview; JS errors=',errors)
 assert not errors
 b.close()
