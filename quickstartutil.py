# -*- coding: utf8 -*-
import os
import sys
import locale
import logging
import subprocess
import tempfile
import sqlite3
try:
    import xml.etree.cElementTree as ElementTree
except ImportError:
    import xml.etree.ElementTree as ElementTree


__version__ = '0.1.9'


__all__ = ['Error',
           'OsxSystemExecError', 'OsxPathError', 'OsxPathNotExistError', 'OsxPathAlreadyExistError', 'OsxPathTypeUnsupportedError',
           'SvnError', 'SvnNoMessageError', 'SvnAlreadyLockedError', 'SvnBranchDestinationAlreadyExist',
           'set_logger', 'set_local_encoding',
           'Osx', 'osx',
           'Svn', 'svn']


if sys.version_info[0] == 3:
    _PY3 = True
else:
    _PY3 = False


_logger = logging.getLogger('quickstartutil')
def set_logger(logger):
    global _logger
    _logger = logger


_local_encoding = locale.getdefaultlocale()[1]
def set_local_encoding(local_encoding):
    global _local_encoding
    _local_encoding = local_encoding


def _to_local_str(cmd):
    if _PY3:
        return cmd
    else:
        return cmd.decode('utf8').encode(_local_encoding)


def _fix_cmd_retcode(retcode):
    return retcode if os.name == 'nt' else (retcode >> 8)


class Error(Exception):
    pass


class OsxSystemExecError(Error):
    def __init__(self, cmd, code, output, msg):
        Error.__init__(self, msg)
        self.cmd = cmd
        self.code = code
        self.output = output


class OsxPathError(Error):
    def __init__(self, path):
        Error.__init__(self)
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
    def __init__(self, msg):
        Error.__init__(self, msg)


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


class SvnBranchDestinationAlreadyExist(SvnError):
    def __init__(self, dst):
        SvnError.__init__(self, "svn: branch destination '%s' already exist" % dst)
        self.dst = dst


