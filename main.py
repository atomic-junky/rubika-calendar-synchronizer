import asyncio
import datetime
from dataclasses import dataclass
from html import unescape
from random import Random
from typing import List
import json
from zoneinfo import ZoneInfo
import requests
import re
import os.path
import xml.etree.ElementTree as ET

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

PARIS = ZoneInfo("Europe/Paris")
SCOPES = ['https://www.googleapis.com/auth/calendar']
session: requests.Session = None

@dataclass
class Event:
    id: int
    title: str
    start: datetime.datetime
    end: datetime.datetime
    teachers: List[str]
    location: str

    @property
    def color_id(self) -> str:
        id = Random(self.title).randint(1, 12)
        return str(id)


def browser_offset_ms() -> int:
    return -int(datetime.datetime.now(PARIS).utcoffset().total_seconds() * 1000)

PLANNING_URL = "https://extranet.rubika-edu.com/faces/Planning.xhtml"


def _input_value(page: str, name: str) -> str | None:
    """Valeur d'un <input name="..."> quel que soit l'ordre des attributs."""
    for tag in re.findall(r"<input\b[^>]*>", page):
        if re.search(rf'\bname="{re.escape(name)}"', tag):
            m = re.search(r'\bvalue="([^"]*)"', tag)
            if m:
                return unescape(m.group(1))
    return None


def open_planning(session: requests.Session) -> tuple[str, str]:
    r = session.get(PLANNING_URL)
    view_state = _input_value(r.text, "javax.faces.ViewState")
    if view_state is None:
        raise Exception("ViewState introuvable (session invalide ?)")

    base = {"form": "form", "form:largeurDivCenter": 725, "form:idInit": ""}

    r = session.post(PLANNING_URL, data={
        **base,
        "javax.faces.partial.ajax": "true",
        "javax.faces.source": "form:j_idt46",
        "javax.faces.partial.execute": "form:j_idt46",
        "javax.faces.partial.render": "form:sidebar",
        "form:j_idt46": "form:j_idt46",
        "webscolaapp.Sidebar.ID_SUBMENU": "submenu_44413",
        "javax.faces.ViewState": view_state,
    }, headers={
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "application/xml, text/xml, */*; q=0.01",
    })
    m = re.search(r'<update id="[^"]*ViewState[^"]*"><!\[CDATA\[(.*?)\]\]>', r.text, re.S)
    if m:
        view_state = m.group(1)

    r = session.post(PLANNING_URL, data={
        **base,
        "form:sidebar": "form:sidebar",
        "form:sidebar_menuid": "1_0",
        "javax.faces.ViewState": view_state,
    })
    view_state = _input_value(r.text, "javax.faces.ViewState")
    id_init = _input_value(r.text, "form:idInit")
    if not view_state or not id_init:
        with open("debug_planning.html", "w", encoding="utf-8") as f:
            f.write(r.text)
        raise Exception("Navigation vers Mon planning échouée (voir debug_planning.html)")
    return view_state, id_init


def get_schedule(month: int, year: int) -> str:
    first_day = datetime.datetime(year, month, 1)

    start_of_grid = first_day - datetime.timedelta(days=first_day.weekday())
    start_of_grid = start_of_grid.replace(tzinfo=datetime.timezone.utc)
    end_of_grid = start_of_grid + datetime.timedelta(days=42)

    start_ms = int(start_of_grid.timestamp() * 1000)
    end_ms = int(end_of_grid.timestamp() * 1000)

    week_number = first_day.isocalendar()[1]
    view_state, id_init = open_planning(session)

    data: dict = {
        'javax.faces.partial.ajax': 'true',
        'javax.faces.source': 'form:j_idt118',
        'javax.faces.partial.execute': 'form:j_idt118',
        'javax.faces.partial.render': 'form:j_idt118',
        'form:j_idt118': 'form:j_idt118',
        'form:j_idt118_start': start_ms,
        'form:j_idt118_end': end_ms,
        'form': 'form',
        'form:largeurDivCenter': 725,
        'form:idInit': id_init,
        'form:date_input': first_day.strftime("%d/%m/%Y"),
        'form:week': f'{week_number}-{first_day.year}',
        'form:j_idt118_view': 'month',
        'form:offsetFuseauNavigateur': -7200000,
        'form:onglets_activeIndex': 0,
        'form:onglets_scrollState': 0,
        'javax.faces.ViewState': view_state,
    }

    header = {
        "Accept": "application/xml, text/xml, */*; q=0.01",
        "Faces-Request": "partial/ajax",
        "X-Requested-With": "XMLHttpRequest",
        "Origin": "https://extranet.rubika-edu.com",
        "Referer": "https://extranet.rubika-edu.com/faces/Planning.xhtml",
    }

    r = session.post('https://extranet.rubika-edu.com/faces/Planning.xhtml', data=data, headers=header)

    if r.status_code != 200:
        raise Exception(f"Failed to get schedule: {r.status_code} {r.reason}")

    return r.text


