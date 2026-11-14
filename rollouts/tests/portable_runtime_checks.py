"""Expose the portable runner regressions through the shared check entry point."""
import unittest
from test_runtime import ArchiveTests, LifecycleTests, LargeArchiveTests

if __name__ == '__main__':
    unittest.main()
