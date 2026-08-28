"""API client for Kungsbacka Library via Arena web scraping."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
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
    is_overdue: bool

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
    """Parse a date string like '2026-08-31'."""
    if not text:
        return None
    text = text.strip()
    # Try extracting a YYYY-MM-DD pattern from the text
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        try:
            dt = datetime.strptime(match.group(1), "%Y-%m-%d")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    _LOGGER.debug("Could not parse date: %s", text)
    return None


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
        result_soup = BeautifulSoup(result_html, "html.parser")

        has_logout = result_soup.find(
            string=re.compile(r"Logga ut|logga ut|Sign out", re.IGNORECASE)
        )
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

        # Find the loans portlet by its wrapper div ID
        loans_panel = soup.find(
            "div", id=re.compile(r"p_p_id_loansWicket", re.IGNORECASE)
        )
        if not loans_panel:
            _LOGGER.warning("No loans panel found on the page")
            return []

        # Loans are in <tr> rows with id like "loan-row-id-1"
        rows = loans_panel.find_all("tr", id=re.compile(r"^loan-row-id-"))
        if not rows:
            _LOGGER.debug("No loan rows found — user may have no active loans")
            return []

        for row in rows:
            # Title: .arena-record-title a span
            title_el = row.find("div", class_="arena-record-title")
            title = ""
            if title_el:
                span = title_el.find("span")
                title = span.get_text(strip=True) if span else title_el.get_text(strip=True)

            # Author: .arena-record-author .arena-value
            author = ""
            author_el = row.find("div", class_="arena-record-author")
            if author_el:
                value_span = author_el.find("span", class_="arena-value")
                author = value_span.get_text(strip=True) if value_span else ""

            # Record ID: .arena-record-id
            record_id = ""
            id_el = row.find("span", class_="arena-record-id")
            if id_el:
                record_id = id_el.get_text(strip=True)

            # Due date: .arena-renewal-date-value
            due_date = None
            due_el = row.find("span", class_="arena-renewal-date-value")
            if due_el:
                due_date = _parse_date(due_el.get_text(strip=True))

            # Branch and loan date: .arena-renewal-branch .arena-value
            # Text is like "Fyrens bibliotek 2026-08-03"
            branch = ""
            loan_date = None
            branch_el = row.find("div", class_="arena-renewal-branch")
            if branch_el:
                value_span = branch_el.find("span", class_="arena-value")
                if value_span:
                    branch_text = value_span.get_text(strip=True)
                    # Extract the date from the end
                    loan_date = _parse_date(branch_text)
                    # Remove the date to get the branch name
                    branch = re.sub(r"\s*\d{4}-\d{2}-\d{2}\s*$", "", branch_text).strip()

            # Renewable: check row class for arena-renewal-true
            row_classes = " ".join(row.get("class", []))
            is_renewable = "arena-renewal-true" in row_classes

            # Overdue: check row class for arena-loan-overdue-true
            is_overdue = "arena-loan-overdue-true" in row_classes

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
                        is_overdue=is_overdue,
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
