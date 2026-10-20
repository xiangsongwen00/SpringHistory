"""Experimental desktop adapter. Invoked only by an explicit reader button.

No hard-coded screen coordinates; target only a process launched by this adapter.
UI assumptions still need live verification on the installed legacy app.
"""
from pathlib import Path
import subprocess
import time
import json
import re


class NavigationError(RuntimeError):
    pass


def same_book_label(text, book):
    compact = re.sub(r'\s+', '', str(text))
    book = re.sub(r'\s+', '', book)
    return compact == book or (compact.startswith(book) and
        compact[len(book):len(book)+1] in ('(', '（', '[', '【'))


def selection_snapshot(dialog, item, book):
    """Read actual controls; selected-book list is separate from tree highlight."""
    lists, controls, errors = [], [], []
    for control in dialog.descendants():
        try:
            cls = control.class_name()
            controls.append({'class': cls, 'text': control.window_text()[:160]})
            if cls == 'SysListView32' or cls.lower().endswith('listbox'):
                texts = [str(s).strip() for s in control.texts() if str(s).strip()]
                lists.append({'class': cls, 'texts': texts[:100]})
        except Exception as error:
            errors.append(str(error)[:160])
    state = checked = None
    try:
        state = int(item.state())
    except Exception as error:
        errors.append('state: ' + str(error)[:160])
    try:
        checked = bool(item.is_checked())
    except Exception as error:
        errors.append('is_checked: ' + str(error)[:160])
    return {'book': book, 'itemText': item.text(), 'treeState': state,
            'stateImageIndex': None if state is None else (state >> 12) & 15,
            'standardChecked': checked, 'selectedLists': lists,
            'selectedBookFound': any(same_book_label(t, book)
                for group in lists for t in group['texts']),
            'controls': controls[:100], 'readErrors': errors[:10]}


def confirmed_selection(snapshot):
    # The visible selected-book list also covers legacy/custom check images.
    # Do not treat a highlighted tree item or any nonzero image as checked.
    return snapshot['selectedBookFound'] or (
        snapshot['standardChecked'] is True and snapshot['stateImageIndex'] == 2)


def state_icon_center(label_left, y, target_handle, hit_test):
    """Find the interior of this item's checkbox, never an icon/text edge."""
    xs = []
    for x in range(max(0, label_left - 128), label_left + 1):
        flags, handle = hit_test(x, y)
        if flags & 0x40 and handle == target_handle:  # TVHT_ONITEMSTATEICON
            xs.append(x)
    if not xs or not 4 <= len(xs) <= 64 or xs[-1] - xs[0] + 1 != len(xs):
        raise NavigationError('未唯一识别目标书目的方框内部，未点击。')
    return {'x': (xs[0] + xs[-1]) // 2, 'y': y,
            'left': xs[0], 'right': xs[-1], 'hitFlags': 0x40}


def click_book_checkbox(item):
    import ctypes
    from pywinauto.handleprops import is64bitprocess
    from pywinauto.remote_memory_block import RemoteMemoryBlock
    tree = item.tree_ctrl
    target_bits = 64 if is64bitprocess(tree.process_id()) else 32
    # Match the target process ABI, including the hItem field offset. The
    # bundled helper uses the host Python layout for this particular structure.
    class HitTest(ctypes.Structure):
        _fields_ = [('x', ctypes.c_int32), ('y', ctypes.c_int32),
                    ('flags', ctypes.c_uint32),
                    ('hItem', ctypes.c_uint64 if target_bits == 64 else ctypes.c_uint32)]
    item.ensure_visible()
    rect = item.client_rect()
    if rect is None or rect.bottom <= rect.top:
        raise NavigationError('目标书目不可见，未点击。')
    remote = RemoteMemoryBlock(tree)
    mask = (1 << target_bits) - 1
    target = int(item.elem) & mask
    def hit_test(x, y):
        hit = HitTest(x=x, y=y)
        remote.Write(hit)
        tree.send_message(0x1111, 0, remote)  # TVM_HITTEST
        remote.Read(hit)
        return int(hit.flags), int(hit.hItem)
    try:
        point = state_icon_center(rect.left, (rect.top + rect.bottom) // 2,
                                  target, hit_test)
        flags, handle = hit_test(point['x'], point['y'])
        if not flags & 0x40 or handle != target:
            raise NavigationError('方框位置发生变化，未点击。')
        point['targetBits'] = target_bits
        point['targetHandle'] = target
        from win_coordinates import physical_client_point, physical_dpi_context
        from pywinauto import mouse
        with physical_dpi_context():
            screen = physical_client_point(tree.handle, point['x'], point['y'])
            point['screenX'], point['screenY'] = screen
            mouse.click(coords=screen)
        return point
    finally:
        del remote


