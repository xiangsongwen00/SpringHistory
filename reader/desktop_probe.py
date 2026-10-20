"""Local diagnostic for the explicitly requested Hanji desktop acceptance."""
import ctypes
import json
from pathlib import Path
import argparse
import subprocess
import time

ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
from pywinauto import Desktop

ROOT = Path(__file__).resolve().parent
HANJI_EXE = Path('E:/汉籍全文检索系统/汉籍全文检索系统.exe').resolve()

def process_path(pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = ctypes.c_void_p
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle: return ''
    try:
        size = ctypes.c_ulong(32768)
        value = ctypes.create_unicode_buffer(size.value)
        kernel.QueryFullProcessImageNameW.argtypes = [ctypes.c_void_p, ctypes.c_ulong,
            ctypes.c_wchar_p, ctypes.POINTER(ctypes.c_ulong)]
        return value.value if kernel.QueryFullProcessImageNameW(handle, 0, value, ctypes.byref(size)) else ''
    finally:
        kernel.CloseHandle.argtypes = [ctypes.c_void_p]
        kernel.CloseHandle(handle)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--window', type=int)
    parser.add_argument('--launch', action='store_true')
    parser.add_argument('--expand')
    parser.add_argument('--checkbox')
    parser.add_argument('--button')
    parser.add_argument('--screen-click', nargs=2, type=int)
    parser.add_argument('--convert', nargs=2, type=int)
    parser.add_argument('--tree-list', action='store_true')
    parser.add_argument('--chapter')
    parser.add_argument('--query')
    parser.add_argument('--tree-key')
    parser.add_argument('--uia', action='store_true')
    parser.add_argument('--results', action='store_true')
    parser.add_argument('--close', action='store_true')
    args = parser.parse_args()
    if args.launch:
        process = subprocess.Popen([str(HANJI_EXE)], cwd=HANJI_EXE.parent)
        time.sleep(1.5)
        print('Launched PID', process.pid)
    desktop = Desktop(backend='win32')
    windows = [w for w in desktop.windows() if w.is_visible() and
               process_path(w.process_id()).casefold() == str(HANJI_EXE).casefold()]
    if args.window is None:
        print(json.dumps([{'handle': w.handle, 'pid': w.process_id(), 'title':w.window_text(),
                           'rect':str(w.rectangle())} for w in windows], ensure_ascii=False))
        return
    matches = [w for w in windows if w.handle == args.window]
    if len(matches) != 1: raise RuntimeError('窗口未唯一匹配')
    window = matches[0]
    if args.close:
        window.close()
        print('CLOSE REQUESTED', window.handle)
        return
    if args.results:
        for control in window.descendants(class_name='SysListView32'):
            print('RESULTS', json.dumps(control.texts(), ensure_ascii=False))
    if args.uia:
        uia = Desktop(backend='uia').window(handle=window.handle).wrapper_object()
        result = []
        for element in uia.descendants(control_type='TreeItem'):
            text = element.window_text()
            if '一八下' not in text and len(result) >= 8: continue
            row = {'text':text}
            for name in ('iface_toggle','iface_invoke','iface_selection_item','iface_legacy_iaccessible'):
                try:
                    interface = getattr(element, name)
                    row[name] = True
                    if name == 'iface_legacy_iaccessible':
                        row['defaultAction'] = interface.CurrentDefaultAction
                        row['state'] = interface.CurrentState
                except Exception: row[name] = False
            result.append(row)
        print('UIA', json.dumps(result, ensure_ascii=False))
    if args.tree_key:
        tree = window.descendants(class_name='SysTreeView32')[0]
        window.set_focus()
        tree.type_keys(args.tree_key, set_foreground=True)
        time.sleep(.6)
    if args.tree_list:
        tree = window.descendants(class_name='SysTreeView32')[0]
        titles = [i.text() for i in tree.roots()]
        print('TREE', json.dumps({'count':len(titles),'first':titles[:25],
            'target':[t for t in titles if '一八下' in t]}, ensure_ascii=False))
    if args.chapter:
        tree = window.descendants(class_name='SysTreeView32')[0]
        from hanji_driver import walk_tree
        items = [i for i in walk_tree(tree) if i.text() == args.chapter]
        if len(items) != 1: raise RuntimeError('篇章不唯一')
        item = items[0]
        window.set_focus()
        item.ensure_visible()
        from native_elements import double_click_tree_item
        double_click_tree_item(item)
        time.sleep(.7)
    if args.query:
        edit = window.descendants(class_name='ComboBox')[0].descendants(class_name='Edit')[0]
        window.set_focus()
        edit.set_edit_text(args.query)
        if edit.window_text() != args.query: raise RuntimeError('检索词不符')
        edit.type_keys('{ENTER}', set_foreground=True)
        time.sleep(1)
    if args.convert:
        from win_coordinates import physical_client_point
        tree = window.descendants(class_name='SysTreeView32')[0]
        print('CONVERT', physical_client_point(tree.handle, *args.convert))
    if args.screen_click:
        from pywinauto import mouse
        x,y = args.screen_click
        rect = window.rectangle()
        if not (rect.left <= x < rect.right and rect.top <= y < rect.bottom):
            raise RuntimeError('点击位置不在目标窗口内')
        window.set_focus()
        mouse.click(coords=(x,y))
        time.sleep(.5)
    if args.expand or args.checkbox:
        tree = window.descendants(class_name='SysTreeView32')[0]
        path = (args.expand or args.checkbox).split('/')
        item = tree.get_item(path, exact=True)
        if args.expand:
            item.expand()
        else:
            from hanji_driver import click_book_checkbox
            window.set_focus()
            print('CHECKBOX', json.dumps(click_book_checkbox(item)))
        time.sleep(.5)
        print('ITEM', item.text(), 'state', item.state())
        print('CHILDREN', json.dumps([i.text() for i in item.children()], ensure_ascii=False))
    if args.button:
        buttons = [c for c in window.descendants(class_name='Button') if c.window_text() == args.button]
        if len(buttons) != 1: raise RuntimeError('按钮不唯一')
        from pywinauto import mouse
        window.set_focus()
        point = buttons[0].rectangle().mid_point()
        mouse.click(coords=(point.x, point.y))
        time.sleep(.7)
        print('BUTTON CLICKED', args.button)
        return
    ROOT.joinpath('diagnostics').mkdir(exist_ok=True)
    image = window.capture_as_image()
    image.save(str(ROOT / 'diagnostics' / 'desktop-current.png'))
    print(json.dumps({'handle': window.handle, 'title':window.window_text(),
        'rect':str(window.rectangle()), 'controls':[
            {'handle': c.handle, 'class':c.class_name(), 'text':c.window_text()[:160],
             'rect':str(c.rectangle())} for c in window.descendants()]}, ensure_ascii=False))

if __name__ == '__main__': main()
