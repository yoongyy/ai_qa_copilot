from __future__ import annotations

from datetime import datetime, timezone
import uuid

from fastapi import APIRouter, HTTPException

from .db import get_conn
from .models import (
  CalendarResponse,
  LinkCqRequest,
  MessagesResponse,
  NominationCreateRequest,
  NominationResponse,
  ReadinessPatchRequest,
  SchedulePatchRequest,
  SignCqRequest,
)

router = APIRouter(tags=['vessel_connect'])


def utc_now() -> str:
  return datetime.now(timezone.utc).isoformat()


def row_to_nomination(row) -> NominationResponse:
  return NominationResponse(
    id=row['id'],
    vessel_name=row['vessel_name'],
    port=row['port'],
    eta=row['eta'],
    readiness_time=row['readiness_time'],
    scheduled_eta=row['scheduled_eta'],
    jetty=row['jetty'],
    cq_id=row['cq_id'],
    created_at=row['created_at'],
  )


def add_message(conn, nomination_id: str, body: str) -> None:
  conn.execute(
    'INSERT INTO messages (nomination_id, body, created_at) VALUES (?, ?, ?)',
    (nomination_id, body, utc_now()),
  )


def create_calendar_event(conn, nomination_id: str, title: str, start_time: str) -> None:
  conn.execute(
    'INSERT INTO calendar_events (nomination_id, title, start_time, created_at) VALUES (?, ?, ?, ?)',
    (nomination_id, title, start_time, utc_now()),
  )


def get_nomination_or_404(conn, nomination_id: str):
  row = conn.execute('SELECT * FROM nominations WHERE id = ?', (nomination_id,)).fetchone()
  if not row:
    raise HTTPException(status_code=404, detail='Nomination not found')
  return row


@router.post('/vc/nominations', response_model=NominationResponse)
def create_nomination(payload: NominationCreateRequest) -> NominationResponse:
  conn = get_conn()
  nomination_id = f'nom-{uuid.uuid4().hex[:8]}'
  created_at = utc_now()

  try:
    conn.execute(
      'INSERT INTO nominations (id, vessel_name, port, eta, created_at) VALUES (?, ?, ?, ?, ?)',
      (nomination_id, payload.vessel_name, payload.port, payload.eta, created_at),
    )
    add_message(conn, nomination_id, f'Nomination created for {payload.vessel_name}')
    conn.commit()
    row = conn.execute('SELECT * FROM nominations WHERE id = ?', (nomination_id,)).fetchone()
    return row_to_nomination(row)
  finally:
    conn.close()


@router.get('/vc/nominations/{nomination_id}', response_model=NominationResponse)
def get_nomination(nomination_id: str) -> NominationResponse:
  conn = get_conn()
  try:
    row = get_nomination_or_404(conn, nomination_id)
    return row_to_nomination(row)
  finally:
    conn.close()


@router.patch('/vc/nominations/{nomination_id}/readiness', response_model=NominationResponse)
def update_readiness(nomination_id: str, payload: ReadinessPatchRequest) -> NominationResponse:
  conn = get_conn()
  try:
    get_nomination_or_404(conn, nomination_id)
    conn.execute(
      'UPDATE nominations SET readiness_time = ? WHERE id = ?',
      (payload.readiness_time, nomination_id),
    )
    add_message(conn, nomination_id, f'Readiness updated to {payload.readiness_time}')
    conn.commit()
    row = conn.execute('SELECT * FROM nominations WHERE id = ?', (nomination_id,)).fetchone()
    return row_to_nomination(row)
  finally:
    conn.close()


@router.patch('/vc/nominations/{nomination_id}/schedule', response_model=NominationResponse)
def update_schedule(nomination_id: str, payload: SchedulePatchRequest) -> NominationResponse:
  conn = get_conn()
  try:
    get_nomination_or_404(conn, nomination_id)
    conn.execute(
      'UPDATE nominations SET jetty = ?, scheduled_eta = ? WHERE id = ?',
      (payload.jetty, payload.eta, nomination_id),
    )
    add_message(conn, nomination_id, f'Schedule updated to {payload.jetty} / {payload.eta}')

    create_calendar_event(conn, nomination_id, f"Jetty call at {payload.jetty}", payload.eta)

    conn.commit()
    row = conn.execute('SELECT * FROM nominations WHERE id = ?', (nomination_id,)).fetchone()
    return row_to_nomination(row)
  finally:
    conn.close()


@router.post('/vc/nominations/{nomination_id}/link-cq')
def link_cq(nomination_id: str, payload: LinkCqRequest):
  conn = get_conn()
  try:
    get_nomination_or_404(conn, nomination_id)
    cq_id = payload.cq_reference or f'cq-{uuid.uuid4().hex[:8]}'
    conn.execute(
      'INSERT INTO cqs (id, nomination_id, status, created_at) VALUES (?, ?, ?, ?)',
      (cq_id, nomination_id, 'linked', utc_now()),
    )
    conn.execute('UPDATE nominations SET cq_id = ? WHERE id = ?', (cq_id, nomination_id))
    add_message(conn, nomination_id, f'CQ linked: {cq_id}')
    conn.commit()
    return {'cq_id': cq_id, 'status': 'linked'}
  finally:
    conn.close()


@router.post('/vc/cq/{cq_id}/sign')
def sign_cq(cq_id: str, payload: SignCqRequest):
  conn = get_conn()
  try:
    cq_row = conn.execute('SELECT * FROM cqs WHERE id = ?', (cq_id,)).fetchone()
    if not cq_row:
      raise HTTPException(status_code=404, detail='CQ not found')

    conn.execute(
      'UPDATE cqs SET status = ?, signed_by = ?, signed_at = ? WHERE id = ?',
      ('signed', payload.signed_by, utc_now(), cq_id),
    )
    add_message(conn, cq_row['nomination_id'], f'CQ signed by {payload.signed_by}')
    conn.commit()
    return {'cq_id': cq_id, 'status': 'signed', 'signed_by': payload.signed_by}
  finally:
    conn.close()


@router.get('/vc/nominations/{nomination_id}/messages', response_model=MessagesResponse)
def get_messages(nomination_id: str) -> MessagesResponse:
  conn = get_conn()
  try:
    get_nomination_or_404(conn, nomination_id)
    rows = conn.execute(
      'SELECT id, nomination_id, body, created_at FROM messages WHERE nomination_id = ? ORDER BY id ASC',
      (nomination_id,),
    ).fetchall()
    return MessagesResponse(messages=[dict(row) for row in rows])
  finally:
    conn.close()


@router.get('/vc/nominations/{nomination_id}/calendar', response_model=CalendarResponse)
def get_calendar(nomination_id: str) -> CalendarResponse:
  conn = get_conn()
  try:
    get_nomination_or_404(conn, nomination_id)
    rows = conn.execute(
      'SELECT id, nomination_id, title, start_time, created_at FROM calendar_events WHERE nomination_id = ? ORDER BY id ASC',
      (nomination_id,),
    ).fetchall()
    return CalendarResponse(events=[dict(row) for row in rows])
  finally:
    conn.close()
