from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from endsplash_guard import EndSplashGuard


class FakeProcess:
    def __init__(self, name, exe):
        self.info = {'name':name,'exe':exe}
        self.pid = 101
        self.terminated = False
    def terminate(self): self.terminated = True


class GuardTests(TestCase):
    def test_only_exact_executable_path_is_terminated(self):
        target = Path('E:/汉籍全文检索系统/EndSplash.exe')
        wanted = FakeProcess('EndSplash.exe', str(target))
        elsewhere = FakeProcess('EndSplash.exe', 'E:/other/EndSplash.exe')
        app = FakeProcess('汉籍全文检索系统.exe', 'E:/汉籍全文检索系统/汉籍全文检索系统.exe')
        unreadable = FakeProcess('EndSplash.exe', None)
        guard = EndSplashGuard(target)
        with patch('endsplash_guard.psutil.process_iter', return_value=[wanted, elsewhere, app, unreadable]):
            guard.scan()
        self.assertTrue(wanted.terminated)
        self.assertFalse(any(p.terminated for p in [elsewhere, app, unreadable]))
        self.assertEqual(guard.closed, 1)
