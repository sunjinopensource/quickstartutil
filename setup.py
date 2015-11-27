import os
from setuptools import setup


f = open(os.path.join(os.path.dirname(__file__), 'README.rst'))
readme = f.read()
f.close()


setup(
	name='quickstartutil',
	version=__import__('quickstartutil').__version__,
    description='A simple utility for building application quickly',
    long_description=readme,
    author='Sun Jin',
    author_email='sunjinopensource@qq.com',
    url='https://github.com/sunjinopensource/quickstartutil/',
	py_modules=['quickstartutil'],
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Programming Language :: Python :: 3',
    ],
)
