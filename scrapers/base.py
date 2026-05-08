import asyncio
import os
from abc import ABC, abstractmethod
from typing import List, Dict, Optional
from datetime import datetime
from playwright.async_api import async_playwright, Browser, BrowserContext, Page


# Persistent browser profile directory
USER_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'browser_profiles')


class BaseScraper(ABC):
    """Base class for all platform scrapers."""
    
    platform_name: str = ''
    base_url: str = ''
    login_url: str = ''
    message_url: str = ''
    
    def __init__(self):
        self._browser: Optional[Browser] = None
        self._context: Optional[BrowserContext] = None
        self._playwright = None
    
    def _get_profile_dir(self) -> str:
        """Get platform-specific persistent profile directory."""
        profile_dir = os.path.join(USER_DATA_DIR, self.platform_name)
        os.makedirs(profile_dir, exist_ok=True)
        return profile_dir
    
    async def start_browser(self, headless: bool = False, persistent: bool = True):
        """
        Start a Playwright browser instance.
        If persistent=True, uses a persistent browser context (saves cookies/session to disk).
        """
        self._playwright = await async_playwright().start()
        
        if persistent:
            profile_dir = self._get_profile_dir()
            self._context = await self._playwright.chromium.launch_persistent_context(
                profile_dir,
                headless=headless,
                viewport={'width': 1366, 'height': 768},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--no-sandbox',
                ],
                ignore_default_args=['--enable-automation'],
            )
            # Add stealth scripts
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
            """)
            self._browser = None  # persistent context doesn't have separate browser
        else:
            self._browser = await self._playwright.chromium.launch(
                headless=headless,
                args=['--disable-blink-features=AutomationControlled', '--no-sandbox']
            )
            self._context = await self._browser.new_context(
                viewport={'width': 1366, 'height': 768},
                user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            await self._context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                Object.defineProperty(navigator, 'languages', {get: () => ['zh-CN', 'zh', 'en']});
                Object.defineProperty(navigator, 'platform', {get: () => 'MacIntel'});
            """)
    
    async def stop_browser(self):
        """Stop the browser instance."""
        try:
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
        except Exception:
            pass
        finally:
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception:
                    pass
    
    async def get_cookies(self) -> List[Dict]:
        """Get cookies from current browser context."""
        if self._context:
            return await self._context.cookies()
        return []
    
    async def load_cookies(self, cookies: List[Dict]):
        """Load cookies into browser context."""
        if self._context and cookies:
            await self._context.add_cookies(cookies)
    
    async def open_login_page(self, page: Page) -> Dict:
        """
        Open the login page in the browser. The user will manually complete login.
        Returns: {'success': bool, 'message': str}
        """
        try:
            await page.goto(self.login_url, wait_until='domcontentloaded', timeout=30000)
            return {'success': True, 'message': f'请在浏览器中完成 {self.platform_name} 的登录操作'}
        except Exception as e:
            return {'success': False, 'message': f'打开登录页失败: {str(e)}'}

    async def check_login_by_cookies(self) -> bool:
        """
        Lightweight login status check using ONLY cookies (no navigation).
        This is safe to use during polling without disrupting the user's login process.
        Subclasses should override this with platform-specific cookie checks.
        """
        try:
            cookies = await self.get_cookies()
            cookie_names = {c['name'] for c in cookies}
            # Generic check: look for common auth-related cookie patterns
            auth_keywords = ['token', 'session', 'uid', 'user', 'login', 'auth', 'sid', 'passport']
            for name in cookie_names:
                name_lower = name.lower()
                for keyword in auth_keywords:
                    if keyword in name_lower:
                        return True
            return False
        except Exception:
            return False

    @abstractmethod
    async def login(self, username: str, password: str, page: Page) -> Dict:
        """Perform login with username/password."""
        pass

    @abstractmethod
    async def fetch_messages(self, page: Page) -> List[Dict]:
        """Fetch latest messages from the platform."""
        pass
    
    @abstractmethod
    async def check_login_status(self, page: Page) -> bool:
        """Check if user is currently logged in."""
        pass
