# -*- coding: utf8 -*-
import os
import sys
import locale
import logging
import subprocess
import tempfile
import sqlite3
import zipfile

try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree


# In python 3, os must be imported again at the end
import os
if os.name == 'nt':
    import msvcrt
    _IS_OS_WIN32 = True
else:
    _IS_OS_WIN32 = False


__version__ = '0.1.26'


__all__ = ['Error',
           'OsxError',
           'OsxSystemExecError', 'OsxPathError', 'OsxPathNotExistError', 'OsxPathAlreadyExistError', 'OsxPathTypeUnsupportedError',
           'SvnError',
           'SvnNoMessageError', 'SvnAlreadyLockedError', 'SvnBranchDestinationAlreadyExistError',
           'GitError', 
           'GitParseMetaDataError',
           'set_logger', 'set_local_encoding',
           'raw_input_nonblock',
           'Osx', 'osx',
           'Svn', 'svn',
           'Git', 'git',
           'Zip', 'zip']


if sys.version_info[0] == 3:
    _PY3 = True
    _unicode = str
    _raw_input = input
else:
    _PY3 = False
    _unicode = unicode
    _raw_input = raw_input


class Error(Exception):
    pass


class UnsupportedEncodingError(Error):
    def __init__(self, msg, encodings):
        Error.__init__(self)
        self.msg = msg
        self.encodings = encodings

    def __str__(self):
        return "Message '%s' can't decode by %s" % (self.msg, str(self.encodings))


class OsxError(Error):
    pass


class OsxSystemExecError(OsxError):
    def __init__(self, cmd, code, output, msg):
        OsxError.__init__(self, msg)
        self.cmd = cmd
        self.code = code
        self.output = output


class OsxPathError(OsxError):
    def __init__(self, path):
        OsxError.__init__(self)
        self.path = path


class OsxPathNotExistError(OsxPathError):
    def __init__(self, path):
        OsxPathError.__init__(self, path)

    def __str__(self):
        return "path '%s' not exist" % self.path


class OsxPathAlreadyExistError(OsxPathError):
    def __init__(self, path):
        OsxPathError.__init__(self, path)

    def __str__(self):
        return "path '%s' already exist" % self.path


class OsxPathTypeUnsupportedError(OsxPathError):
    def __init__(self, path, msg=None):
        OsxPathError.__init__(self, path)
        self.message = msg

    def __str__(self):
        if self.msg is None:
            return "path '%s' is unsupported type" % self.path
        else:
            return self.msg


class SvnError(Error):
    pass


class SvnNoMessageError(SvnError):
    def __init__(self, str_operation):
        SvnError.__init__(self, "svn: %s must give a message" % (str_operation))


class SvnAlreadyLockedError(SvnError):
    def __init__(self, path, lock_owner, lock_comment, lock_date):
        SvnError.__init__(self, "svn: path '%s' already locked by user '%s' at %s%s" %
                          (path, lock_owner, lock_date, '' if lock_comment == '' else ': ' + lock_comment ) )
        self.path = path
        self.lock_owner = lock_owner
        self.lock_comment = lock_comment
        self.lock_date = lock_date


class SvnBranchDestinationAlreadyExistError(SvnError):
    def __init__(self, dst):
        SvnError.__init__(self, "svn: branch destination '%s' already exist" % dst)
        self.dst = dst


class GitError(Error):
    pass


class GitParseMetaDataError(GitError):
    def __init__(self, msg):
        SvnError.__init__(self, "git meta data error: %s" % msg)


_logger = logging.getLogger('quickstartutil')
def set_logger(logger):
    global _logger
    _logger = logger


_default_local_encoding = locale.getdefaultlocale()[1]
_local_encoding = _default_local_encoding
def set_local_encoding(encoding):
    global _local_encoding
    _local_encoding = encoding


_to_unicode_str_encodings = ('utf8', _local_encoding, 'gbk')
def _to_unicode_str(s):
    if isinstance(s, _unicode):
        return s
    for encoding in _to_unicode_str_encodings:
        try:
            return s.decode(encoding)
        except:
            pass
    raise UnsupportedEncodingError(s, _to_unicode_str_encodings)


