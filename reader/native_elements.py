"""Semantic actions on the legacy app's standard native elements."""
import ctypes


def double_click_tree_item(item):
    from pywinauto import mouse
    from win_coordinates import physical_client_point, physical_dpi_context
    tree = item.tree_ctrl
    tree.top_level_parent().set_focus()
    item.ensure_visible()
    item.select()
    if not item.state() & 2:
        raise RuntimeError('未能选中目标目录条目')
    rect = item.client_rect()
    if rect is None: raise RuntimeError('目录条目不可见')
    with physical_dpi_context():
        screen = physical_client_point(tree.handle, (rect.left+rect.right)//2,
                                        (rect.top+rect.bottom)//2)
        mouse.double_click(coords=screen)


def invoke_button(button):
    button.send_message(0xf5)  # BM_CLICK
