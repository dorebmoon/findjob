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
        """Check if logged in to Boss直聘."""
        try:
            # First check cookies for session token
            cookies = await self.get_cookies()
            cookie_names = {c['name'] for c in cookies}
            # Boss直聘 uses these cookies when logged in
            if any(name in cookie_names for name in ['wt2', 'bst', 't', '__zp_stoken__']):
                return True
            
            # Navigate and check URL
            await page.goto(self.base_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(3)
            current_url = page.url
            
            # If redirected to login page, not logged in
            if 'login' in current_url or 'passport' in current_url:
                return False
            
            # Check for logged-in indicators
            try:
                user_el = page.locator('[class*="user-nav"], [class*="header-user"], [class*="nav-figure"], .nav-item:has-text("我的")')
                if await user_el.count() > 0:
                    return True
            except Exception:
                pass
            
            # Try accessing the chat page directly
            try:
                await page.goto(self.message_url, wait_until='domcontentloaded', timeout=10000)
                await asyncio.sleep(2)
                if 'chat' in page.url or 'geek' in page.url:
                    return True
            except Exception:
                pass
            
            return False
        except Exception:
            return False

    async def check_login_by_cookies(self) -> bool:
        """Lightweight cookie-based login check (no navigation)."""
        try:
            cookies = await self.get_cookies()
            cookie_names = {c['name'] for c in cookies}
            return any(name in cookie_names for name in ['wt2', 'bst', 't', '__zp_stoken__', 'wt2_geek'])
        except Exception:
            return False
    
    async def fetch_messages(self, page: Page) -> List[Dict]:
        """Fetch messages from Boss直聘."""
        messages = []
        try:
            await page.goto(self.message_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            # Try to find message items in the chat list
            chat_items = page.locator('.chat-item, .conversation-item, [class*="chat-list"] > div')
            count = await chat_items.count()
            
            for i in range(min(count, 20)):
                try:
                    item = chat_items.nth(i)
                    
                    sender_name = ''
                    content = ''
                    job_title = ''
                    sender_company = ''
                    
                    # Try to extract sender name
                    name_el = item.locator('.name, .user-name, [class*="name"]').first
                    if await name_el.count() > 0:
                        sender_name = (await name_el.text_content() or '').strip()
                    
                    # Try to extract message content
                    msg_el = item.locator('.message-text, .last-msg, [class*="message"], [class*="msg"]').first
                    if await msg_el.count() > 0:
                        content = (await msg_el.text_content() or '').strip()
                    
                    # Try to extract job title
                    job_el = item.locator('.job-name, [class*="job"], [class*="position"]').first
                    if await job_el.count() > 0:
                        job_title = (await job_el.text_content() or '').strip()
                    
                    if sender_name or content:
                        messages.append({
                            'sender_name': sender_name,
                            'sender_company': sender_company,
                            'content': content,
                            'job_title': job_title,
                            'salary_range': '',
                            'message_type': 'chat',
                            'received_at': datetime.utcnow().isoformat(),
                            'external_url': self.message_url
                        })
                except Exception:
                    continue
                    
        except Exception as e:
            print(f"Boss直聘 fetch messages error: {e}")
        
        return messages