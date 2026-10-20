import sys
import tempfile
from pathlib import Path
from unittest import TestCase, main
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from hanji_driver import ensure_book_selected, NavigationError, same_book_label, state_icon_center


class ListControl:
    def __init__(self, owner): self.owner = owner
    def class_name(self): return 'SysListView32'
    def window_text(self): return ''
    def texts(self):
        self.owner.reads += 1
        return ['已选文献名', '旧唐书(百纳本)'] if self.owner.selected or (
            self.owner.clicks and self.owner.reads >= self.owner.ready_at) else ['已选文献名']


class FakeDialog:
    def __init__(self, selected=False, ready_at=2):
        self.selected, self.ready_at = selected, ready_at
        self.clicks = self.reads = 0
    def descendants(self): return [ListControl(self)]
    def set_focus(self): pass


class FakeItem:
    def __init__(self, dialog): self.dialog = dialog
    def state(self): return 0x1000  # old control reports unchecked even after list changes
    def is_checked(self): return False
    def text(self): return '旧唐书(百纳本)[后晋·刘昫等]'
    def ensure_visible(self): pass


class SelectionTests(TestCase):
    def run_selection(self, dialog, timeout=.4):
        with tempfile.TemporaryDirectory() as directory:
            with patch('hanji_driver.__file__', str(Path(directory) / 'hanji_driver.py')):
                def click(item):
                    item.dialog.clicks += 1
                    return {'x': 67, 'y': 8}
                with patch('hanji_driver.click_book_checkbox', side_effect=click):
                    return ensure_book_selected(dialog, FakeItem(dialog), '旧唐书', lambda **kw: None, timeout)

    def test_selected_list_confirms_custom_checkbox_without_toggling(self):
        dialog = FakeDialog(selected=True)
        self.assertTrue(self.run_selection(dialog)['selectedBookFound'])
        self.assertEqual(dialog.clicks, 0)

    def test_waits_for_list_after_one_real_click(self):
        dialog = FakeDialog(ready_at=3)
        self.assertTrue(self.run_selection(dialog)['selectedBookFound'])
        self.assertEqual(dialog.clicks, 1)

    def test_unconfirmed_stops_without_repeated_toggle(self):
        dialog = FakeDialog(ready_at=100)
        with self.assertRaisesRegex(NavigationError, '状态图索引=1'):
            self.run_selection(dialog, timeout=0)
        self.assertEqual(dialog.clicks, 1)

    def test_book_prefix_does_not_match_different_title(self):
        self.assertTrue(same_book_label('旧唐书（百纳本）', '旧唐书'))
        self.assertFalse(same_book_label('旧唐书考证', '旧唐书'))

    def test_checkbox_click_is_interior_and_matches_target_handle(self):
        def hit(x, y):
            if 60 <= x <= 75: return (0x40, 123)
            if 10 <= x <= 25: return (0x40, 999)
            return (4, 123)  # book icon, never a checkbox
        point = state_icon_center(92, 8, 123, hit)
        self.assertEqual((point['x'], point['y']), (67, 8))
        self.assertNotEqual(point['x'], point['right'])

    def test_no_checkbox_hit_does_not_fall_back_to_book_text(self):
        with self.assertRaises(NavigationError):
            state_icon_center(92, 8, 123, lambda x,y: (4, 123))


if __name__ == '__main__': main()
