from __future__ import annotations

import base64
from dataclasses import dataclass
from io import BytesIO
import math
import os
import re
import uuid
from pathlib import Path
from typing import Dict, List


@dataclass
class Chunk:
  chunk_id: str
  page: int
  text: str


DOC_STORE: Dict[str, List[Chunk]] = {}
EMBEDDING_CACHE: Dict[str, List[List[float]]] = {}

BACKEND_DIR = Path(__file__).resolve().parents[2]
SAMPLE_TEXT_PATH = BACKEND_DIR / 'data' / 'vessel_connect_excerpt.txt'


def _tokenize(text: str) -> List[str]:
  return [t for t in re.findall(r'[a-zA-Z0-9]+', text.lower()) if len(t) > 2]


def _chunk_page_text(page_num: int, text: str) -> List[Chunk]:
  paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
  chunks: List[Chunk] = []
  for paragraph in paragraphs:
    if len(paragraph) <= 700:
      chunks.append(Chunk(chunk_id=uuid.uuid4().hex[:8], page=page_num, text=paragraph))
      continue

    # Keep chunking simple and deterministic for demo.
    for idx in range(0, len(paragraph), 650):
      part = paragraph[idx : idx + 650]
      if part.strip():
        chunks.append(Chunk(chunk_id=uuid.uuid4().hex[:8], page=page_num, text=part.strip()))
  return chunks


def _extract_pdf_text(pdf_base64: str) -> List[Chunk]:
  try:
    import pdfplumber
  except Exception as exc:  # pragma: no cover
    raise RuntimeError('pdfplumber is required to index PDF files') from exc

  decoded = base64.b64decode(pdf_base64)
  chunks: List[Chunk] = []
  with pdfplumber.open(BytesIO(decoded)) as pdf:
    for page_index, page in enumerate(pdf.pages, start=1):
      text = page.extract_text() or ''
      if text.strip():
        chunks.extend(_chunk_page_text(page_index, text))

  return chunks


def _load_sample_text() -> List[Chunk]:
  text = SAMPLE_TEXT_PATH.read_text(encoding='utf-8')
  pseudo_pages = [p.strip() for p in text.split('\n===PAGE===\n') if p.strip()]
  chunks: List[Chunk] = []
  for i, content in enumerate(pseudo_pages, start=1):
    chunks.extend(_chunk_page_text(i, content))
  return chunks


def index_document(pdf_base64: str | None, use_sample: bool) -> tuple[str, int]:
  if pdf_base64:
    try:
      chunks = _extract_pdf_text(pdf_base64)
    except Exception:
      chunks = _load_sample_text()
  elif use_sample:
    chunks = _load_sample_text()
  else:
    chunks = _load_sample_text()

  if not chunks:
    chunks = _load_sample_text()

  doc_id = f'doc-{uuid.uuid4().hex[:10]}'
  DOC_STORE[doc_id] = chunks
  return doc_id, len(chunks)


def get_doc_chunks(doc_id: str) -> List[Chunk]:
  return DOC_STORE.get(doc_id, [])


def _keyword_retrieve(chunks: List[Chunk], query: str, top_k: int) -> List[Chunk]:
  query_tokens = _tokenize(query)
  scored = []
  for chunk in chunks:
    text = chunk.text.lower()
    score = 0.0
    for token in query_tokens:
      score += text.count(token)
    if score > 0:
      scored.append((score, chunk))

  scored.sort(key=lambda item: item[0], reverse=True)
  if scored:
    return [chunk for _, chunk in scored[:top_k]]
  return chunks[:top_k]


def _cosine(a: List[float], b: List[float]) -> float:
  dot = sum(x * y for x, y in zip(a, b))
  norm_a = math.sqrt(sum(x * x for x in a))
  norm_b = math.sqrt(sum(y * y for y in b))
  if norm_a == 0 or norm_b == 0:
    return 0.0
  return dot / (norm_a * norm_b)


def _embedding_retrieve(chunks: List[Chunk], query: str, top_k: int) -> List[Chunk]:
  try:
    from openai import OpenAI
  except Exception:
    return _keyword_retrieve(chunks, query, top_k)

  api_key = os.getenv('OPENAI_API_KEY')
  if not api_key:
    return _keyword_retrieve(chunks, query, top_k)

  client = OpenAI(api_key=api_key)
  cache_key = '|'.join([c.chunk_id for c in chunks])

  if cache_key not in EMBEDDING_CACHE:
    input_texts = [c.text for c in chunks]
    emb_resp = client.embeddings.create(model='text-embedding-3-small', input=input_texts)
    EMBEDDING_CACHE[cache_key] = [item.embedding for item in emb_resp.data]

  query_vec = client.embeddings.create(model='text-embedding-3-small', input=[query]).data[0].embedding
  chunk_vectors = EMBEDDING_CACHE[cache_key]

  scored = []
  for chunk, vector in zip(chunks, chunk_vectors):
    scored.append((_cosine(query_vec, vector), chunk))

  scored.sort(key=lambda item: item[0], reverse=True)
  return [chunk for _, chunk in scored[:top_k]]


def retrieve_chunks(doc_id: str, query: str, top_k: int = 4) -> List[Chunk]:
  chunks = get_doc_chunks(doc_id)
  if not chunks:
    return []

  if os.getenv('OPENAI_API_KEY'):
    try:
      return _embedding_retrieve(chunks, query, top_k)
    except Exception:
      return _keyword_retrieve(chunks, query, top_k)

  return _keyword_retrieve(chunks, query, top_k)
