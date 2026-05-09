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