def ensure_book_selected(dialog, item, book, report, timeout=3):
    before = selection_snapshot(dialog, item, book)
    after = before
    trace = {'before': before, 'action': 'already_selected'}
    diagnostic = Path(__file__).resolve().parent / 'diagnostics' / 'selection-latest.json'
    try:
        if not confirmed_selection(before):
            report(stage='selecting_book', message='正在核对目标书目的方框区域，点击方框中心后验证勾选。')
            dialog.set_focus()
            item.ensure_visible()
            trace['action'] = 'click_input_checkbox_center_once'
            try:
                rect = item.client_rect()
                trace['labelClientRect'] = {name: getattr(rect, name)
                    for name in ('left', 'top', 'right', 'bottom')}
            except Exception as error:
                trace['rectReadError'] = str(error)
            trace['checkboxHit'] = click_book_checkbox(item)
            deadline = time.monotonic() + timeout
            while True:
                after = selection_snapshot(dialog, item, book)
                if confirmed_selection(after):
                    break
                if time.monotonic() >= deadline:
                    raise NavigationError(
                        f"选书未获确认：state={after['treeState']}，"
                        f"状态图索引={after['stateImageIndex']}，"
                        f"标准勾选={after['standardChecked']}，"
                        f"已选列表匹配={after['selectedBookFound']}。"
                        '控件诊断见 reader/diagnostics/selection-latest.json；未重复点击，以免反选。')
                time.sleep(0.15)
        return after
    except Exception:
        try:
            diagnostic.parent.mkdir(exist_ok=True)
            screenshot = diagnostic.with_suffix('.png')
            image = dialog.capture_as_image()
            if image is None:
                raise RuntimeError('窗口截图未返回图像')
            image.save(str(screenshot))
            trace['failureScreenshot'] = screenshot.name
        except Exception as error:
            trace['screenshotError'] = str(error)
        raise
    finally:
        trace['after'] = after
        diagnostic.parent.mkdir(exist_ok=True)
        diagnostic.write_text(json.dumps(trace, ensure_ascii=False, indent=2), encoding='utf-8')


def unique(items, label):
    if len(items) != 1:
        raise NavigationError(f'{label}应唯一，实际发现{len(items)}项；已停止，未继续发送输入。')
    return items[0]


def walk_tree(tree, limit=3000):
    queue = list(tree.roots())
    count = 0
    while queue:
        item = queue.pop(0)
        count += 1
        if count > limit:
            raise NavigationError('目录过大，已停止自动遍历。')
        yield item
        item.expand()
        queue.extend(item.children())


def drive(exe, project, book, chapter, query, mode='auto', report=lambda **kw: None):
    from win_coordinates import physical_dpi_context
    with physical_dpi_context():
        return _drive(exe, project, book, chapter, query, mode, report)


