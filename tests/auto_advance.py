"""Regression checks for selection, navigation cancellation and local save failures."""
import os
from playwright.sync_api import sync_playwright,expect

base=os.environ.get('ATLAS_TEST_URL','http://127.0.0.1:5173')
exe=os.environ.get('ATLAS_BROWSER_EXECUTABLE')
with sync_playwright() as p:
    browser=p.chromium.launch(**({'executable_path':exe} if exe else {}))
    context=browser.new_context(viewport={'width':390,'height':844},has_touch=True)
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/test?mode=basic')
    page.get_by_role('button',name='开始探索',exact=True).click()
    # A double tap chooses one answer and advances exactly one question.
    page.locator('[data-answer="2"]').dblclick(delay=50)
    expect(page.locator('.progress-label')).to_contain_text('第 2 / 99')
    expect(page.locator('.progress-label')).to_contain_text('已答 1 / 99')
    page.wait_for_timeout(500)
    expect(page.locator('.progress-label')).to_contain_text('第 2 / 99')
    page.reload();expect(page.locator('.progress-label')).to_contain_text('第 2 / 99')
    page.get_by_role('button',name='上一题',exact=True).click()
    expect(page.locator('[data-answer="2"]')).to_have_attribute('aria-pressed','true')
    page.locator('[data-answer="-1"]').click()
    expect(page.locator('.progress-label')).to_contain_text('第 2 / 99')
    page.get_by_role('button',name='上一题',exact=True).click()
    expect(page.locator('[data-answer="-1"]')).to_have_attribute('aria-pressed','true')
    page.get_by_role('button',name='下一题',exact=True).click()
    # Opening a pause or question overview cancels an outstanding transition.
    page.evaluate('''() => {
      document.querySelector('[data-answer="1"]').click();
      [...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='暂停').click();
    }''')
    expect(page.get_by_role('heading',name='先歇一会儿，再继续。')).to_be_visible()
    page.wait_for_timeout(500)
    page.get_by_role('button',name='继续探索',exact=True).click()
    expect(page.locator('.progress-label')).to_contain_text('第 2 / 99')
    expect(page.locator('[data-answer="1"]')).to_have_attribute('aria-pressed','true')
    page.evaluate('''() => {
      document.querySelector('[data-answer="3"]').click();
      [...document.querySelectorAll('button')].find(b=>b.textContent.trim()==='题号').click();
    }''')
    page.get_by_role('button',name='第 1 题，已答',exact=True).click()
    page.wait_for_timeout(500)
    expect(page.locator('.progress-label')).to_contain_text('第 1 / 99')
    # Failed local storage must not move the user away from the answer.
    page.evaluate('''() => {
      window.atlasOriginalPut=IDBObjectStore.prototype.put;
      IDBObjectStore.prototype.put=function(value,key){
        if(String(key).startsWith('draft:'))throw new DOMException('Test storage full','QuotaExceededError');
        return window.atlasOriginalPut.apply(this,arguments);
      };
    }''')
    page.locator('[data-answer="0"]').click()
    expect(page.locator('.alert.error')).to_be_visible()
    page.wait_for_timeout(500)
    expect(page.locator('.progress-label')).to_contain_text('第 1 / 99')
    expect(page.locator('[data-answer="0"]')).to_have_attribute('aria-pressed','true')
    page.evaluate('() => {IDBObjectStore.prototype.put=window.atlasOriginalPut;}')
    page.locator('[data-answer="0"]').click()
    expect(page.locator('.progress-label')).to_contain_text('第 2 / 99')
    assert not errors,errors
    browser.close()
    print('PASS: double tap, autosave/reload, previous/edit, manual next for saved answers, pause/grid cancellation and storage-failure retry.')