class _BaseOsx:
    class ChangeDirectory:
        def __init__(self, target):
            self.old_cwd = os.getcwd()
            self.target = target

        def __enter__(self):
            _logger.info('>>> cd %s', self.target)
            os.chdir(_to_local_str(self.target))
            return self

        def __exit__(self, exc_type, exc_value, exc_tb):
            _logger.info('>>> cd %s', self.old_cwd)
            os.chdir(self.old_cwd)

    @classmethod
    def _system_exec_1(cls, cmd, shell=False):
        """
        Execute command and wait complete.
        The normal output & error will output to console.
        It's recommended for long time operation.
        :except: raise SystemCallError on failure
        """
        _logger.info('>>> %s' % cmd)
        try:
            subprocess.check_call(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
        except subprocess.CalledProcessError as e:
            final_code = _fix_cmd_retcode(e.returncode)
            raise OsxSystemExecError(cmd, final_code, None, "subprocess.check_call failed(%d): %s" % (final_code, e))

    @classmethod
    def _system_exec_2(cls, cmd, shell=False):
        _logger.info('>>> %s' % cmd)
        try:
            output = subprocess.check_output(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
            _logger.info(output)
        except subprocess.CalledProcessError as e:
            _logger.error(e.output)
            final_code = _fix_cmd_retcode(e.returncode)
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
            _system_exec_2(cmd, shell)
        else:
            _system_exec_1(cmd, shell)

    @classmethod
    def system_output(cls, cmd, shell=False):
        """
        Execute command and return it's output
        raise OsxSystemExecError on failure
        """
        try:
            return subprocess.check_output(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
        except subprocess.CalledProcessError as e:
            final_code = e.returncode if os.name == 'nt' else (e.returncode >> 8)
            raise OsxSystemExecError(cmd, final_code, e.output, "subprocess.check_output failed(%d): %s" % (final_code, e))

    @classmethod
    def is_path_exist(cls, path):
        return os.path.exists(_to_local_str(path))

    @classmethod
    def is_directory(cls, path):
        return os.path.isdir(_to_local_str(path))

    @classmethod
    def is_file(cls, path):
        return os.path.isfile(_to_local_str(path))

    def __init__(self, redirect_output_to_log=False):
        self.redirect_output_to_log = redirect_output_to_log

    def exec_command(self, cmd, shell=False):
        self.system_exec(cmd, shell=shell, redirect_output_to_log=self.redirect_output_to_log)


class _Osx_Win32(_BaseOsx):
    def __init__(self, redirect_output_to_log=False):
        _BaseOsx.__init__(self, redirect_output_to_log)

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

        if self.is_directory(path):
            self.exec_command('rd /s/q %s' % path, shell=True)
        elif self.is_file(path):
            self.exec_command('del /f/q %s' % path, shell=True)
        else:
            raise OsxPathTypeUnsupportedError(path, "'%s' is not a valid file or directory path" % path)

    def copy_directory(self, src_dir, dst_dir, excludes=None):
        """
        Copy all the files from source directory to destination directory.
        If target directory does not exist, then create one.
        :param src_dir: the source directory
        :param dst_dir: the destination directory
        :param excludes: if not None, files with the given pattern list in excludes will not be copied
        """
        if excludes is None:
            self.exec_command('xcopy %s\\* %s /r/i/c/k/h/e/q/y' % (src_dir, dst_dir))
        else:
            excludes_file_path = tempfile.mktemp()
            with open(excludes_file_path, 'w') as fp:
                fp.writelines(excludes)
            self.exec_command('xcopy %s\\* %s /r/i/c/k/h/e/q/y/exclude:%s' % (src_dir, dst_dir, excludes_file_path))
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
        self.exec_command('mkdir %s' % path)


if os.name == 'nt':
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
        return s

    @classmethod
    def stringing_revision_option(cls, revision):
        if revision is None:
            return '-r HEAD'
        if isinstance(revision, int):
            return '-r %d' % revision
        return '-r %s' % revision

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
        for prefix in ('file:\\\\\\' 'svn://', 'http://', 'https://'):
            if url.startswith(prefix):
                return True

    def __init__(self, user_pass=None, redirect_output_to_log=False):
        self.str_user_pass_option = self.stringing_user_pass_option(user_pass)
        self.base_command = 'svn --non-interactive --no-auth-cache'
        self.redirect_output_to_log = redirect_output_to_log
        self.osx = Osx(redirect_output_to_log)

    def exec_sub_command(self, sub_command):
        self.osx.system_exec(self.base_command + ' ' + sub_command, redirect_output_to_log=self.redirect_output_to_log)

    def exec_sub_command_output(self, sub_command):
        return self.osx.system_output(self.base_command + ' ' + sub_command)

    def info_dict(self, path='.'):
        ret = {}
        result = self.exec_sub_command_output('info --xml ' + path)
        root = ElementTree.fromstring(result)
        entry_node = root.find('entry')

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

    def checkout(self, url, path='.', revision=None):
        cmd = 'checkout ' + url + ' ' + path
        cmd += ' ' + self.stringing_revision_option(revision)
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def update(self, path_list='.', revision=None):
        cmd = 'update ' + self.stringing_path_list(path_list)
        cmd += ' ' + self.stringing_revision_option(revision)
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)

    def update_or_checkout(self, url, path='.', revision=None):
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

    def branch(self, src, dst, msg, revision=None):
        """
        :except:
            SvnNoMessageError: if msg is empty
        """
        if not msg:
            raise SvnNoMessageError("branch '%s' -> '%s'" % (src, dst))

        try:
            self.info_dict(dst)
            raise SvnBranchDestinationAlreadyExist(dst)
        except OsxSystemExecError:
            pass

        cmd = 'copy ' + src + ' ' + dst
        cmd += ' ' + self.stringing_revision_option(revision)
        cmd += ' ' + self.stringing_message_option(msg)
        cmd += ' --parents'
        cmd += ' ' + self.str_user_pass_option
        self.exec_sub_command(cmd)


# default Svn object
svn = Svn()
