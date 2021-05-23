import asyncio
from pathlib import PurePath
from typing import Optional

import aiohttp

from .config import Config
from .crawler import Crawler, CrawlerSection
from .logging import log
from .utils import fmt_real_path
from .version import NAME, VERSION


class HttpCrawler(Crawler):
    COOKIE_FILE = PurePath(".cookies")

    def __init__(
            self,
            name: str,
            section: CrawlerSection,
            config: Config,
    ) -> None:
        super().__init__(name, section, config)

        self._cookie_jar_path = self._output_dir.resolve(self.COOKIE_FILE)
        self._output_dir.register_reserved(self.COOKIE_FILE)
        self._authentication_id = 0
        self._authentication_lock = asyncio.Lock()
        self._current_cookie_jar: Optional[aiohttp.CookieJar] = None

    async def prepare_request(self) -> int:
        # We acquire the lock here to ensure we wait for any concurrent authenticate to finish.
        # This should reduce the amount of requests we make: If an authentication is in progress
        # all future requests wait for authentication to complete.
        async with self._authentication_lock:
            return self._authentication_id

    async def authenticate(self, current_id: int) -> None:
        async with self._authentication_lock:
            # Another thread successfully called authenticate in-between
            # We do not want to perform auth again, so we return here. We can
            # assume the other thread suceeded as authenticate will throw an error
            # if it failed and aborts the crawl process.
            if current_id != self._authentication_id:
                return
            await self._authenticate()
            self._authentication_id += 1
            # Saving the cookies after the first auth ensures we won't need to re-authenticate
            # on the next run, should this one be aborted or crash
            await self._save_cookies()

    async def _authenticate(self) -> None:
        """
        Performs authentication. This method must only return normally if authentication suceeded.
        In all other cases it must either retry internally or throw a terminal exception.
        """
        raise RuntimeError("_authenticate() was called but crawler doesn't provide an implementation")

    async def _save_cookies(self) -> None:
        log.explain_topic("Saving cookies")
        if not self._current_cookie_jar:
            log.explain("No cookie jar, save aborted")
            return

        try:
            self._current_cookie_jar.save(self._cookie_jar_path)
            log.explain(f"Cookies saved to {fmt_real_path(self._cookie_jar_path)}")
        except Exception:
            log.warn(f"Failed to save cookies to {fmt_real_path(self._cookie_jar_path)}")

    async def run(self) -> None:
        self._current_cookie_jar = aiohttp.CookieJar()

        try:
            self._current_cookie_jar.load(self._cookie_jar_path)
        except Exception:
            pass

        async with aiohttp.ClientSession(
                headers={"User-Agent": f"{NAME}/{VERSION}"},
                cookie_jar=self._current_cookie_jar,
        ) as session:
            self.session = session
            try:
                await super().run()
            finally:
                del self.session

        # They are saved in authenticate, but a final save won't hurt
        await self._save_cookies()
