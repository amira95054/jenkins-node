# filesystem_node_iterator

Lazily walks a filesystem tree and yields each entry as an `FsNode` containing the path and its `os.stat_result`, with optional filtering by type, depth, and device boundary.

## Usage

```python
import os
import tempfile

from filesystem_node_iterator import iter_nodes, FsNode

with tempfile.TemporaryDirectory() as root:
    for name in ("a.txt", "b/c.txt"):
        path = os.path.join(root, name)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(name)

    for node in iter_nodes(root, include_files=True, include_dirs=True, max_depth=3):
        print(node.path, node.is_dir, node.stat_result.st_size)
```

`iter_nodes(root, *, include_files=True, include_dirs=True, max_depth=None, same_device=False)` returns an iterator of `FsNode(path: str, stat_result: os.stat_result)`. `FsNode` exposes `is_dir` and `is_file` properties derived from the stat result.

## Why

`os.walk` yields `(dirpath, dirnames, filenames)` tuples and forces you to re-stat every entry you care about. This library gives you the stat up front in one call, a depth limit without manual bookkeeping, and an option to stop at mount points so a walk of `/` does not wander into `/proc` or other mounted filesystems. The trade-off is that it holds nothing for you: no tree structure, no parent links, no accumulated counts. If you need those, build them on top of the yielded records.

## Edge cases you will hit

- The root itself is always yielded at depth 0. If you only want descendants, skip the first item or call `iter_nodes` on the root's children.
- `max_depth` counts edges from root, not path-separator segments. Depth 1 means the root's direct children only.
- `same_device=True` compares the device of each directory against the root's device using a follow-stat (not lstat), so a bind mount on Linux will be treated as a device boundary if `st_dev` differs. Symlinks themselves are never followed during traversal; only directory entries are descended into.
- Unreadable directories are skipped silently, as are entries that vanish between listing and stat. The iterator does not raise `OSError` for these transient conditions.
- Non-regular, non-directory entries (symlinks, fifos, sockets, devices) are yielded only when both `include_files` and `include_dirs` are `True`, since the two flags are treated as a binary split of the namespace rather than a complete type taxonomy.
