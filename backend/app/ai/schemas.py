from __future__ import annotations

from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class Citation(BaseModel):
  page: int
  excerpt: str


class WorkflowSummaryItem(BaseModel):
  title: str
  detail: str
  citations: List[Citation]


class TestCaseItem(BaseModel):
  id: str
  title: str
  gherkin: str
  tags: List[str]
  citations: List[Citation]


class GeneratedFileItem(BaseModel):
  path: str
  language: str
  contents: str


class GenerateTestsResponse(BaseModel):
  workflow_summary: List[WorkflowSummaryItem]
  test_cases: List[TestCaseItem]
  generated_files: List[GeneratedFileItem]


class ProposeFixResponse(BaseModel):
  root_cause: str
  patch_diff: str
  regression_tests: List[str]
  rollout_plan: List[str]
  risk_level: str


class IndexDocRequest(BaseModel):
  pdf_base64: Optional[str] = None
  use_sample: bool = False


class IndexDocResponse(BaseModel):
  doc_id: str
  chunks_count: int


class GenerateTestsRequest(BaseModel):
  doc_id: str
  product: str = Field(default='vessel_connect')


class RunTestsResponse(BaseModel):
  pytest: dict
  playwright: dict
  artifacts: List[str]


class ProposeFixRequest(BaseModel):
  failing_logs: str
  target_files: List[str]
  context_doc_id: Optional[str] = None


class ApplyFixRequest(BaseModel):
  patch_diff: str


class ApplyFixResponse(BaseModel):
  applied: bool
  message: str


class AutoTestCaseSpec(BaseModel):
  name: str
  description: str
  runner: Literal['python_api', 'playwright_ui']
  script: str
  assertions: List[str]
  citations: List[Citation]
