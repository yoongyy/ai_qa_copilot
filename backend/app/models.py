from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class NominationCreateRequest(BaseModel):
  vessel_name: str = Field(min_length=2)
  port: str = Field(min_length=2)
  eta: str = Field(description='ISO timestamp')


class ReadinessPatchRequest(BaseModel):
  readiness_time: str = Field(description='ISO timestamp')


class SchedulePatchRequest(BaseModel):
  jetty: str = Field(min_length=1)
  eta: str = Field(description='ISO timestamp')


class LinkCqRequest(BaseModel):
  cq_reference: Optional[str] = None


class SignCqRequest(BaseModel):
  signed_by: str = Field(min_length=2)


class MessageItem(BaseModel):
  id: int
  nomination_id: str
  body: str
  created_at: str


class CalendarEventItem(BaseModel):
  id: int
  nomination_id: str
  title: str
  start_time: str
  created_at: str


class NominationResponse(BaseModel):
  id: str
  vessel_name: str
  port: str
  eta: str
  readiness_time: Optional[str] = None
  scheduled_eta: Optional[str] = None
  jetty: Optional[str] = None
  cq_id: Optional[str] = None
  created_at: str


class MessagesResponse(BaseModel):
  messages: List[MessageItem]


class CalendarResponse(BaseModel):
  events: List[CalendarEventItem]
