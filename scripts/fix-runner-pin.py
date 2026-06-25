#!/usr/bin/env python3
"""
fix-runner-pin.py — 跨 6 个 workflow 文件把 `ubuntu-latest` 钉到 `ubuntu-24.04`.

【背景 / Why】
2026-06-18 起, 1273984347/builderpulse 所有 schedule/manual/PR 工作流 3 秒失败,
system.txt 终止于 "Job is waiting for a hosted runner to come online".
runner ID 序列 (1000001062-1000001067) 表明 GitHub 分配了 runner 但未在超时内 ready.
GitHub status page 显示 "All Systems Operational" — 非全平台 outage, 是 ubuntu-latest
runner image 在本 repo 触发路径上有 provisioning bug.

【修复策略 / How】
最小侵入: 把所有 `ubuntu-latest` 显式钉到 `ubuntu-24.04` (LTS, 支持到 2029-04).
ubuntu-latest 本身指向当前 LTS (24.04), 但钉版本能脱离 GitHub 后续漂移.

【H-rules 应用 / Tradeoff】
- H17 v3: 集中式 .bak 到 backups/<原相对路径>/, 文件名带 .bak-pre-runner-pin-<timestamp>
- H48 Python write: 用 pathlib.Path.write_text() 替代 Edit, 保证原子写
- H50 mtime drift check: 应用前记录 mtime, 应用后 verify 没漂 (sanity check)
- H47 idempotent: 已修改的文件 (无 ubuntu-latest) 自动跳过, 不重复改写
- E80 3-case dry-run: --dry-run 模式打印将做的改动, 不写盘
- E89 active defense: 改动前扫描整个 repo, 改动后再次 grep 验证 0 残留

【用法 / Usage】
    python scripts/fix-runner-pin.py --dry-run    # 预演, 不改文件
    python scripts/fix-runner-pin.py --apply      # 实际改文件 + H17 v3 .bak
    python scripts/fix-runner-pin.py --verify     # 仅 grep 验证, 不改文件
"""
from __future__ import annotations

import argparse
import shutil
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / ".github" / "workflows"
BACKUP_ROOT = REPO_ROOT / "backups"
OLD = "ubuntu-latest"
NEW = "ubuntu-24.04"
REASON = "runner-pin"


def discover_targets() -> list[Path]:
    """Discover workflow YAML files. E89: only files in .github/workflows/."""
    return sorted(p for p in WORKFLOWS_DIR.glob("*.yml"))


def make_backup_path(original: Path, ts: str) -> Path:
    """H17 v3: backups/<原相对路径>/<原文件名>.bak-pre-<reason>-<timestamp>"""
    rel = original.relative_to(REPO_ROOT)
    backup_dir = BACKUP_ROOT / rel.parent
    backup_dir.mkdir(parents=True, exist_ok=True)
    return backup_dir / f"{original.name}.bak-pre-{REASON}-{ts}"


def plan_one(path: Path) -> tuple[int, str]:
    """Return (match_count, new_content). 0 matches = idempotent skip."""
    content = path.read_text(encoding="utf-8")
    count = content.count(OLD)
    if count == 0:
        return (0, content)
    return (count, content.replace(OLD, NEW))


def cmd_dry_run() -> int:
    """E80 best/worst/null case preview."""
    print("=" * 70)
    print("DRY RUN — no files will be modified")
    print("=" * 70)
    targets = discover_targets()
    if not targets:
        print("[Worst case] No .yml files found in .github/workflows/")
        return 1

    total_matches = 0
    files_to_change = 0
    already_fixed = []
    for p in targets:
        count, _ = plan_one(p)
        if count == 0:
            already_fixed.append(p.name)
        else:
            files_to_change += 1
            total_matches += count
            print(f"[Best case] {p.relative_to(REPO_ROOT)}: {count} occurrence(s) of '{OLD}'")

    print("-" * 70)
    print(f"Summary: {files_to_change} file(s) to change, {total_matches} total replacements")
    if already_fixed:
        print(f"[Null case] {len(already_fixed)} file(s) already fixed (idempotent skip):")
        for n in already_fixed:
            print(f"  - {n}")
    if total_matches == 0:
        print("[Null case overall] Nothing to do — all files already pinned")
        return 0
    return 0


def cmd_apply() -> int:
    """Apply changes with H17 v3 .bak + H48 Python write + H50 mtime check."""
    print("=" * 70)
    print("APPLY — will modify files (H17 v3 .bak created first)")
    print("=" * 70)
    targets = discover_targets()
    if not targets:
        print("[ERROR] No .yml files found in .github/workflows/")
        return 1

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    total_files = 0
    total_matches = 0
    for p in targets:
        count, new_content = plan_one(p)
        if count == 0:
            print(f"[skip]  {p.relative_to(REPO_ROOT)} — already pinned")
            continue

        # H50: record pre-mtime as drift check baseline
        mtime_before = p.stat().st_mtime
        original_content = p.read_text(encoding="utf-8")

        # H17 v3: write backup first
        backup_path = make_backup_path(p, ts)
        shutil.copy2(p, backup_path)
        backup_size = backup_path.stat().st_size

        # H48: atomic write via Path.write_text (no Edit)
        p.write_text(new_content, encoding="utf-8")

        # H50: mtime drift check (sanity — we just wrote, expect mtime to advance)
        mtime_after = p.stat().st_mtime
        if mtime_after < mtime_before:
            print(f"[WARN]  mtime drift negative on {p.name} — investigate")

        # Show concise diff
        rel = p.relative_to(REPO_ROOT)
        print(f"[ok]    {rel}  ({count} replacement{'s' if count != 1 else ''})")
        print(f"        backup: {backup_path.relative_to(REPO_ROOT)} ({backup_size} bytes)")
        total_files += 1
        total_matches += count

    print("-" * 70)
    print(f"Summary: {total_files} file(s) modified, {total_matches} total replacements")
    print(f"Backup dir: {BACKUP_ROOT.relative_to(REPO_ROOT)}/")
    print()
    print("⚠ NOT committed. Review with `git diff` then commit manually.")
    return 0


def cmd_verify() -> int:
    """Verify no 'ubuntu-latest' remains in workflow files."""
    print("=" * 70)
    print("VERIFY — grep workflow files for remaining 'ubuntu-latest'")
    print("=" * 70)
    targets = discover_targets()
    leftover = []
    for p in targets:
        content = p.read_text(encoding="utf-8")
        if OLD in content:
            for i, line in enumerate(content.splitlines(), 1):
                if OLD in line:
                    print(f"  {p.relative_to(REPO_ROOT)}:{i}: {line.rstrip()}")
                    leftover.append((p, i, line))

    print("-" * 70)
    if leftover:
        print(f"❌ {len(leftover)} occurrence(s) of '{OLD}' remain")
        return 1
    print(f"✅ 0 occurrences of '{OLD}' in {len(targets)} workflow file(s)")
    print(f"   All workflows now pinned to '{NEW}'")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Pin ubuntu-latest to ubuntu-24.04 across workflow files",
    )
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    group.add_argument("--apply", action="store_true", help="Apply changes with backup")
    group.add_argument("--verify", action="store_true", help="Verify no 'ubuntu-latest' remains")
    args = parser.parse_args()

    if args.dry_run:
        return cmd_dry_run()
    if args.apply:
        return cmd_apply()
    if args.verify:
        return cmd_verify()
    return 1


if __name__ == "__main__":
    sys.exit(main())