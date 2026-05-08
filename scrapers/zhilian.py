import asyncio
from datetime import datetime
from typing import Dict, List
from playwright.async_api import Page
from .base import BaseScraper


class ZhilianScraper(BaseScraper):
    """智联招聘 scraper."""
    
    platform_name = 'zhilian'
    base_url = 'https://www.zhaopin.com'
    login_url = 'https://passport.zhaopin.com/login'
    message_url = 'https://www.zhaopin.com/inbox'
    
    async def login(self, username: str, password: str, page: Page) -> Dict:
        try:
            await page.goto(self.login_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(2)
            
            if await self.check_login_status(page):
                cookies = await self.get_cookies()
                return {'success': True, 'message': '已登录', 'cookies': cookies}
            
            # Switch to password login if needed
            try:
                pwd_tab = page.locator('text=密码登录, text=账号密码登录')
                if await pwd_tab.count() > 0:
                    await pwd_tab.first.click()
                    await asyncio.sleep(1)
            except Exception:
                pass
            
            # Fill credentials
            username_input = page.locator('input[placeholder*="手机"], input[placeholder*="邮箱"], input[name="username"], input[type="text"]').first
            await username_input.fill(username)
            await asyncio.sleep(0.5)
            
            password_input = page.locator('input[type="password"]').first
            await password_input.fill(password)
            await asyncio.sleep(0.5)
            
            login_btn = page.locator('button[type="submit"], .login-btn, button:has-text("登录")').first
            await login_btn.click()
            await asyncio.sleep(5)
            
            if await self.check_login_status(page):
                cookies = await self.get_cookies()
                return {'success': True, 'message': '登录成功', 'cookies': cookies}
            
            return {'success': False, 'message': '登录失败，请检查账号密码'}
            
        except Exception as e:
            return {'success': False, 'message': f'登录出错: {str(e)}'}
    
    async def check_login_status(self, page: Page) -> bool:
        try:
            cookies = await self.get_cookies()
            cookie_names = {c['name'] for c in cookies}
            if any(name in cookie_names for name in ['xltoken', 'xap', 'zhaopin_token', 'ZP-LOGIN-TOKEN']):
                return True
            await page.goto(self.base_url, wait_until='domcontentloaded', timeout=15000)
            await asyncio.sleep(2)
            if 'login' in page.url or 'passport' in page.url:
                return False
            user_el = page.locator('[class*="user-name"], [class*="avatar"], .zp-header__user')
            return await user_el.count() > 0
        except Exception:
            return False

    async def check_login_by_cookies(self) -> bool:
        try:
            cookies = await self.get_cookies()
            cookie_names = {c['name'] for c in cookies}
            return any(name in cookie_names for name in ['xltoken', 'xap', 'zhaopin_token', 'ZP-LOGIN-TOKEN', 'token', 'sessionid'])
        except Exception:
            return False
    
    async def fetch_messages(self, page: Page) -> List[Dict]:
        messages = []
        try:
            await page.goto(self.message_url, wait_until='networkidle', timeout=30000)
            await asyncio.sleep(3)
            
            msg_items = page.locator('.message-item, .msg-item, [class*="message-list"] > div, [class*="inbox"] > div')
            count = await msg_items.count()
            
            for i in range(min(count, 20)):
                try:
                    item = msg_items.nth(i)
                    sender_name = ''
                    content = ''
                    job_title = ''
                    sender_company = ''
                    
                    name_el = item.locator('[class*="name"], [class*="sender"]').first
                    if await name_el.count() > 0:
                        sender_name = (await name_el.text_content() or '').strip()
                    
                    msg_el = item.locator('[class*="content"], [class*="text"], [class*="msg"]').first
                    if await msg_el.count() > 0:
                        content = (await msg_el.text_content() or '').strip()
                    
                    company_el = item.locator('[class*="company"]').first
                    if await company_el.count() > 0:
                        sender_company = (await company_el.text_content() or '').strip()
                    
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
            print(f"智联招聘 fetch messages error: {e}")
        return messages