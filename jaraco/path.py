# -*- coding: UTF-8 -*-

"""
Tools for working with files and file systems
"""

from __future__ import division, unicode_literals, absolute_import

import os
import re
import itertools
import functools
import calendar
import contextlib
import logging
import datetime
import glob
import tempfile

log = logging.getLogger(__name__)

def get_unique_pathname(path, root = ''):
	"""Return a pathname possibly with a number appended to it so that it is
	unique in the directory."""
	path = os.path.join(root, path)
	# consider the path supplied, then the paths with numbers appended
	potentialPaths = itertools.chain((path,), __get_numbered_paths(path))
	potentialPaths = itertools.ifilterfalse(os.path.exists, potentialPaths)
	return potentialPaths.next()

def __get_numbered_paths(filepath):
	"""Append numbers in sequential order to the filename or folder name
	Numbers should be appended before the extension on a filename."""
	format = '%s (%%d)%s' % splitext_files_only(filepath)
	return itertools.imap(lambda n: format % n, itertools.count(1))

def splitext_files_only(filepath):
	"Custom version of splitext that doesn't perform splitext on directories"
	return (filepath, '') if os.path.isdir(filepath) else os.path.splitext()

def set_time(filename, mod_time):
	"""
	Set the modified time of a file
	"""
	log.debug('Setting modified time to %s', mod_time)
	mtime = calendar.timegm(mod_time.utctimetuple())
	# utctimetuple discards microseconds, so restore it (for consistency)
	mtime += mod_time.microsecond / 1000000
	atime = os.stat(filename).st_atime
	os.utime(filename, (atime, mtime))

def get_time(filename):
	"""
	Get the modified time for a file as a datetime instance
	"""
	ts = os.stat(filename).st_mtime
	return datetime.datetime.utcfromtimestamp(ts)

def insert_before_extension(filename, content):
	"""
	Given a filename and some content, insert the content just before
	the extension.

	>>> insert_before_extension('pages.pdf', '-old')
	'pages-old.pdf'
	"""
	parts = list(os.path.splitext(filename))
	parts[1:1] = [content]
	return ''.join(parts)

class DirectoryStack(list):
	r"""
	...

	DirectoryStack includes a context manager function that can be used
	to easily perform an operation in a separate directory.

	>>> orig_dir = os.getcwd()
	>>> stack = DirectoryStack()
	>>> with stack.context('/'): context_dir = os.getcwd()
	>>> orig_dir == os.getcwd()
	True
	>>> orig_dir == context_dir
	False
	>>> len(stack)
	0
	>>> stack.pushd('/')
	>>> len(stack)
	1
	>>> os.getcwd() == os.path.abspath('/')
	True
	>>> last_dir = stack.popd()
	>>> last_dir == context_dir
	True
	>>> os.getcwd() == orig_dir
	True
	"""
	def pushd(self, new_dir):
		self.append(os.getcwd())
		os.chdir(new_dir)

	def popd(self):
		res = os.getcwd()
		os.chdir(self.pop())
		return res

	@contextlib.contextmanager
	def context(self, new_dir):
		self.pushd(new_dir)
		try:
			yield
		finally:
			self.popd()

def recursive_glob(root, spec):
	"""
	Like iglob, but recurse directories

	>>> any('path.py' in result for result in recursive_glob('.', '*.py'))
	True

	>>> all(result.startswith('.') for result in recursive_glob('.', '*.py'))
	True

	>>> len(list(recursive_glob('.', '*.foo')))
	0

	"""
	specs = (
		os.path.join(dirpath, dirname, spec)
		for dirpath, dirnames, filenames in os.walk(root)
		for dirname in dirnames
	)

	return itertools.chain.from_iterable(
		glob.iglob(spec)
		for spec in specs
	)

def encode(name, system='NTFS'):
	"""
	Encode the name for a suitable name in the given filesystem
	>>> encode('Test :1')
	'Test _1'
	"""
	assert system == 'NTFS', 'unsupported filesystem'
	special_characters = r'<>:"/\|?*' + ''.join(map(chr, range(32)))
	pattern = '|'.join(map(re.escape, special_characters))
	pattern = re.compile(pattern)
	return pattern.sub('_', name)

class save_to_file():
	"""
	A context manager for saving some content to a file, and then
	cleaning up the file afterward.

	>>> with save_to_file(b'foo') as filename:
	...     assert 'foo' == open(filename).read()
	"""
	def __init__(self, content):
		self.content = content

	def __enter__(self):
		tf = tempfile.NamedTemporaryFile(delete=False)
		tf.write(self.content)
		tf.close()
		self.filename = tf.name
		return tf.name

	def __exit__(self, type, value, traceback):
		os.remove(self.filename)

@contextlib.contextmanager
def tempfile_context(*args, **kwargs):
	"""
	A wrapper around tempfile.mkstemp to create the file in a context and
	delete it after.
	"""
	fd, filename = tempfile.mkstemp(*args, **kwargs)
	os.close(fd)
	try:
		yield filename
	finally:
		os.remove(filename)

def replace_extension(new_ext, filename):
	"""
	>>> replace_extension('.pdf', 'myfile.doc')
	'myfile.pdf'
	"""
	return os.path.splitext(filename)[0] + new_ext

def ExtensionReplacer(new_ext):
	"""
	A reusable function to replace a file's extension with another

	>>> repl = ExtensionReplacer('.pdf')
	>>> repl('myfile.doc')
	'myfile.pdf'
	>>> repl('myfile.txt')
	'myfile.pdf'
	>>> repl('myfile')
	'myfile.pdf'
	"""
	return functools.partial(replace_extension, new_ext)

def ensure_dir_exists(func):
	"wrap a function that returns a dir, making sure it exists"
	@functools.wraps(func)
	def make_if_not_present():
		dir = func()
		if not os.path.isdir(dir):
			os.makedirs(dir)
		return dir
	return make_if_not_present

def read_chunks(file, chunk_size=2048, update_func=lambda x: None):
	"""
	Read file in chunks of size chunk_size (or smaller).
	If update_func is specified, call it on every chunk with the amount
	read.
	"""
	while(True):
		res = file.read(chunk_size)
		if not res: break
		update_func(len(res))
		yield res