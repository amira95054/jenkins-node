"""Lazily yield stat-annotated filesystem nodes under a root."""

from __future__ import annotations

import os
from dataclasses import dataclass
from stat import S_ISDIR, S_ISREG
from typing import Iterator, Optional, Callable


@dataclass(frozen=True)
class FsNode:
    """A single filesystem entry with its stat result.

    The path is absolute when iter_nodes is called with an absolute root,
    which makes records directly comparable across a traversal regardless of
    the process's current working directory.
    """
    path: str
    stat_result: os.stat_result

    @property
    def is_dir(self) -> bool:
        return S_ISDIR(self.stat_result.st_mode)

    @property
    def is_file(self) -> bool:
        return S_ISREG(self.stat_result.st_mode)


def iter_nodes(
    root: str,
    *,
    include_files: bool = True,
    include_dirs: bool = True,
    max_depth: Optional[int] = None,
    same_device: bool = False,
) -> Iterator[FsNode]:
    """Yield FsNode records for entries under root.

    Traversal is pre-order: a directory is yielded before its children.

    Args:
        root: Directory to walk. The yielded paths are prefixed by this string,
            so passing an absolute path yields absolute paths.
        include_files: When False, regular files are skipped.
        include_dirs: When False, directories are skipped (but still traversed
            so their file children are still reachable).
        max_depth: Maximum depth of entries to yield. The root itself is
            depth 0; its immediate children are depth 1. None means unbounded.
        same_device: When True, do not descend into directories whose device
            number differs from root's. This prevents crossing filesystem
            mount points. The root is always stat'd once to establish the
            reference device.

    Yields:
        FsNode instances for entries that match the filters.

    Choice: max_depth is measured as edges from root, not as a raw string
    prefix length. This avoids counting os.path.join separators as depth and
    makes semantics predictable regardless of platform separator width.
    """
    root_stat = os.stat(root)
    root_device = root_stat.st_dev

    # Depth-bounded DFS. We push initial children so the root itself is
    # yielded at depth 0 and its direct children at depth 1.
    #
    # A tuple of (path, depth) is used rather than a recursive generator so
    # that deep trees do not risk Python's generator-recursion limits.
    stack: list[tuple[str, int]] = [(root, 0)]

    while stack:
        path, depth = stack.pop()
        try:
            st = os.lstat(path)
        except OSError:
            # The entry may have vanished between listing the parent and
            # statting it, or may be an unreadable symlink target via lstat.
            # Skip silently; an iterator should be resilient to races.
            continue

        # File vs. dir filtering by lstat result so the caller's include_dirs
        # / include_files semantics match what is actually on disk at yield
        # time, not at a later os.walk time.
        if S_ISDIR(st.st_mode):
            if include_dirs:
                yield FsNode(path=path, stat_result=st)
        elif S_ISREG(st.st_mode):
            if include_files:
                yield FsNode(path=path, stat_result=st)
        else:
            # Non-regular, non-directory entry (fifo, socket, device, broken
            # symlink). Yield only if both filters are on, as a best effort
            # to surface "other" entries the caller explicitly asked for.
            # We pick the conservative interpretation that "include_files"
            # and "include_dirs" describe a binary split of the FS namespace
            # and do not attempt to cover exotic types.
            if include_files and include_dirs:
                yield FsNode(path=path, stat_result=st)

        # Enqueue children only for directories, only if depth permits, and
        # only if same_device is satisfied.
        if S_ISDIR(st.st_mode):
            if max_depth is None or depth < max_depth:
                # Re-stat to check device. os.lstat above gave the link's
                # stat; for directories on Linux lstat == stat in practice,
                # but we follow the link target explicitly to honor the
                # caller's device-boundary intent even on systems where a
                # directory entry itself sits on a different device than
                # what it resolves to.
                try:
                    dir_st = os.stat(path)
                except OSError:
                    continue
                if same_device and dir_st.st_dev != root_device:
                    continue
                try:
                    names = sorted(os.listdir(path))
                except OSError:
                    continue
                # Push in reverse so traversal order (within a depth level)
                    # matches sorted(listdir) order when popped from the
                    # LIFO stack.
                for name in reversed(names):
                    child = os.path.join(path, name)
                    stack.append((child, depth + 1))
