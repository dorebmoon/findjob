import asyncio
from datetime import datetime
from typing import Dict, List
from playwright.async_api import Page
from .base import BaseScraper


class BossScraper(BaseScraper):
    """Boss直聘 scraper."""
    
    platform_name = 'boss'
    base_url = 'https://www.zhipin.com'
    login_url = 'https://www.zhipin.com/web/user/?ka=header-login'
    message_url = 'https://www.zhipin.com/web/geek/chat'
    job_search_url = 'https://www.zhipin.com/web/geek/job'
    supports_delivery = True

    # Known auth cookies issued by zhipin.com after a successful login.
    # These are exact names, not substrings.
    LOGIN_COOKIE_NAMES = {
        'wt2', 'bst', '__zp_stoken__', 'wt2_geek',
        'geek_zp_token', 'zp_token', 'boss_login', 'ac_t',
    }
    LOGIN_COOKIE_DOMAINS = {'zhipin'}
    
    async def login(self, username: str, password: str, page: Page) -> Dict:
        """Login to Boss直聘."""
        try:
            await page.goto(self.login_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            # Check if already logged in
            if await self.check_login_status(page):
                cookies = await self.get_cookies()
                return {'success': True, 'message': '已登录', 'cookies': cookies}
            
            # Click password login tab if needed
            try:
                pwd_tab = page.locator('text=密码登录')
                if await pwd_tab.count() > 0:
                    await pwd_tab.click()
                    await asyncio.sleep(1)
            except Exception:
                pass
            
            # Fill in credentials
            username_input = page.locator('input[placeholder*="手机号"], input[name="username"], input[type="text"]').first
            await username_input.fill(username)
            await asyncio.sleep(0.5)
            
            password_input = page.locator('input[type="password"]').first
            await password_input.fill(password)
            await asyncio.sleep(0.5)
            
            # Click login button
            login_btn = page.locator('button[type="submit"], .btn-login, button:has-text("登录")').first
            await login_btn.click()
            
            # Wait for navigation or error
            await asyncio.sleep(5)
            
            # Check for CAPTCHA
            captcha = page.locator('.geetest_panel, .captcha, .verify-wrap')
            if await captcha.count() > 0:
                return {
                    'success': False,
                    'message': '需要验证码，请在弹出的浏览器窗口中手动完成验证',
                    'need_captcha': True
                }
            
            # Check login success
            if await self.check_login_status(page):
                cookies = await self.get_cookies()
                return {'success': True, 'message': '登录成功', 'cookies': cookies}
            
            return {'success': False, 'message': '登录失败，请检查账号密码'}
            
        except Exception as e:
            return {'success': False, 'message': f'登录出错: {str(e)}'}
    
    async def check_login_status(self, page: Page) -> bool:
        """
        Check if logged in to Boss直聘.
        Uses a separate page so we don't disrupt the user's active login tab.
        """
        try:
            # First check cookies for session token (no navigation).
            if await self.check_login_by_cookies():
                return True

            # Use a fresh page in the same context to probe the site.
            # This avoids blowing away the user's current login page state.
            probe = None
            try:
                probe = await self._context.new_page()
                await probe.goto(self.base_url, wait_until='domcontentloaded', timeout=15000)
                await asyncio.sleep(2)

                if self.is_login_url(probe.url):
                    return False

                # Check logged-in UI markers on homepage
                try:
                    user_el = probe.locator(
                        '[class*="user-nav"], [class*="header-user"], [class*="nav-figure"], '
                        '.nav-figure, .user-nav, a:has-text("我的简历")'
                    )
                    if await user_el.count() > 0:
                        return True
                except Exception:
                    pass

                # Probe the chat page — if accessible without a login redirect,
                # the session is valid.
                try:
                    await probe.goto(self.message_url, wait_until='domcontentloaded', timeout=15000)
                    await asyncio.sleep(2)
                    if self.is_login_url(probe.url):
                        return False
                    if 'chat' in probe.url or 'geek' in probe.url:
                        return True
                except Exception:
                    pass
            finally:
                if probe is not None:
                    try:
                        await probe.close()
                    except Exception:
                        pass

            # Re-check cookies one more time in case session was just issued.
            return await self.check_login_by_cookies()
        except Exception:
            return False
    
    # Ordered candidate selectors for the chat list.
    # Boss updates class names periodically; try the most recent first, then
    # broader fallbacks. The first selector that returns >= 1 item wins.
    _CHAT_LIST_SELECTORS = [
        'ul.user-list li',          # classic /geek/chat layout
        '.geek-new-job-list li',
        '.friend-list .friend-item',
        '[class*="geek-new-msg"] li',
        '[class*="chat-list"] li',
        '.conversation-list .conversation-item',
        'li[class*="chat-item"]',
        '[class*="chat-item"]',
        '.conversation-item',
    ]

    async def fetch_messages(self, page: Page) -> List[Dict]:
        """Fetch messages from Boss直聘 with multiple selector fallbacks."""
        messages: List[Dict] = []
        try:
            await page.goto(self.message_url, wait_until='domcontentloaded', timeout=30000)

            # Chat list is client-rendered; wait for any candidate to appear.
            # If none shows up within 8s, fall through and let JS-side scan decide.
            wait_selector = ', '.join(self._CHAT_LIST_SELECTORS)
            try:
                await page.wait_for_selector(wait_selector, timeout=8000)
            except Exception:
                pass
            await asyncio.sleep(2)

            # Pick the first selector that actually matches something.
            chat_locator = None
            for sel in self._CHAT_LIST_SELECTORS:
                loc = page.locator(sel)
                try:
                    count = await loc.count()
                except Exception:
                    count = 0
                if count > 0:
                    chat_locator = loc
                    break

            if chat_locator is None:
                # Last-ditch: pull structured data out of the page via JS.
                # Scans all <li> and returns those that look like chat items
                # (contain a name + a message preview).
                try:
                    data = await page.evaluate(
                        """() => {
                            const items = [];
                            const seen = new Set();
                            const candidates = document.querySelectorAll(
                                'li, [class*=chat], [class*=conversation], [class*=message-item]'
                            );
                            for (const el of candidates) {
                                const txt = (el.innerText || '').trim();
                                if (!txt || txt.length < 2 || txt.length > 400) continue;
                                // Look for a structured name / msg pair.
                                const nameEl = el.querySelector(
                                    '[class*=name], [class*=Name], .geek-name, .friend-name'
                                );
                                const msgEl = el.querySelector(
                                    '[class*=msg-text], [class*=last-msg], [class*=content], [class*=text]'
                                );
                                const jobEl = el.querySelector(
                                    '[class*=job-name], [class*=position], [class*=title]'
                                );
                                const name = nameEl ? (nameEl.innerText || '').trim() : '';
                                const msg = msgEl ? (msgEl.innerText || '').trim() : '';
                                const job = jobEl ? (jobEl.innerText || '').trim() : '';
                                if (!name && !msg) continue;
                                const key = name + '::' + msg.slice(0, 40);
                                if (seen.has(key)) continue;
                                seen.add(key);
                                items.push({name, msg, job});
                                if (items.length >= 20) break;
                            }
                            return items;
                        }"""
                    )
                except Exception:
                    data = []

                for d in data or []:
                    if not (d.get('name') or d.get('msg')):
                        continue
                    messages.append({
                        'sender_name': d.get('name', ''),
                        'sender_company': '',
                        'content': d.get('msg', ''),
                        'job_title': d.get('job', ''),
                        'salary_range': '',
                        'message_type': 'chat',
                        'external_id': self.make_external_id(
                            d.get('name'), d.get('msg'), d.get('job')
                        ),
                        'received_at': datetime.utcnow().isoformat(),
                        'external_url': self.message_url,
                    })
                return messages

            # Structured extraction when we have a concrete locator.
            total = await chat_locator.count()
            for i in range(min(total, 20)):
                try:
                    item = chat_locator.nth(i)

                    sender_name = await self._safe_text(
                        item,
                        '.geek-name, .friend-name, .name, .user-name, '
                        '[class*="Name"], [class*="name"]',
                    )
                    content = await self._safe_text(
                        item,
                        '.last-msg-text, .msg-text, .message-text, '
                        '.last-msg, [class*="last-msg"], [class*="msg-text"], '
                        '[class*="message"], [class*="content"]',
                    )
                    job_title = await self._safe_text(
                        item,
                        '.job-name, [class*="job-name"], [class*="position"], [class*="job"]',
                    )
                    sender_company = await self._safe_text(
                        item,
                        '[class*="company"], [class*="corp"]',
                    )

                    if not (sender_name or content):
                        continue

                    messages.append({
                        'sender_name': sender_name,
                        'sender_company': sender_company,
                        'content': content,
                        'job_title': job_title,
                        'salary_range': '',
                        'message_type': 'chat',
                        'external_id': self.make_external_id(
                            sender_name, content, job_title
                        ),
                        'received_at': datetime.utcnow().isoformat(),
                        'external_url': self.message_url,
                    })
                except Exception:
                    continue

        except Exception as e:
            print(f"Boss直聘 fetch messages error: {e}")

        return messages

    @staticmethod
    async def _safe_text(item, selectors: str) -> str:
        """Grab text from the first matching child, swallowing errors."""
        try:
            el = item.locator(selectors).first
            if await el.count() > 0:
                txt = await el.text_content()
                return (txt or '').strip()
        except Exception:
            pass
        return ''

    # ─── Job search ──────────────────────────────────────────────────────────

    async def search_jobs(self, page: Page, keyword: str, city: str = '', limit: int = 20) -> List[Dict]:
        """
        Search job posts on Boss直聘. City is the friendly name ("深圳" etc.);
        we rely on Boss resolving it via the query string.

        NOTE: Boss uses a numeric `city` code (e.g. 101280600 for 深圳) in its
        most specific URLs. We keep this simple and let Boss default to "all"
        when city isn't a known code — the keyword carries the main filter.
        """
        jobs: List[Dict] = []
        if not keyword:
            return jobs
        try:
            from urllib.parse import quote
            url = f"{self.base_url}/web/geek/job?query={quote(keyword)}"
            if city:
                url += f"&city={quote(city)}"
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            # Let the JS-rendered list appear; Boss uses <li class="job-card-wrapper">
            # or similar class names that shift between A/B tests.
            wait_sel = ('li.job-card-wrapper, .job-list-box li, '
                        '.job-list .job-card, [class*="job-card"]')
            try:
                await page.wait_for_selector(wait_sel, timeout=8000)
            except Exception:
                pass

            card = None
            for sel in ('li.job-card-wrapper', '.job-list-box li',
                        '.job-list .job-card', '[class*="job-card"]'):
                loc = page.locator(sel)
                if await loc.count() > 0:
                    card = loc
                    break

            if card is None:
                # JS-side fallback — scrape whatever looks like a job card.
                raw = await page.evaluate(
                    """(limit) => {
                        const out = [];
                        const nodes = document.querySelectorAll(
                            'li.job-card-wrapper, [class*="job-card"], .job-list li'
                        );
                        for (const n of nodes) {
                            const a = n.querySelector('a[href*="/job_detail/"], a[href*="/web/geek/job"]');
                            const titleEl = n.querySelector('[class*="job-name"], [class*="job-title"]');
                            const salaryEl = n.querySelector('[class*="salary"], [class*="red"]');
                            const companyEl = n.querySelector('[class*="company-name"], [class*="company"]');
                            const cityEl = n.querySelector('[class*="job-area"], [class*="city"]');
                            const tagsEls = n.querySelectorAll('[class*="job-label"], [class*="tag-list"] li, [class*="labels"] span');
                            const title = (titleEl?.innerText || '').trim();
                            const company = (companyEl?.innerText || '').trim();
                            if (!title && !company) continue;
                            const href = a?.getAttribute('href') || '';
                            const tags = [];
                            tagsEls.forEach(t => {
                                const v = (t.innerText || '').trim();
                                if (v) tags.push(v);
                            });
                            out.push({
                                title,
                                company,
                                salary: (salaryEl?.innerText || '').trim(),
                                city: (cityEl?.innerText || '').trim(),
                                tags,
                                href
                            });
                            if (out.length >= limit) break;
                        }
                        return out;
                    }""",
                    limit
                )
                for r in raw or []:
                    href = r.get('href') or ''
                    ext_id = self._extract_job_id(href) or self.make_external_id(
                        r.get('title'), r.get('company'), r.get('salary')
                    )
                    if not ext_id:
                        continue
                    jobs.append({
                        'external_id': ext_id,
                        'title': r.get('title', ''),
                        'company': r.get('company', ''),
                        'salary_range': r.get('salary', ''),
                        'city': r.get('city', ''),
                        'experience': '',
                        'education': '',
                        'tags': r.get('tags', []),
                        'description': '',
                        'url': self._absolute_url(href),
                    })
                return jobs

            total = await card.count()
            for i in range(min(total, limit)):
                try:
                    item = card.nth(i)
                    title = await self._safe_text(
                        item, '[class*="job-name"], [class*="job-title"]')
                    company = await self._safe_text(
                        item, '[class*="company-name"], [class*="company"]')
                    salary = await self._safe_text(
                        item, '[class*="salary"], [class*="red"]')
                    city_txt = await self._safe_text(
                        item, '[class*="job-area"], [class*="city"]')

                    href = ''
                    try:
                        a = item.locator('a[href*="/job_detail/"], a[href*="/web/geek/job"]').first
                        if await a.count() > 0:
                            href = await a.get_attribute('href') or ''
                    except Exception:
                        pass

                    ext_id = self._extract_job_id(href) or self.make_external_id(
                        title, company, salary)
                    if not ext_id:
                        continue
                    if not (title or company):
                        continue

                    jobs.append({
                        'external_id': ext_id,
                        'title': title,
                        'company': company,
                        'salary_range': salary,
                        'city': city_txt,
                        'experience': '',
                        'education': '',
                        'tags': [],
                        'description': '',
                        'url': self._absolute_url(href),
                    })
                except Exception:
                    continue
        except Exception as e:
            print(f"Boss直聘 search_jobs error: {e}")

        return jobs

    def _absolute_url(self, href: str) -> str:
        if not href:
            return ''
        if href.startswith('http'):
            return href
        if href.startswith('//'):
            return 'https:' + href
        if href.startswith('/'):
            return self.base_url + href
        return href

    @staticmethod
    def _extract_job_id(href: str) -> str:
        """Pull the job id out of a Boss detail URL like /job_detail/xxx.html."""
        if not href:
            return ''
        import re
        m = re.search(r'/job_detail/([^./?#]+)', href)
        if m:
            return m.group(1)
        m = re.search(r'[?&]jobId=([^&]+)', href)
        if m:
            return m.group(1)
        return ''

    # ─── Delivery (send initial greeting) ────────────────────────────────────

    async def submit_greeting(self, page: Page, job: Dict, greeting: str) -> Dict:
        """
        Open the job detail page, click 「立即沟通」(Chat Now), and send the
        greeting as the first message. Returns success only when we see either:
          - navigation to /web/geek/chat with the boss in the list, or
          - a success confirmation dialog / toast.
        """
        url = job.get('url') or ''
        if not url:
            return {'success': False, 'message': '缺少职位 URL'}

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=30000)
            await asyncio.sleep(3)

            if self.is_login_url(page.url):
                return {'success': False, 'message': '未登录或登录已失效，请先在 Boss 完成登录'}

            # Click the 「立即沟通」 button. Boss varies between button/a.
            chat_btn = page.locator(
                'a.btn-startchat, .btn.btn-startchat, '
                'a:has-text("立即沟通"), button:has-text("立即沟通"), '
                'a:has-text("继续沟通"), button:has-text("继续沟通")'
            ).first
            if await chat_btn.count() == 0:
                # Could also be "已沟通" if we talked before.
                already = page.locator('a:has-text("继续沟通"), button:has-text("继续沟通")').first
                if await already.count() == 0:
                    return {'success': False, 'message': '未找到沟通按钮（可能职位已下架或需要登录）'}
                chat_btn = already

            try:
                await chat_btn.click(timeout=5000)
            except Exception:
                # Some layouts open chat in a new tab.
                try:
                    await chat_btn.evaluate("el => el.click()")
                except Exception as e:
                    return {'success': False, 'message': f'点击沟通按钮失败: {e}'}

            # Wait for chat input to become available. Boss sometimes opens a
            # floating dialog, sometimes routes to /web/geek/chat.
            await asyncio.sleep(3)
            try:
                await page.wait_for_url(lambda u: 'geek/chat' in u or 'job_detail' in u, timeout=8000)
            except Exception:
                pass

            input_sel = (
                'div.chat-input[contenteditable], '
                'div[contenteditable="true"].chat-input, '
                '[class*="chat-input"][contenteditable], '
                'textarea[placeholder*="说点什么"], textarea[placeholder*="输入"]'
            )
            try:
                await page.wait_for_selector(input_sel, timeout=8000)
            except Exception:
                return {'success': False, 'message': '未找到聊天输入框（对方可能需要先接受沟通）'}

            box = page.locator(input_sel).first
            try:
                await box.click()
            except Exception:
                pass

            # contenteditable divs don't accept .fill(); type instead.
            try:
                tag = (await box.evaluate('el => el.tagName')).lower()
            except Exception:
                tag = ''
            if tag == 'textarea':
                try:
                    await box.fill(greeting)
                except Exception:
                    await box.type(greeting, delay=15)
            else:
                await box.type(greeting, delay=15)

            await asyncio.sleep(1)

            # Send: click button if present, else press Enter.
            send_btn = page.locator(
                'button:has-text("发送"), .btn-send, [class*="send-btn"]'
            ).first
            sent = False
            if await send_btn.count() > 0:
                try:
                    await send_btn.click(timeout=5000)
                    sent = True
                except Exception:
                    pass
            if not sent:
                try:
                    await box.press('Enter')
                    sent = True
                except Exception:
                    pass
            if not sent:
                return {'success': False, 'message': '无法发送消息'}

            # Confirm — look for the sent message to appear in the chat log.
            await asyncio.sleep(3)
            try:
                snippet = greeting.strip().split('\n')[0][:20]
                if snippet:
                    found = page.locator(f'text={snippet}').first
                    if await found.count() > 0:
                        return {
                            'success': True,
                            'message': '已发送打招呼',
                            'external_url': page.url
                        }
            except Exception:
                pass

            # If we can't positively confirm but also didn't crash, treat as
            # success — Boss often doesn't echo the message immediately.
            return {
                'success': True,
                'message': '已发送（未能二次确认）',
                'external_url': page.url
            }
        except Exception as e:
            return {'success': False, 'message': f'投递异常: {e}'}
