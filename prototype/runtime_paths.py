"""Optional release-independent local storage; importing never creates or migrates data."""
import os
from pathlib import Path,PureWindowsPath


def data_root():
    raw=os.environ.get('STUDY_DATA_DIR')
    if raw is None:return None
    if not raw or not raw.strip() or '\x00' in raw or raw.startswith(('\\\\','//')):
        raise ValueError('STUDY_DATA_DIR must name an absolute local directory')
    path=Path(raw)
    if not path.is_absolute() or '..' in path.parts or '..' in PureWindowsPath(raw).parts:
        raise ValueError('STUDY_DATA_DIR must be absolute without parent traversal')
    for ancestor in (path,*path.parents):
        if ancestor.exists() and (ancestor.is_symlink() or bool(getattr(ancestor.lstat(),'st_file_attributes',0)&0x400)):
            raise ValueError('Linked or reparse-point data ancestors are forbidden')
    resolved=path.resolve()
    if not resolved.is_absolute() or str(resolved).startswith(('\\\\','//')) or resolved==Path(resolved.anchor):
        raise ValueError('Use a dedicated absolute local Study data directory')
    return resolved


def data_path(module_file,name):
    """Resolve a fixed leaf beneath the configured root or its legacy module path."""
    if not isinstance(name,str) or not name or name in ('.','..') or any(x in name for x in ('/','\\',':','\x00')):
        raise ValueError('A single storage leaf name is required')
    root=data_root()
    return root/name if root is not None else Path(module_file).with_name(name)
