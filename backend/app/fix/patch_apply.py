from __future__ import annotations

import re
from pathlib import Path


class PatchApplyError(Exception):
  pass


def _normalize_path(path: str) -> str:
  path = path.strip()
  if path.startswith('a/') or path.startswith('b/'):
    return path[2:]
  return path


def apply_unified_diff(original_text: str, diff_text: str) -> str:
  original_lines = original_text.splitlines(keepends=True)
  out_lines = []
  idx = 0

  lines = diff_text.splitlines()
  i = 0

  while i < len(lines):
    line = lines[i]
    if not line.startswith('@@'):
      i += 1
      continue

    match = re.match(r'^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@', line)
    if not match:
      raise PatchApplyError(f'Invalid hunk header: {line}')

    old_start = int(match.group(1)) - 1
    out_lines.extend(original_lines[idx:old_start])
    idx = old_start
    i += 1

    while i < len(lines) and not lines[i].startswith('@@'):
      hunk_line = lines[i]
      if hunk_line.startswith(' '):
        expected = hunk_line[1:] + '\n'
        if idx >= len(original_lines) or original_lines[idx] != expected:
          raise PatchApplyError('Context mismatch while applying patch')
        out_lines.append(original_lines[idx])
        idx += 1
      elif hunk_line.startswith('-'):
        expected = hunk_line[1:] + '\n'
        if idx >= len(original_lines) or original_lines[idx] != expected:
          raise PatchApplyError('Removal mismatch while applying patch')
        idx += 1
      elif hunk_line.startswith('+'):
        out_lines.append(hunk_line[1:] + '\n')
      elif hunk_line.startswith('\\'):
        pass
      else:
        raise PatchApplyError(f'Unknown patch line: {hunk_line}')
      i += 1

  out_lines.extend(original_lines[idx:])
  return ''.join(out_lines)


def apply_demo_patch(diff_text: str, project_root: Path) -> tuple[bool, str]:
  allowed_target = (project_root / 'backend' / 'app' / 'vc_api.py').resolve()

  plus_path = None
  for line in diff_text.splitlines():
    if line.startswith('+++ '):
      plus_path = _normalize_path(line.replace('+++ ', '', 1))
      break

  if not plus_path:
    return False, 'Patch rejected: missing +++ target path.'

  target_path = (project_root / plus_path).resolve()
  if target_path != allowed_target:
    return False, f'Patch rejected: only {allowed_target} can be modified.'

  try:
    original = target_path.read_text(encoding='utf-8')
    updated = apply_unified_diff(original, diff_text)
    target_path.write_text(updated, encoding='utf-8')
    return True, f'Patch applied to {target_path}'
  except PatchApplyError as exc:
    return False, f'Patch rejected: {exc}'
  except Exception as exc:  # pragma: no cover
    return False, f'Patch apply error: {exc}'
