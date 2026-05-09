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

    # Cookie names that subclasses can override / extend to indicate a signed-in session.
    LOGIN_COOKIE_NAMES: set = set()
    # Optional: restrict auth-cookie matching to these domain substrings for accuracy.
    # e.g. {'zhipin'} for Boss, {'zhaopin'} for 智联. If empty, all cookies are considered.
    LOGIN_COOKIE_DOMAINS: set = set()

    def _cookie_matches_domain(self, cookie: Dict) -> bool:
        if not self.LOGIN_COOKIE_DOMAINS:
            return True
        domain = (cookie.get('domain') or '').lower()
        return any(d in domain for d in self.LOGIN_COOKIE_DOMAINS)

    async def check_login_by_cookies(self) -> bool:
        """
        Lightweight login status check using ONLY cookies (no navigation).
        Safe to use during polling without disrupting the user's login process.

        Detection strategy (in order):
          1. Exact match on subclass-declared LOGIN_COOKIE_NAMES
          2. Auth-keyword heuristic (token/session/passport/ticket/sso)
             on cookies whose domain passes LOGIN_COOKIE_DOMAINS
          3. Skip known pre-login tracking cookies (analytics, A/B)
        Subclasses normally only need to set LOGIN_COOKIE_NAMES (and optionally
        LOGIN_COOKIE_DOMAINS) — no need to override this method.
        """
        try:
            cookies = await self.get_cookies()
            scoped = [c for c in cookies if self._cookie_matches_domain(c)]
            cookie_names = {c['name'] for c in scoped}
            # 1. Exact match on known auth cookies (fast path).
            if self.LOGIN_COOKIE_NAMES and cookie_names & self.LOGIN_COOKIE_NAMES:
                return True
            # 2. Heuristic fallback.
            tracking_prefixes = (
                'hm_lvt_', 'hm_lpvt_', 'hmaccount', 'ab_', 'bid', '_ga', '_gid',
                'hm_', '__a', '__c', '__g', '__l', 'wzws_', 'acw_',
            )
            auth_keywords = ('token', 'session', 'passport', 'ticket', 'sso')
            for c in scoped:
                n = c['name'].lower()
                if any(n.startswith(p) for p in tracking_prefixes):
                    continue
                if any(k in n for k in auth_keywords) and c.get('value'):
                    return True
            return False
        except Exception:
            return False

    def is_login_url(self, url: str) -> bool:
        """Heuristic: return True if the given URL looks like a login/auth page."""
        if not url:
            return True
        u = url.lower()
        markers = ('login', 'passport', 'signin', 'sign-in', '/user/?ka=header-login', 'authorize')
        return any(m in u for m in markers)

    async def check_login_by_url(self, page: Page) -> bool:
        """
        Verify login by visiting a page that requires auth (messages page if available,
        else base_url) using a fresh page context. Returns True if the final URL is
        NOT a login/auth page.
        """
        target = self.message_url or self.base_url
        try:
            await page.goto(target, wait_until='domcontentloaded', timeout=20000)
            await asyncio.sleep(2)
            return not self.is_login_url(page.url)
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
