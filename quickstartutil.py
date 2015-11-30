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


__version__ = '0.1.6'


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


class SystemExecError(Error):
    def __init__(self, cmd, code, output, msg):
        Error.__init__(self, msg)
        self.cmd = cmd
        self.code = code
        self.output = output


class PathError(Error):
    def __init__(self, path, msg):
        Error.__init__(self, path, msg)
        self.path = path


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


def _system_exec_1(cmd, shell=False):
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
        raise SystemExecError(cmd, final_code, None, "subprocess.check_call failed(%d): %s" % (final_code, e))


def _system_exec_2(cmd, shell=False):
    _logger.info('>>> %s' % cmd)
    try:
        output = subprocess.check_output(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
        _logger.info(output)
    except subprocess.CalledProcessError as e:
        _logger.error(e.output)
        final_code = _fix_cmd_retcode(e.returncode)
        raise SystemExecError(cmd, final_code, e.output, "subprocess.check_output failed(%d): %s" % (final_code, e))


def system_exec(cmd, shell=False, redirect_output_to_log=False):
    """
    Execute command and wait complete.
    :param: redirect_output_to_log:
      True: OUTPUT & ERROR will redirect to the logger
      False: OUTPUT & ERROR will output to console. It's recommended for long-time operation
    :except: raise SystemExecError on failure
    """
    if redirect_output_to_log:
        _system_exec_2(cmd, shell)
    else:
        _system_exec_1(cmd, shell)


def system_output(cmd, shell=False):
    """
    Execute command and return it's output
    raise SystemExecError on failure
    """
    try:
        return subprocess.check_output(_to_local_str(cmd), stderr=subprocess.STDOUT, shell=shell)
    except subprocess.CalledProcessError as e:
        final_code = e.returncode if os.name == 'nt' else (e.returncode >> 8)
        raise SystemExecError(cmd, final_code, e.output, "subprocess.check_output failed(%d): %s" % (final_code, e))


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


class _OS_Win32:
    @classmethod
    def remove_path_if_exist(cls, path):
        if not os.path.exists(_to_local_str(path)):
            return
        if os.path.isdir(_to_local_str(path)):
            system_exec('rd /s/q %s' % path)
        elif os.path.isfile(_to_local_str(path)):
            system_exec('del /f/q %s' % path)
        else:
            raise PathError(path, "'%s' is not a valid file or directory path" % path)

    @classmethod
    def copy_directory(cls, src_dir, dst_dir, excludes=None):
        if excludes is None:
            system_exec('xcopy %s\\* %s /r/i/c/k/h/e/q/y' % (src_dir, dst_dir))
        else:
            excludes_file_path = tempfile.mktemp()
            with open(excludes_file_path, 'w') as fp:
                fp.writelines(excludes)
            system_exec('xcopy %s\\* %s /r/i/c/k/h/e/q/y/exclude:%s' % (src_dir, dst_dir, excludes_file_path))
            os.remove(excludes_file_path)

    @classmethod
    def make_dir(cls, path):
        system_exec('mkdir %s' % path)


if os.name == 'nt':
    _os_cls = _OS_Win32
else:
    raise NotImplementedError('Unsupported os.')


def remove_path_if_exist(path):
    """Remove the file or directory if exist."""
    _os_cls.remove_path_if_exist(path)


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
    if os.path.exists(_to_local_str(path)):
        return
    _os_cls.make_dir(path)


class svn:
    """
    A svn command wrapper.

    Global param:
        user_pass: None or a tuple with username & password
        revision: can be integer or string
    """

    RESOLVE_ACCEPT_BASE = 'base'
    RESOLVE_ACCEPT_WORKING = 'working'
    RESOLVE_ACCEPT_MINE_CONFLICT = 'mine-conflict'
    RESOLVE_ACCEPT_THEIRS_CONFLICT = 'theirs-conflict'
    RESOLVE_ACCEPT_MINE_FULL = 'mine-full'
    RESOLVE_ACCEPT_THEIRS_FULL = 'theirs-full'

    @classmethod
    def _base_command(cls):
        return 'svn --non-interactive --no-auth-cache'

    @classmethod
    def exec_sub_command(cls, sub_command):
        system_exec(cls._base_command() + ' ' + sub_command)

    @classmethod
    def exec_sub_command_output(cls, sub_command):
        return system_output(cls._base_command() + ' ' + sub_command)

    @classmethod
    def str_user_pass_option(cls, user_pass):
        s = ''
        if user_pass is not None:
            s += '--username ' + user_pass[0]
            s += ' --password ' + user_pass[1]
        return s

    @classmethod
    def str_revision(cls, revision):
        if revision is None:
            return 'HEAD'
        if isinstance(revision, int):
            return '%d' % revision
        return revision

    @classmethod
    def info_dict(cls, path='.'):
        ret = {}
        result = cls.exec_sub_command_output('info --xml ' + path)
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

    @classmethod
    def checkout(cls, url, path='.', revision=None, user_pass=None):
        cls.exec_sub_command('checkout -r %s %s %s %s' % (cls.str_revision(revision), url, path, cls.str_user_pass_option(user_pass)) )

    @classmethod
    def update(cls, path='.', revision=None):
        cls.exec_sub_command('update -r %s %s' % (cls.str_revision(revision), path) )

    @classmethod
    def update_or_checkout(cls, url, path='.', revision=None, user_pass=None):
        if os.path.exists(path):
            cls.update(path, revision)
        else:
            cls.checkout(url, path, revision, user_pass)

    @classmethod
    def add(cls, path_list):
        cls.exec_sub_command('add ' + ' '.join(path_list))

    @classmethod
    def commit(cls, msg, path='.', include_external=False, user_pass=None):
        """
        :except:
            SvnNoMessageError: if msg is empty
        """
        if not msg:
            raise SvnNoMessageError("commit on '%s'" % path)

        cmd = 'commit ' + path
        if include_external:
            cmd += ' --include-externals'
        cmd += ' -m "%s"' % msg
        cmd += ' ' + cls.str_user_pass_option(user_pass)
        cls.exec_sub_command(cmd)

    @classmethod
    def resolve(cls, path_list, accept_arg, recursive=True, quiet=True):
        """
        :param accept_arg: svn.RESOLVE_ACCEPT_XXX
        """
        cmd = 'resolve ' + ' '.join(path_list)
        if recursive:
            cmd += ' -R'
        if quiet:
            cmd += ' -q'
        cmd += ' --accept ' + accept_arg
        cls.exec_sub_command(cmd)

    @classmethod
    def clear_work_queue(cls, path='.'):
        """Do this action maybe useful if cleanup failed"""
        conn = sqlite3.connect(os.path.join(path, '.svn', 'wc.db'))
        conn.execute('DELETE FROM work_queue')

    @classmethod
    def cleanup(cls, path='.'):
        cls.exec_sub_command('cleanup ' + path)

    @classmethod
    def revert(cls, path='.', recursive=True):
        cmd = 'revert '
        if recursive is not None:
            cmd += '-R '
        cmd += path
        cls.exec_sub_command(cmd)

    @classmethod
    def clear_all(cls, path='.'):
        cls.clear_work_queue(path)
        cls.cleanup(path)
        cls.revert(path)

    @classmethod
    def remove_not_versioned(cls, path='.'):
        for line in cls.exec_sub_command_output('status ' + path).splitlines():
            if len(line) > 0 and line[0] == '?':
                remove_path_if_exist(line[8:])

    @classmethod
    def propset_externals(cls, dir, external_pairs):
        """
        :param dir: the externals to set on
        :param external_pairs: [(sub_dir, external_dir),...]
        """
        temp_external_file_path = tempfile.mktemp()
        with open(temp_external_file_path, 'w') as fp:
            for pair in external_pairs:
                fp.write(pair[1] + ' ' + pair[0] + '\n')
        cls.exec_sub_command('propset svn:externals -F %s %s' % (temp_external_file_path, dir) )
        remove_path_if_exist(temp_external_file_path)

    @classmethod
    def lock(cls, msg, path='.', user_pass=None):
        """
        :except:
            SvnNoMessageError: if msg is empty
            SvnAlreadyLockedError: if lock failure
        """
        if not msg:
            raise SvnNoMessageError("lock on '%s'" % path)
        lock_result = cls.exec_sub_command_output('lock ' + path + ' ' + cls.str_user_pass_option(user_pass))
        if lock_result[0:4] == "svn:":
            lock_info = cls.info_dict(path)['lock']
            raise SvnAlreadyLockedError(path, lock_info['owner'], lock_info['comment'], lock_info['created'])

    @classmethod
    def unlock(cls, path='.', user_pass=None):
        cls.exec_sub_command('unlock ' + path + ' --force ' + cls.str_user_pass_option(user_pass))

    @classmethod
    def move(cls, msg, src, dst, user_pass=None):
        """
        :except:
            SvnNoMessageError: if msg is empty
        """
        if not msg:
            raise SvnNoMessageError("move '%s' -> '%s'" % (src, dst))

        cmd = 'move ' + src + ' ' + dst
        cmd += ' -m "%s"' % msg
        cmd += ' --force'
        cmd += ' --parents'
        cmd += ' ' + cls.str_user_pass_option(user_pass)

        cls.exec_sub_command(cmd)

    @classmethod
    def branch(cls, msg, src, dst, revision=None, user_pass=None):
        """
        :except:
            SvnNoMessageError: if msg is empty
        """
        str_revision = cls.str_revision(revision)
        if not msg:
            raise SvnNoMessageError("branch '%s'@%s -> '%s'" % (src, str_revision, dst))

        try:
            svn.info_dict(dst)
            raise SvnBranchDestinationAlreadyExist(dst)
        except SystemExecError:
            pass

        cmd = 'copy ' + src + ' ' + dst
        cmd += ' -r %s' % str_revision
        cmd += ' -m "%s"' % msg
        cmd += ' --parents'
        cmd += ' ' + cls.str_user_pass_option(user_pass)

        cls.exec_sub_command(cmd)


#url = 'svn://127.0.0.1'
#svn.branch('lalala', url+'/jinji2', url+'/jinji6', revision=4)
#svn.move('auto move ', url+'/jinji2', url+'/jinjimove2')