def parse_schedule(schedule: str) -> list[Event]:
    try:
        root: ET.Element = ET.fromstring(schedule)
        updates: ET.Element = root.findall("./changes/update")
    except ET.ParseError as e:
        print(f"Failed to parse schedule XML: {e}")
        return []

    json_events: List[dict] = []
    for update in updates:
        try:
            json_data: dict = json.loads(update.text)
        except json.JSONDecodeError as e:
            continue
            
    json_events += json_data["events"]

    events: List[Event] = []
    for data in json_events:
        title, teachers, location = parse_title(data["title"])

        event: Event = Event(
            id=int(data["id"]),
            title=title,
            start=datetime.datetime.fromisoformat(data['start']),
            end=datetime.datetime.fromisoformat(data['end']),
            teachers=teachers,
            location=location
        )
        events.append(event)

    return events


def parse_title(raw_title: str) -> tuple[str, list[str], str]:
    parts = [p.strip() for p in re.split(r'\s*-\s*-\s*', raw_title.replace("\n", "")) if p.strip()]
    
    if not parts:
        return "", [], ""
    
    title = parts[-1]
    if len(parts) == 1:
        return title, [], ""
    
    meta_parts = [p.strip() for p in re.split(r'\s+-\s*|\s*-\s+', parts[0]) if p.strip()]
    
    if len(meta_parts) >= 2:
        teachers = [f"{meta_parts[0]} {meta_parts[1]}"]
        location = " - ".join(meta_parts[2:])
    else:
        teachers = []
        location = meta_parts[0] if meta_parts else ""
        
    return title, teachers, location

def get_middleday(time: datetime.datetime) -> datetime.datetime:
    return time.replace(hour=12, minute=0, second=0)

def is_morning(time: datetime.datetime) -> bool:
    middle_day: datetime.datetime = get_middleday(time)
    return time < middle_day

def get_gcal_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('calendar', 'v3', credentials=creds)


def sync_event_to_gcal(service, calendar_id: str, event: Event):
    time_min = (event.start - datetime.timedelta(days=3)).replace(hour=0, minute=0, second=0).isoformat()
    time_max = (event.start + datetime.timedelta(days=3)).replace(hour=23, minute=59, second=59).isoformat()
    
    unique_sync_id = f"db_event_{event.id}"
    
    gcal_existing_events = service.events().list(
        calendarId=calendar_id,
        timeMin=time_min,
        timeMax=time_max,
        singleEvents=True,
        showDeleted=False
    ).execute()
    
    body = {
        'summary': event.title,
        'location': event.location or "",
        'description': f"Enseignant·e·s : {', '.join(event.teachers)}" if event.teachers else "",
        'start': {
            'dateTime': event.start.isoformat(),
            'timeZone': 'Europe/Paris',
        },
        'end': {
            'dateTime': event.end.isoformat(),
            'timeZone': 'Europe/Paris',
        },
        'extendedProperties': {
            'private': {
                'sync_id': unique_sync_id
            }
        }
    }

    existing_items = gcal_existing_events.get('items', [])
    
    event_to_update_id = None
    is_perfect_match = False
    duplicates_to_delete = []

    for e in existing_items:
        gcal_sync_id = e.get('extendedProperties', {}).get('private', {}).get('sync_id')
        
        if gcal_sync_id == unique_sync_id:
            if not event_to_update_id:
                event_to_update_id = e["id"]
                match_summary = body['summary'] == e.get('summary', '')
                match_location = body['location'] == e.get('location', '')
                match_description = body['description'] == e.get('description', '')
                match_start = body['start']['dateTime'] == e.get('start', {}).get('dateTime')
                match_end = body['end']['dateTime'] == e.get('end', {}).get('dateTime')
                
                if match_summary and match_location and match_description and match_start and match_end:
                    is_perfect_match = True
            else:
                duplicates_to_delete.append(e["id"])

    for duplicate_id in duplicates_to_delete:
        try:
            service.events().delete(calendarId=calendar_id, eventId=duplicate_id).execute()
            print(f"[CLEANUP] Deleted duplicate GCal event ID: {duplicate_id}")
        except HttpError as err:
            print(f"[WARNING] Failed to delete duplicate {duplicate_id}: {err}")

    try:
        if event_to_update_id:
            if is_perfect_match:
                print(f"[SKIP] No changes detected for: '{event.title}' ({event.start.strftime('%Y-%m-%d %H:%M')})")
                return
            
            res = service.events().update(calendarId=calendar_id, eventId=event_to_update_id, body=body).execute()
            print(f"[UPDATE] Rescheduled/Modified: '{event.title}' -> New Time: {event.start.strftime('%H:%M')}")
        else:
            res = service.events().insert(calendarId=calendar_id, body=body).execute()
            print(f"[CREATE] Success: '{event.title}' ({event.start.strftime('%Y-%m-%d %H:%M')})")
            
    except HttpError as err:
        print(f"[ERROR] Failed to save event '{event.title}': {err}")

