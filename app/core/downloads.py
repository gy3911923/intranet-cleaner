# -*- coding: utf-8 -*-
"""下载目录管理。"""
import os

from .util import expand, human_size


def list_files(dir_path, recursive=False):
    """列出目录文件：[{path, name, size, mtime, is_dir}]。"""
    root = expand(dir_path)
    out = []
    if not os.path.isdir(root):
        return out
    if recursive:
        for r, dirs, files in os.walk(root):
            for d in dirs:
                p = os.path.join(r, d)
                out.append(_entry(p, is_dir=True))
            for f in files:
                out.append(_entry(os.path.join(r, f)))
    else:
        for e in os.scandir(root):
            if e.is_dir():
                out.append(_entry(e.path, is_dir=True))
            elif e.is_file():
                out.append(_entry(e.path))
    return out


def _entry(path, is_dir=False):
    try:
        st = os.stat(path)
        return {"path": path, "name": os.path.basename(path),
                "size": 0 if is_dir else st.st_size, "mtime": st.st_mtime,
                "is_dir": is_dir}
    except OSError:
        return {"path": path, "name": os.path.basename(path), "size": 0,
                "mtime": 0, "is_dir": is_dir}


def total_size(entries):
    return sum(e["size"] for e in entries if not e["is_dir"])


def summary(entries):
    return f"{len(entries)} 项 / 合计 {human_size(total_size(entries))}"
