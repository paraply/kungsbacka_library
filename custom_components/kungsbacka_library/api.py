"""API client for Kungsbacka Library via Arena web scraping."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape

import aiohttp
from bs4 import BeautifulSoup

from .const import ARENA_BASE_URL

_LOGGER = logging.getLogger(__name__)

# Pages
OVERVIEW_URL = f"{ARENA_BASE_URL}/protected/my-account/overview"
LOGIN_PAGE_URL = f"{ARENA_BASE_URL}/mina-sidor"


class ArenaApiError(Exception):
    """Raised when the Arena web interface returns an error."""


class ArenaAuthError(ArenaApiError):
    """Raised when authentication fails."""


@dataclass
class Loan:
    """A single library loan."""

    loan_id: str
    title: str
    author: str
    loan_date: datetime | None
    due_date: datetime | None
    branch: str
    is_renewable: bool

    @property
    def is_overdue(self) -> bool:
        """Return True if this loan is past its due date."""
        if self.due_date is None:
            return False
        return datetime.now().astimezone() > self.due_date

    def as_dict(self) -> dict:
        """Return loan as a plain dict for sensor attributes."""
        return {
            "loan_id": self.loan_id,
            "title": self.title,
            "author": self.author,
            "loan_date": self.loan_date.isoformat() if self.loan_date else None,
            "due_date": self.due_date.isoformat() if self.due_date else None,
            "branch": self.branch,
            "is_overdue": self.is_overdue,
            "is_renewable": self.is_renewable,
        }


def _parse_date(text: str) -> datetime | None:
    """Parse a Swedish date string like '2024-03-15' or '15 mar 2024'."""
    if not text:
        return None
    text = text.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%d/%m-%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    # Try extracting a date pattern from surrounding text
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            return datetime.strptime(match.group(1), "%Y-%m-%d")
        except ValueError:
            pass
    _LOGGER.debug("Could not parse date: %s", text)
    return None


def _extract_text(element) -> str:
    """Extract and clean text from a BeautifulSoup element."""
    if element is None:
        return ""
    return element.get_text(strip=True)


class KungsbackaLibraryAPI:
    """Client for Kungsbacka Library via Arena web scraping."""

    def __init__(
        self,
        card_number: str,
        pin: str,
    ) -> None:
        """Initialize the API client."""
        self._card_number = card_number
        self._pin = pin

    async def _create_session(self) -> aiohttp.ClientSession:
        """Create an aiohttp session with a cookie jar."""
        jar = aiohttp.CookieJar()
        return aiohttp.ClientSession(
            cookie_jar=jar,
            timeout=aiohttp.ClientTimeout(total=30),
        )

    async def _login(self, session: aiohttp.ClientSession) -> None:
        """Authenticate by submitting the Arena login form."""
        # Step 1: GET the login page to get JSESSIONID and form details
        async with session.get(LOGIN_PAGE_URL) as resp:
            if resp.status != 200:
                raise ArenaApiError(
                    f"Failed to load login page (HTTP {resp.status})"
                )
            html = await resp.text()

        soup = BeautifulSoup(html, "html.parser")

        # Find the patronLogin form
        login_form = soup.find("form", id=re.compile(r"patronLogin"))
        if not login_form:
            raise ArenaApiError("Could not find login form on the page")

        # Extract form action URL
        action_url = login_form.get("action", "")
        if not action_url:
            raise ArenaApiError("Login form has no action URL")
        # Unescape HTML entities in the URL
        action_url = unescape(str(action_url))

        # Build form data with all hidden fields
        form_data: dict[str, str] = {}
        for hidden in login_form.find_all("input", type="hidden"):
            name = hidden.get("name", "")
            if name:
                form_data[name] = hidden.get("value", "")

        # Add credentials
        form_data["openTextUsernameContainer:openTextUsername"] = self._card_number
        form_data["textPassword"] = self._pin

        _LOGGER.debug("Posting login to: %s", action_url)

        # Step 2: POST credentials
        async with session.post(
            action_url,
            data=form_data,
            allow_redirects=True,
        ) as resp:
            if resp.status != 200:
                raise ArenaApiError(
                    f"Login POST returned HTTP {resp.status}"
                )
            result_html = await resp.text()

        # Check if login succeeded by looking for sign-out indicators
        # or the absence of the login form
        result_soup = BeautifulSoup(result_html, "html.parser")

        # A successful login shows a "Logga ut" link or patron name
        has_logout = result_soup.find(
            string=re.compile(r"Logga ut|logga ut|Sign out", re.IGNORECASE)
        )
        # Or the login form is gone
        still_has_login = result_soup.find(
            "input", {"name": "textPassword"}
        )

        if still_has_login and not has_logout:
            raise ArenaAuthError(
                "Login failed — invalid library card number or PIN"
            )

        _LOGGER.debug("Login successful")

    def _parse_loans_page(self, html: str) -> list[Loan]:
        """Parse loans from the account overview page HTML."""
        soup = BeautifulSoup(html, "html.parser")
        loans: list[Loan] = []

        # Find the loans panel
        loans_panel = soup.find(
            "div", id=re.compile(r"loansWicket", re.IGNORECASE)
        )
        if not loans_panel:
            # Try broader search
            loans_panel = soup.find("div", class_=re.compile(r"arena-loans"))
        if not loans_panel:
            _LOGGER.debug("No loans panel found — user may have no active loans")
            return []

        # Each loan is wrapped in an .arena-record or similar container
        records = loans_panel.find_all(
            "div", class_=re.compile(r"arena-record(?!-)")
        )
        if not records:
            # Fallback: look for list items
            records = loans_panel.find_all("li", class_=re.compile(r"arena"))
        if not records:
            # Last resort: look for any arena-loan-details
            records = loans_panel.find_all(
                "div", class_=re.compile(r"arena-loan-details|loans-loanInfo")
            )

        for record in records:
            title_el = record.find(
                class_=re.compile(r"arena-record-title")
            )
            title = _extract_text(title_el)

            # Author can be in subtitle or a dedicated element
            author_el = record.find(
                class_=re.compile(r"arena-record-subtitle|arena-record-author")
            )
            author = _extract_text(author_el)

            # Due date
            due_date_el = record.find(
                class_=re.compile(r"arena-record-expire|arena-loan-date|due-date")
            )
            due_date_text = _extract_text(due_date_el)
            due_date = _parse_date(due_date_text)

            # Loan date (may not always be shown)
            loan_date_el = record.find(
                class_=re.compile(r"arena-loan-date")
            )
            loan_date = None
            if loan_date_el and loan_date_el != due_date_el:
                loan_date = _parse_date(_extract_text(loan_date_el))

            # Branch
            branch_el = record.find(
                class_=re.compile(r"arena-record-branch|branch")
            )
            branch = _extract_text(branch_el)

            # Record ID (from hidden input or data attribute)
            record_id = ""
            id_input = record.find("input", {"name": re.compile(r"id|loan")})
            if id_input:
                record_id = id_input.get("value", "")
            if not record_id:
                id_el = record.find(class_=re.compile(r"arena-record-id"))
                record_id = _extract_text(id_el)

            # Renewable check
            is_renewable = bool(
                record.find(class_=re.compile(r"arena-renew|arena-reloanable"))
            ) or bool(
                record.find("input", {"type": "checkbox"})
            )

            if title:
                loans.append(
                    Loan(
                        loan_id=record_id or title,
                        title=title,
                        author=author,
                        loan_date=loan_date,
                        due_date=due_date,
                        branch=branch,
                        is_renewable=is_renewable,
                    )
                )

        _LOGGER.debug("Parsed %d loans from page", len(loans))
        return loans

    async def async_get_loans(self) -> list[Loan]:
        """Login and fetch active loans by scraping the overview page."""
        async with await self._create_session() as session:
            await self._login(session)

            # Fetch the account overview page with the loans portlet
            async with session.get(OVERVIEW_URL) as resp:
                if resp.status != 200:
                    raise ArenaApiError(
                        f"Failed to load loans page (HTTP {resp.status})"
                    )
                html = await resp.text()

            return self._parse_loans_page(html)

    async def async_validate_credentials(self) -> bool:
        """Validate credentials by attempting to log in."""
        try:
            async with await self._create_session() as session:
                await self._login(session)
                return True
        except ArenaAuthError:
            return False