def get_session() -> requests.Session:
    try:
        with open('extranet.json', 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Can't read file extranet.json: {e}")
        return ""

    email = data.get("email")
    password = data.get("password")

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    }

    session = requests.Session()
    session.headers.update(headers)

    # Get the default session ID (without login).
    r1 = session.get("https://extranet.rubika-edu.com/", allow_redirects=False)
    if r1.status_code != 302:
        print(f"[GetSessionID] Unexpected status code (must be 302): {r1.status_code} {r1.reason}")
    print(f"[GetSessionID] Base session ID is {session.cookies.get('JSESSIONID', '<not found>')}")

    r2 = session.get("https://extranet.rubika-edu.com/faces/Login.xhtml", allow_redirects=True)
    if r2.status_code != 200:
        print(f"[GetSessionID] Unexpected status code (must be 200): {r1.status_code} {r1.reason}")

    headers = {
        "Accept": "application/xml, text/xml, */*; q=0.01",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    r3 = session.post(
        "https://extranet.rubika-edu.com/login",
        data={
            "username": email,
            "password": password,
            "j_idt42": "",
        },
        headers=headers,
        allow_redirects=False
    )
    if r3.status_code != 302:
        print(f"[GetSessionID] Unexpected status code (must be 302): {r1.status_code} {r1.reason}")
    print(f"[GetSessionID] User session ID is {session.cookies.get('JSESSIONID', '<not found>')} (confidential)")

    return session


schedule_lock = asyncio.Lock()

async def fetch_and_parse(month: int, year: int) -> list[Event]:
    async with schedule_lock:
        data: str = await asyncio.to_thread(get_schedule, month, year)

    if not data:
        print(f"Invalid data received for month {month}.")
        return []

    return parse_schedule(data)


def get_primary_calendar(service) -> str:
    calendars_result = service.calendarList().list().execute()
    calendars = calendars_result.get('items', [])

    for cal in calendars:
        cal_id = cal.get('id')
        if cal.get('primary'):
            return cal_id

    return "primary"


async def main():
    global session

    gcal_service = get_gcal_service()
    session = get_session()

    now = datetime.datetime.now()
    first_month = 9
    first_year = now.year if now.month >= first_month else now.year - 1

    dates: list[tuple[int, int]] = [
        (
            (first_month - 1 + i) % 12 + 1,
            first_year + (first_month - 1 + i) // 12
        )
        for i in range(12)
    ]

    results = []
    for m, y in dates:
        print(f"Fetching schedule for {m}/{y}...")
        results.append(await fetch_and_parse(m, y))
    
    events: dict[int, Event] = {}
    for month_events in results:
        for event in month_events:
            events[event.id] = event

    print(f"Found {len(events)} events.")

    for event in events.values():
        sync_event_to_gcal(gcal_service, get_primary_calendar(gcal_service), event)

    print(f"{len(events)} events synched.")


if __name__ == "__main__":
    asyncio.run(main())