def _drive(exe, project, book, chapter, query, mode='auto', report=lambda **kw: None):
    exe, project = Path(exe), Path(project)
    if not exe.is_file() or not project.is_file():
        raise NavigationError('本机程序或书库文件不存在。')
    if mode == 'book':
        process = subprocess.Popen([str(exe), str(project)], cwd=exe.parent)
        return {'stage': 'launch_requested', 'pid': process.pid,
                'message': '已向汉籍程序传入书库文件。请核对选书是否成功；尚未定位卷章或检索。'}

    # Import before launch, so a missing dependency does not leave a stray app.
    from pywinauto import Application
    app = Application(backend='win32').start(
        subprocess.list2cmdline([str(exe), str(project)]), work_dir=str(exe.parent))
    report(stage='launched', message='已启动专用汉籍窗口，正在核对控件。')
    app.wait_cpu_usage_lower(threshold=5, timeout=15)
    deadline = time.monotonic() + 15
    while True:
        windows = [w for w in app.windows() if w.is_visible()]
        if any('选择文献' in w.window_text() for w in windows): break
        if any('汉籍' in w.window_text() for w in windows) and time.monotonic() > deadline - 12: break
        if time.monotonic() >= deadline: break
        time.sleep(.2)
    chooser = [w for w in windows if '选择文献' in w.window_text()]
    if chooser:
        dialog = unique(chooser, '选择文献对话框')
        trees = dialog.descendants(class_name='SysTreeView32')
        tree = unique(trees, '书目树')
        found = [i for i in walk_tree(tree) if i.text().replace(' ', '').startswith(book)]
        item = unique(found, '目标书目')
        ensure_book_selected(dialog, item, book, report)
        button = unique([b for b in dialog.descendants(class_name='Button')
                         if b.window_text().replace('&', '').startswith('打开')], '打开按钮')
        from native_elements import invoke_button
        invoke_button(button)
        import win32gui
        def chooser_visible():
            return win32gui.IsWindow(dialog.handle) and win32gui.IsWindowVisible(dialog.handle)
        deadline = time.monotonic() + 12
        while chooser_visible() and time.monotonic() < deadline:
            time.sleep(0.2)
        if chooser_visible():
            raise NavigationError('选书窗口尚未关闭，已停止。')
    windows = [w for w in app.windows() if w.is_visible() and '汉籍' in w.window_text()]
    main = unique(windows, '汉籍主窗口')
    main.maximize()
    deadline = time.monotonic() + 5
    while not main.is_maximized() and time.monotonic() < deadline:
        time.sleep(.1)
    if not main.is_maximized():
        raise NavigationError('主窗口未确认最大化，已停止后续目录操作。')
    report(stage='window_maximized', message='书籍已加载，主窗口已最大化，正在定位目标卷章。', pid=app.process)
    trees = main.descendants(class_name='SysTreeView32')
    tree = unique(trees, '篇章目录树')
    # Exact metadata title is mandatory. A book-wide hit is never a chapter hit.
    matches = [i for i in walk_tree(tree) if i.text().strip() == chapter.strip()]
    item = unique(matches, '目标篇章')
    item.ensure_visible()
    from native_elements import double_click_tree_item
    double_click_tree_item(item)
    evidence = Path(__file__).resolve().parent / 'diagnostics'
    evidence.mkdir(exist_ok=True)
    time.sleep(.4)
    chapter_image = main.capture_as_image()
    if chapter_image is not None: chapter_image.save(str(evidence / 'chapter-latest.png'))
    report(stage='chapter_open_requested', message=f'已请求打开：{chapter}；正在准备查询。')
    if not query:
        return {'stage': 'chapter_open_requested', 'message': '已请求打开篇章，请核对正文标题。'}
    # Help: the edit inside the query ComboBox accepts literal text + Enter.
    combos = main.descendants(class_name='ComboBox')
    edits = []
    for combo in combos:
        edits.extend(combo.descendants(class_name='Edit'))
    edit = unique(edits, '查询条件输入框')
    edit.set_edit_text(query)
    if edit.window_text() != query:
        raise NavigationError('查询框内容与请求不符，未执行查询。')
    edit.type_keys('{ENTER}', set_foreground=True)
    # The legacy app shows a modal result count before exposing the list.
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        dialogs = [w for w in app.windows() if w.is_visible() and w.window_text() == '查询结果']
        if dialogs:
            dialog = unique(dialogs, '查询结果提示')
            messages = [c.window_text() for c in dialog.descendants(class_name='Static')]
            report(stage='query_result_count', message='；'.join(t for t in messages if t))
            button = unique([b for b in dialog.descendants(class_name='Button')
                if b.window_text().replace('&', '').startswith('确定')], '查询结果确定按钮')
            from native_elements import invoke_button
            invoke_button(button)
            break
        lists = main.descendants(class_name='SysListView32')
        if any(results.item_count() for results in lists): break
        time.sleep(.2)
    time.sleep(.4)
    # Query can return many chapters. Locate an exact-title result if the app
    # exposes a standard listview; otherwise report the intermediate state.
    lists = main.descendants(class_name='SysListView32')
    rows = []
    for results in lists:
        for index in range(results.item_count()):
            if results.get_item(index, 0).text().strip() == chapter.strip():
                rows.append((results, index))
    if len(rows) == 1:
        results, index = rows[0]
        results.get_item(index, 0).select()
        time.sleep(.4)
        image = main.capture_as_image()
        if image is not None: image.save(str(evidence / 'query-latest.png'))
        return {'stage': 'target_result_requested', 'message': '查询已发送，并请求显示目标卷的命中。请目视核对正文与引句；尚未标记原文已校勘。'}
    return {'stage': 'query_sent', 'message': '查询已发送；未唯一识别目标卷结果，请在汉籍结果列表选择目标卷。未标记为原文已校勘。'}