def _to_local_str(s):
    if _PY3:
        return s
    else:
        return _to_unicode_str(s).encode(_local_encoding)


def _raw_input_nonblock_win32():
    if msvcrt.kbhit():
        return _raw_input()
    return None

def raw_input_nonblock():
    """
    return result of raw_input if has keyboard input, otherwise return None
    """
    if _IS_OS_WIN32:
        return _raw_input_nonblock_win32()
    else:
        raise NotImplementedError('Unsupported os.')


class _BaseOsx:
    class ChangeDirectory:
        def __init__(self, target):
            self.old_cwd = os.getcwd()
            self.target = target

        def __enter__(self):
            _logger.info(u'>>> cd %s', _to_unicode_str(self.target))
            os.chdir(_to_local_str(self.target))
            return self

        def __exit__(self, exc_type, exc_value, exc_tb):
            _logger.info(u'>>> cd %s', _to_unicode_str(self.old_cwd))
            os.chdir(self.old_cwd)

    @classmethod
    def _fix_cmd_retcode(cls, retcode):
        return retcode if _IS_OS_WIN32 else (retcode >> 8)

    @classmethod
    def _system_exec_1(cls, cmd, shell=False):
        """
        Execute command and wait complete.
        The normal output & error will output to console.
        It's recommended for long time operation.
        :except: raise SystemCallError on failure
        """
        _logger.info(u'>>> %s' % _to_unicode_str(cmd))
        try:
            subprocess.check_call(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
        except subprocess.CalledProcessError as e:
            final_code = cls._fix_cmd_retcode(e.returncode)
            raise OsxSystemExecError(cmd, final_code, None, "subprocess.check_call failed(%d): %s" % (final_code, e))

    @classmethod
    def _system_exec_2(cls, cmd, shell=False):
        _logger.info(u'>>> %s' % _to_unicode_str(cmd))
        try:
            output = subprocess.check_output(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
            _logger.info(_to_unicode_str(output))
        except subprocess.CalledProcessError as e:
            _logger.error(_to_unicode_str(e.output))
            final_code = cls._fix_cmd_retcode(e.returncode)
            raise OsxSystemExecError(cmd, final_code, e.output, "subprocess.check_output failed(%d): %s" % (final_code, e))

    @classmethod
    def system_exec(cls, cmd, shell=False, redirect_output_to_log=False):
        """
        Execute command and wait complete.
        :param: redirect_output_to_log:
          True: OUTPUT & ERROR will redirect to the logger
          False: OUTPUT & ERROR will output to console. It's recommended for long-time operation
        :except: raise OsxSystemExecError on failure
        """
        if redirect_output_to_log:
            cls._system_exec_2(cmd, shell)
        else:
            cls._system_exec_1(cmd, shell)

    @classmethod
    def system_output(cls, cmd, shell=False):
        """
        Execute command and return it's output
        raise OsxSystemExecError on failure
        """
        try:
            return subprocess.check_output(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
        except subprocess.CalledProcessError as e:
            final_code = e.returncode if _IS_OS_WIN32 else (e.returncode >> 8)
            raise OsxSystemExecError(cmd, final_code, e.output, "subprocess.check_output failed(%d): %s" % (final_code, e))

    @classmethod
    def is_path_exist(cls, path):
        return os.path.exists(_to_local_str(path))

    @classmethod
    def is_dir(cls, path):
        return os.path.isdir(_to_local_str(path))

    @classmethod
    def is_file(cls, path):
        return os.path.isfile(_to_local_str(path))

    def __init__(self):
        self.redirect_output_to_log = False

    def set_redirect_output_to_log(self, redirect_output_to_log=True):
        self.redirect_output_to_log = redirect_output_to_log

    def exec_command(self, cmd, shell=False):
        self.system_exec(cmd, shell=shell, redirect_output_to_log=self.redirect_output_to_log)

    def exec_command_output(self, cmd, shell=False):
        return self.system_output(cmd, shell=shell)

class _Osx_Win32(_BaseOsx):
    def __init__(self):
        _BaseOsx.__init__(self)
        self._shell_command_list = ('dir', 'del', 'rd', 'md')

    def _is_shell_command(self, cmd):
        shell = False
        for shell_cmd in self._shell_command_list:
            if cmd.startswith(shell_cmd):
                shell = True
                break
        return shell

    def exec_command(self, cmd):
        return _BaseOsx.exec_command(self, cmd, self._is_shell_command(cmd))

    def exec_command_output(self, cmd):
        return _BaseOsx.exec_command_output(self, cmd, self._is_shell_command(cmd))

    def remove_path(self, path, force=True):
        """
        :param force: if set to True then un-exist path will not raise exception
        :except: OsxPathNotExistError, OsxPathTypeUnsupportedError
        """
        if not self.is_path_exist(path):
            if force:
                return
            else:
                raise OsxPathNotExistError(path)

        if self.is_dir(path):
            self.exec_command('rd /s/q %s' % os.path.normpath(path))
        elif self.is_file(path):
            self.exec_command('del /f/q %s' % os.path.normpath(path))
        else:
            raise OsxPathTypeUnsupportedError(path, "'%s' is not a valid file or directory path" % path)

    def copy_dir(self, src_dir, dst_dir, excludes=None):
        """
        Copy all the files from source directory to destination directory.
        If target directory does not exist, then create one.
        :param src_dir: the source directory
        :param dst_dir: the destination directory
        :param excludes: if not None, files with the given pattern list in excludes will not be copied
        """
        if excludes is None:
            self.exec_command('xcopy %s\\* %s /r/i/c/k/h/e/q/y' % (os.path.normpath(src_dir), os.path.normpath(dst_dir)))
        else:
            excludes_file_path = tempfile.mktemp()
            with open(excludes_file_path, 'w') as fp:
                fp.writelines(excludes)
            self.exec_command('xcopy %s\\* %s /r/i/c/k/h/e/q/y/exclude:%s' % (os.path.normpath(src_dir), os.path.normpath(dst_dir), excludes_file_path))
            os.remove(excludes_file_path)

    def make_dir(self, path, force=True):
        """
        Create directory structure recursively
        any intermediate path segment (not just the rightmost) will be created if it does not exist.
        :param force: if set to True then existed path will not raise exception
        :except: OsxPathAlreadyExistError
        """
        if self.is_path_exist(path):
            if force:
                return
            else:
                raise OsxPathAlreadyExistError(path)
        self.exec_command('md %s' % os.path.normpath(path))  # mkdir will conflict with cygwin


if _IS_OS_WIN32:
    Osx = _Osx_Win32
else:
    raise NotImplementedError('Unsupported os.')


# default Osx object
osx = Osx()


class Svn:
    """
    A svn command wrapper.

    Global param:
        user_pass: None or a tuple with username & password
        revision: can be integer or string
        revision_or_range: can be a single revision or a list/tuple range of revision
            if specified by a range, both range bound will be included.
        path_list: can be a single string or a list/tuple of path
    """

    RESOLVE_ACCEPT_BASE = 'base'
    RESOLVE_ACCEPT_WORKING = 'working'
    RESOLVE_ACCEPT_MINE_CONFLICT = 'mine-conflict'
    RESOLVE_ACCEPT_THEIRS_CONFLICT = 'theirs-conflict'
    RESOLVE_ACCEPT_MINE_FULL = 'mine-full'
    RESOLVE_ACCEPT_THEIRS_FULL = 'theirs-full'

    @classmethod
    def stringing_user_pass_option(cls, user_pass):
        s = ''
        if user_pass is not None:
            s += '--username ' + user_pass[0]
            s += ' --password ' + user_pass[1]
            s += ' --no-auth-cache'
        return s

    @classmethod
    def stringing_revision_option(cls, revision):
        if revision is None or revision == '':
            return ''
        return '-r %s' % revision

    @classmethod
    def stringing_revision_or_range_option(cls, revision_or_range):
        """
        -r M:N for revision range
        -c for single revision
        """
        if isinstance(revision_or_range, tuple) or isinstance(revision_or_range, list):
            return '-r %s:%s' % (revision_or_range[0], revision_or_range[1])
        return '-c %s' % revision_or_range

    @classmethod
    def stringing_message_option(cls, message):
        return '-m "%s"' % message

    @classmethod
    def stringing_path_list(cls, path_list):
        if isinstance(path_list, tuple) or isinstance(path_list, list):
            return ' '.join(path_list)
        else:
            return path_list

    @classmethod
    def is_url(cls, url):
        for prefix in ('file:\\\\\\', 'svn://', 'http://', 'https://'):
            if url.startswith(prefix):
                return True
        return False

    def __init__(self, user_pass=None, interactive=False):
        self.base_command = 'svn'
        self.str_user_pass_option = self.stringing_user_pass_option(user_pass)
        self.str_interactive_option = '' if interactive else '--non-interactive'
        self.osx = Osx()

    def set_base_command(self, base_command):
        self.base_command = base_command

    def set_redirect_output_to_log(self, redirect_output_to_log=True):
        self.osx.set_redirect_output_to_log(redirect_output_to_log)

    def exec_sub_command(self, sub_command):
        self.osx.exec_command(self.base_command + ' ' + sub_command + ' ' + self.str_interactive_option)

    def exec_sub_command_output(self, sub_command):
        return self.osx.exec_command_output(self.base_command + ' ' + sub_command + ' ' + self.str_interactive_option)

    def is_valid_svn_path(self, path):
        cmd = 'info ' + path
        if self.is_url(path):
            cmd += ' ' + self.str_user_pass_option
        try:
            self.exec_sub_command_output(cmd)
        except OsxSystemExecError as e:
            return False
        return True

    def get_revision_number(self, path, revision):
        """
        transform revision 'HEAD', 'BASE', 'COMMITTED', 'PREV' to integer
        """
        if isinstance(revision, int):
            return revision

        cmd = 'info ' + path
        cmd += ' --xml'
        cmd += ' ' + self.stringing_revision_option(revision)
        if self.is_url(path):
            cmd += ' ' + self.str_user_pass_option
        result = self.exec_sub_command_output(cmd)
        root = ElementTree.fromstring(result)
        entry_node = root.find('entry')
        return int(entry_node.attrib['revision'])

    def info_dict(self, path='.', revision='HEAD'):
        cmd = 'info ' + path
        cmd += ' --xml'
        cmd += ' ' + self.stringing_revision_option(revision)
        if self.is_url(path):
            cmd += ' ' + self.str_user_pass_option
        result = self.exec_sub_command_output(cmd)
        root = ElementTree.fromstring(result)
        entry_node = root.find('entry')

        ret = {}
        ret['#kind'] = entry_node.attrib['kind']
        ret['#path'] = entry_node.attrib['path']
        ret['#revision'] = int(entry_node.attrib['revision'])
        ret['url'] = entry_node.find('url').text
        ret['relative-url'] = entry_node.find('relative-url').text

        repository_node = entry_node.find('repository')
        repository = {}
        ret['repository'] = repository
        repository['root'] = repository_node.find('root').text
        repository['uuid'] = repository_node.find('uuid').text

        wc_info_node = entry_node.find('wc-info')
        if wc_info_node is not None:  # svn info url has no wc-info node
            wc_info = {}
            ret['wc-info'] = wc_info
            wc_info['wcroot-abspath'] = wc_info_node.find('wcroot-abspath').text
            wc_info['uuid'] = wc_info_node.find('schedule').text
            wc_info['depth'] = wc_info_node.find('depth').text

        commit_node = entry_node.find('commit')
        commit = {}
        ret['commit'] = commit
        commit['#revision'] = int(commit_node.attrib['revision'])

        commit_author_node = commit_node.find('author')  # author can be None if the repository has revision 0
        if commit_author_node != None:
            commit['author'] = commit_author_node.text
        commit['date'] = commit_node.find('date').text

        lock_node = entry_node.find('lock')
        if lock_node is not None:
            lock = {}
            ret['lock'] = lock
            lock['token'] = lock_node.find('token').text
            lock['owner'] = lock_node.find('owner').text
            lock_comment_node = lock_node.find('comment')
            lock['comment'] = '' if lock_comment_node is None else lock_comment_node.text
            lock['created'] = lock_node.find('created').text

        return ret

    def log(self, path='.', revision_or_range=('HEAD', 1), limit=None, show_detail_changes=False, search_pattern=None):
        """
        :param path: working copy path or remote url
        :param revision_or_range: single revision number or revision range tuple/list
            - if range specified, format as (5, 10) or (10, 50) are both supported
                - for (5, 10): return list ordered by 5 -> 10
                - for (10, 5): return list ordered by 10 -> 5
                - the bound revision 5 or 10 also included
        :param limit: when the revision is a range, limit the record count
        :param show_detail_changes:
        :param search_pattern:
            - search in the limited records(by param limit)
            - matches any of the author, date, log message text, if show_detail_changes is True also a changed path
            - The search pattern use "glob syntax" wildcards
              ?      matches any single character
              *      matches a sequence of arbitrary characters
              [abc]  matches any of the characters listed inside the brackets
        example:
            revision=(5, 10) limit=2 output: 5, 6
            revision=(10, 5) limit=2 output: 10, 9
        """
        cmd = 'log ' + path
        cmd += ' --xml'
        cmd += ' ' + self.stringing_revision_or_range_option(revision_or_range)
        if limit is not None:
            cmd += ' -l %s' % limit
        if show_detail_changes:
            cmd += ' -v'
        if search_pattern is not None:
            cmd += ' --search %s' % search_pattern
        if self.is_url(path):
            cmd += ' ' + self.str_user_pass_option
        result = self.exec_sub_command_output(cmd)
        root = ElementTree.fromstring(result)

        ret = []
        for logentry_node in root.iterfind('logentry'):
            logentry = {}
            ret.append(logentry)
            logentry['#revision'] = logentry_node.attrib['revision']
            logentry['author'] = logentry_node.find('author').text
            logentry['date'] = logentry_node.find('date').text
            logentry['msg'] = logentry_node.find('msg').text
            paths_node = logentry_node.find('paths')
            if paths_node is not None:
                paths = []
                logentry['paths'] = paths
                for path_node in paths_node.iterfind('path'):
                    path = {}
                    paths.append(path)
                    path['#'] = path_node.text
                    path['#prop-mods'] = True if path_node.attrib['prop-mods']=='true' else False
                    path['#text-mods'] = True if path_node.attrib['text-mods']=='true' else False
                    path['#kind'] = path_node.attrib['kind']
                    path['#action'] = path_node.attrib['action']
        return ret

    def checkout(self, url, path='.', revision='HEAD'):
        cmd = 'checkout ' + url + ' ' + path
        cmd += ' ' + self.stringing_revision_option(revision)
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def update(self, path_list='.', revision='HEAD'):
        cmd = 'update ' + self.stringing_path_list(path_list)
        cmd += ' ' + self.stringing_revision_option(revision)
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def update_or_checkout(self, url, path='.', revision='HEAD'):
        if os.path.exists(path):
            self.update(path, revision)
        else:
            self.checkout(url, path, revision)

    def add(self, path_list):
        cmd = 'add ' + self.stringing_path_list(path_list)
        self.exec_sub_command(cmd)

    def commit(self, msg, path_list='.', include_external=False):
        """
        :except:
            SvnNoMessageError: if msg is empty
        """
        if not msg:
            raise SvnNoMessageError("commit on '%s'" % path_list)

        cmd = 'commit ' + self.stringing_path_list(path_list)
        if include_external:
            cmd += ' --include-externals'
        cmd += ' ' + self.stringing_message_option(msg)
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def resolve(self, path_list, accept_arg, recursive=True, quiet=True):
        """
        :param accept_arg: svn.RESOLVE_ACCEPT_XXX
        """
        cmd = 'resolve ' + self.stringing_path_list(path_list)
        if recursive:
            cmd += ' -R'
        if quiet:
            cmd += ' -q'
        cmd += ' --accept ' + accept_arg
        self.exec_sub_command(cmd)

    def clear_work_queue(self, path='.'):
        """Do this action maybe useful if cleanup failed"""
        conn = sqlite3.connect(os.path.join(path, '.svn', 'wc.db'))
        conn.execute('DELETE FROM work_queue')

    def cleanup(self, path_list='.'):
        cmd = 'cleanup ' + self.stringing_path_list(path_list)
        self.exec_sub_command(cmd)

    def revert(self, path_list='.', recursive=True):
        cmd = 'revert ' + self.stringing_path_list(path_list)
        if recursive is not None:
            cmd += ' -R'
        self.exec_sub_command(cmd)

    def clear_all(self, path='.'):
        self.clear_work_queue(path)
        self.cleanup(path)
        self.revert(path)

    def remove_not_versioned(self, path='.'):
        for line in self.exec_sub_command_output('status ' + path).splitlines():
            if len(line) > 0 and line[0] == '?':
                self.osx.remove_path(line[8:])

    def propset_externals(self, dir, external_pairs):
        """
        :param dir: the externals to set on
        :param external_pairs: [(sub_dir, external_dir),...]
        """
        temp_external_file_path = tempfile.mktemp()
        with open(temp_external_file_path, 'w') as fp:
            for pair in external_pairs:
                fp.write(pair[1] + ' ' + pair[0] + '\n')
        self.exec_sub_command('propset svn:externals -F %s %s' % (temp_external_file_path, dir) )
        os.remove(temp_external_file_path)

    def lock(self, file_path, msg):
        """
        :except:
            SvnNoMessageError: if msg is empty
            SvnAlreadyLockedError: if lock failure
        """
        if not msg:
            raise SvnNoMessageError("lock on '%s'" % file_path)

        cmd = 'lock ' + file_path
        cmd += ' ' + self.stringing_message_option(msg)
        cmd += ' ' + self.str_user_pass_option
        lock_result = self.exec_sub_command_output(cmd)
        if lock_result[0:4] == 'svn:':
            if self.is_url(file_path):
                raise SvnAlreadyLockedError(file_path, 'None', 'None', 'None')
            else:
                lock_info = self.info_dict(file_path)['lock']
                raise SvnAlreadyLockedError(file_path, lock_info['owner'], lock_info['comment'], lock_info['created'])

    def unlock(self, file_path):
        cmd = 'unlock ' + file_path
        cmd += ' --force'
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def move(self, src, dst, msg):
        """
        :except:
            SvnNoMessageError: if msg is empty
        """
        if not msg:
            raise SvnNoMessageError("move '%s' -> '%s'" % (src, dst))

        cmd = 'move ' + src + ' ' + dst
        cmd += ' ' + self.stringing_message_option(msg)
        cmd += ' --force'
        cmd += ' --parents'
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def branch(self, src, dst, msg, revision='HEAD'):
        """
        :except:
            SvnNoMessageError: if msg is empty
        """
        if not msg:
            raise SvnNoMessageError("branch '%s' -> '%s'" % (src, dst))

        try:
            self.info_dict(dst)
            raise SvnBranchDestinationAlreadyExistError(dst)
        except OsxSystemExecError:
            pass

        cmd = 'copy ' + src + ' ' + dst
        cmd += ' ' + self.stringing_revision_option(revision)
        cmd += ' ' + self.stringing_message_option(msg)
        cmd += ' --parents'
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def rollback(self, revision_or_range, path='.'):
        """
        rollback path changes made by commits in revision_or_range
        """
        if isinstance(revision_or_range, tuple) or isinstance(revision_or_range, list):
            start_revision = self.get_revision_number(path, revision_or_range[0])
            end_revision = self.get_revision_number(path, revision_or_range[1])
            if start_revision < end_revision:
                start_revision, end_revision = end_revision, start_revision
            revision_or_range = (start_revision, end_revision-1) if isinstance(revision_or_range, tuple) else [start_revision, end_revision-1]
        else:
            revision_or_range = self.get_revision_number(path, revision_or_range)
            revision_or_range = '-%d' % revision_or_range

        cmd = 'merge '
        cmd += ' ' + self.stringing_revision_or_range_option(revision_or_range)
        cmd += ' ' + path
        cmd += ' ' + path
        self.exec_sub_command(cmd)

# default Svn object
svn = Svn()


class Git:
    """
    A git command wrapper.
    """
    def __init__(self):
        self.base_command = 'git'
        self.meta_data_base_dir = '.git'
        self.osx = Osx()

    def set_base_command(self, base_command):
        self.base_command = base_command

    def set_redirect_output_to_log(self, redirect_output_to_log=True):
        self.osx.set_redirect_output_to_log(redirect_output_to_log)

    def exec_sub_command(self, sub_command):
        self.osx.exec_command(self.base_command + ' ' + sub_command)

    def exec_sub_command_output(self, sub_command):
        return self.osx.exec_command_output(self.base_command + ' ' + sub_command)

    def get_current_branch(self, path='.'):
        """
        return a tuple(branch_name, revision)
        """
        head_file_path = os.path.join(path, self.meta_data_base_dir, 'HEAD')
        with open(head_file_path) as fp:
            try:
                line = fp.readline().rstrip('\n')
                refs_heads = line.split(': ')[1]
                branch_name = refs_heads[len('refs/heads/'):]
            except Exception as e:
                raise GitParseMetaDataError("Can't parse branch name from head file %s: %s" % (head_file_path, str(e)))

        refs_heads_path = os.path.normpath(os.path.join(path, self.meta_data_base_dir, refs_heads))
        with open(refs_heads_path) as fp2:
            try:
                revision = fp2.readline().rstrip('\n')
            except Exception as e:
                raise GitParseMetaDataError("Can't parse revision from %s: %s" % (refs_heads_path, str(e)))

        return (branch_name, revision)

    def clone(self, url, path):
        cmd = 'clone ' + url + ' ' + path
        self.exec_sub_command(cmd)

    def get_clean(self, url, path, branch_name='master', revision=None):
        if not os.path.exists(path):
            self.clone(url, path)

        with self.osx.ChangeDirectory(path):
            self.exec_sub_command('reset --hard')  # revert local changes
            self.exec_sub_command('fetch')
            self.exec_sub_command('checkout ' + branch_name)
            self.exec_sub_command('merge origin/' + branch_name)  # set current branch to newest
            if revision is not None:
                self.exec_sub_command('reset %s --hard' % revision)

# default Git object
git = Git()


class Zip:
    """
    A zip helper.
    """
    def __init__(self):
        pass

    def _zip_file(self, file_path, zip_file_path):
        zf = zipfile.ZipFile(zip_file_path, "w", zipfile.zlib.DEFLATED)
        archive_name = os.path.basename(file_path)
        zf.write(file_path, archive_name)
        zf.close()

    def _zip_dir(self, dir_path, zip_file_path):
        file_list = []
        for root, dirs, files in os.walk(dir_path):
            for name in dirs:
                file_list.append(os.path.join(root, name))
            for name in files:
                file_list.append(os.path.join(root, name))

        zf_obj = zipfile.ZipFile(zip_file_path, "w", zipfile.zlib.DEFLATED)
        for file in file_list:
            archive_name = file[len(dir_path):]
            zf_obj.write(file, archive_name)
        zf_obj.close()

    def zip(self, source_path, zip_file_path):
        """
        make .zip for directory or single file
        """
        if os.path.isfile(source_path):
            self._zip_file(source_path, zip_file_path)
        else:
            self._zip_dir(source_path, zip_file_path)

    def unzip(self, zip_file_path, unzip_to_dir):
        """
        unzip .zip into directory
        """
        if not os.path.exists(unzip_to_dir):
            os.makedirs(unzip_to_dir)
        zf_obj = zipfile.ZipFile(zip_file_path)
        for name in zf_obj.namelist():
            name = name.replace('\\', '/')
            if name.endswith('/'):
                ext_dir = os.path.join(unzip_to_dir, name)
                if not os.path.exists(ext_dir):
                    os.makedirs(ext_dir)
            else:
                ext_filename = os.path.join(unzip_to_dir, name)
                ext_dir= os.path.dirname(ext_filename)
                if not os.path.exists(ext_dir):
                    os.makedirs(ext_dir)
                outfile = open(ext_filename, 'wb')
                outfile.write(zf_obj.read(name))
                outfile.close()


# default Zip object
zip = Zip()
