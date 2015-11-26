# -*- coding: utf8 -*-
import os
import logging
import subprocess
import tempfile


__version__ = '0.1.0'


_logger = logging.getLogger("quickstartutil")
def set_logger(logger):
    global _logger
    _logger = logger


class Error(Exception):
    pass


class SystemExecError(Error):
    def __init__(self, cmd, code, msg):
        Error.__init__(self, msg)
        self.cmd = cmd
        self.code = code


class PathError(Error):
    def __init__(self, path, msg):
        Error.__init__(self, path, msg)
        self.path = path


def system(cmd):
    """raise SystemExecError on failure"""
    _logger.info('>>> %s' % cmd)
    code = os.system(cmd)
    if code != 0:
        final_code = code if os.name == 'nt' else (code >> 8)
        raise SystemExecError(cmd, final_code, "os.system('%s') failed(%d)" % (cmd, final_code))


def system_output(cmd):
    """raise SystemExecError on failure"""
    try:
        return subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError as e:
        final_code = e.returncode if os.name == 'nt' else (e.returncode >> 8)
        raise SystemExecError(cmd, final_code, "subprocess.check_output('%s') failed(%d): %s" % (cmd, final_code, e))


class ChangeDirectory:
    def __init__(self, target):
        self.old_cwd = os.getcwd()
        self.target = target

    def __enter__(self):
        _logger.info(">>> cd %s", self.target)
        os.chdir(self.target)
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        _logger.info(">>> cd %s", self.old_cwd)
        os.chdir(self.old_cwd)


class _OS_Win32:
    @classmethod
    def force_remove_path(cls, path):
        if not os.path.exists(path):
            return
        if os.path.isdir(path):
            system('rd /s/q %s' % path)
        elif os.path.isfile(path):
            system('del /f/q %s' % path)
        else:
            raise PathError(path, "'%s' is not a valid file or directory path" % path)

    @classmethod
    def copy_directory(cls, src_dir, dst_dir, excludes=None):
        if excludes is None:
            system("xcopy %s\\* %s /r/i/c/k/h/e/q/y" % (src_dir, dst_dir))
        else:
            excludes_file_path = tempfile.mktemp()
            fp = file(excludes_file_path, "w")
            fp.writelines(excludes)
            fp.close()
            system("xcopy %s\\* %s /r/i/c/k/h/e/q/y/exclude:%s" % (src_dir, dst_dir, excludes_file_path))
            os.remove(excludes_file_path)

    @classmethod
    def make_dir(cls, path):
        system('mkdir %s' % path)


if os.name == 'nt':
    _os_cls = _OS_Win32
else:
    raise NotImplementedError('Unsupported os.')


def force_remove_path(path):
    """Force remove the file or directory with given path silently."""
    _os_cls.force_remove_path(path)


def copy_directory(src_dir, dst_dir, excludes=None):
    """
    Copy all the files from source directory to destination directory.
    If target directory does not exist, then create one.
    :param src_dir: the source directory
    :param dst_dir: the destination directory
    :param excludes: if not None, files with the given pattern list in excludes will not be copied
    """
    _os_cls.copy_directory(src_dir, dst_dir, excludes)


def make_dir_if_not_exist(path):
    """
    Create directory structure recursively
    any intermediate path segment (not just the rightmost) will be created if it does not exist.
    """
    if os.path.exists(path):
        return
    _os_cls.make_dir(path)
