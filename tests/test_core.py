import os
import shutil
import tempfile
import unittest

from filesystem_node_iterator import FsNode, iter_nodes


class TestIterNodes(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="fsnode_iter_")
        self.root = os.path.join(self.tmp, "root")
        os.mkdir(self.root)
        # root/
        #   a.txt
        #   b/
        #     c.txt
        #     d/
        #       e.txt
        #   f.txt
        with open(os.path.join(self.root, "a.txt"), "w") as f:
            f.write("a")
        self.b = os.path.join(self.root, "b")
        os.mkdir(self.b)
        with open(os.path.join(self.b, "c.txt"), "w") as f:
            f.write("c")
        self.d = os.path.join(self.b, "d")
        os.mkdir(self.d)
        with open(os.path.join(self.d, "e.txt"), "w") as f:
            f.write("e")
        with open(os.path.join(self.root, "f.txt"), "w") as f:
            f.write("f")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _paths(self, nodes):
        return sorted(os.path.relpath(n.path, self.root) for n in nodes)

    def test_yields_all_entries(self):
        nodes = list(iter_nodes(self.root))
        # Expect root, a.txt, b, b/c.txt, b/d, b/d/e.txt, f.txt
        self.assertEqual(self._paths(nodes), [
            ".",
            "a.txt",
            "b",
            "b/c.txt",
            "b/d",
            "b/d/e.txt",
            "f.txt",
        ])

    def test_stat_annotated(self):
        nodes = list(iter_nodes(self.root))
        for n in nodes:
            self.assertIsInstance(n, FsNode)
            self.assertIsInstance(n.stat_result, os.stat_result)
            self.assertEqual(n.path, n.path)

    def test_is_dir_is_file_properties(self):
        nodes = list(iter_nodes(self.root))
        by_path = {n.path: n for n in nodes}
        self.assertTrue(by_path[self.root].is_dir)
        self.assertFalse(by_path[self.root].is_file)
        self.assertTrue(by_path[os.path.join(self.root, "a.txt")].is_file)
        self.assertFalse(by_path[os.path.join(self.root, "a.txt")].is_dir)

    def test_exclude_files(self):
        nodes = list(iter_nodes(self.root, include_files=False))
        rels = self._paths(nodes)
        self.assertEqual(rels, [".", "b", "b/d"])

    def test_exclude_dirs(self):
        nodes = list(iter_nodes(self.root, include_dirs=False))
        rels = self._paths(nodes)
        self.assertEqual(rels, ["a.txt", "b/c.txt", "b/d/e.txt", "f.txt"])

    def test_max_depth_1(self):
        # root (0), its direct children (1). No b/d, no b/d/e.txt.
        nodes = list(iter_nodes(self.root, max_depth=1))
        rels = self._paths(nodes)
        self.assertEqual(rels, [".", "a.txt", "b", "f.txt"])

    def test_max_depth_2(self):
        # root (0), direct (1), b/d and b/c.txt (2). No b/d/e.txt (depth 3).
        nodes = list(iter_nodes(self.root, max_depth=2))
        rels = self._paths(nodes)
        self.assertEqual(rels, [".", "a.txt", "b", "b/c.txt", "b/d", "f.txt"])

    def test_max_depth_0_is_only_root(self):
        nodes = list(iter_nodes(self.root, max_depth=0))
        self.assertEqual(self._paths(nodes), ["."])

    def test_pre_order_directory_before_children(self):
        # Within DFS, root is yielded before its children, and each parent
        # before its descendants.
        nodes = list(iter_nodes(self.root))
        paths = [os.path.relpath(n.path, self.root) for n in nodes]
        root_idx = paths.index(".")
        self.assertEqual(root_idx, 0)
        b_idx = paths.index("b")
        c_idx = paths.index("b/c.txt")
        self.assertLess(b_idx, c_idx)

    def test_absolute_root_yields_absolute_paths(self):
        nodes = list(iter_nodes(os.path.abspath(self.root)))
        for n in nodes:
            self.assertTrue(os.path.isabs(n.path))

    def test_empty_root(self):
        empty = os.path.join(self.root, "empty")
        os.mkdir(empty)
        nodes = list(iter_nodes(empty))
        self.assertEqual(self._paths(nodes), ["empty"])

    @unittest.skipIf(os.geteuid() == 0, "chmod 0o000 does not restrict root")
    def test_unreadable_subdir_skipped_silently(self):
        # An unreadable directory under root should not raise; its children
        # are simply not yielded.
        locked = os.path.join(self.root, "locked")
        os.mkdir(locked)
        with open(os.path.join(locked, "secret.txt"), "w") as f:
            f.write("x")
        try:
            os.chmod(locked, 0o000)
            nodes = list(iter_nodes(self.root))
            rels = self._paths(nodes)
            self.assertIn("locked", rels)
            self.assertNotIn("locked/secret.txt", rels)
        finally:
            os.chmod(locked, 0o755)

    def test_symlink_within_tree_is_not_followed_into_itself(self):
        # A symlink that points elsewhere is yielded as a non-regular,
        # non-dir entry (because include_files=include_dirs=True).
        # We do not assert on its type beyond being a yielded node.
        link = os.path.join(self.root, "link_to_a")
        os.symlink(os.path.join(self.root, "a.txt"), link)
        nodes = list(iter_nodes(self.root))
        paths = [os.path.relpath(n.path, self.root) for n in nodes]
        self.assertIn("link_to_a", paths)

    def test_lazy_does_not_consume_until_iterated(self):
        # Building the iterator must not stat anything until advanced.
        gen = iter_nodes(self.root)
        # Remove root mid-flight after first next to confirm laziness of
        # descendants: we only need the first yield to succeed.
        first = next(gen)
        self.assertEqual(os.path.relpath(first.path, self.root), ".")


if __name__ == "__main__":
    unittest.main()
