## doc generator for python modules

## v 0.1
## Author: Michael Kistler
"""
Used to generate the code documentation using sphinx
Make sure the gh-pages branch is already created for the project
"""

import os
import sys
from pathlib import Path
import sphinx
import subprocess

## Settings
project = 'SICAS-vsdConnect'
docs = 'docs'
module = 'vsdConnect'
version = '0.8.1'
author = 'Michael Kistler'
release = '0.8.1'
htmltheme = 'sphinx_rtd_theme'  #sphinx_rtd_theme, alabaster, classic
wp = Path('C:' + os.sep, 'Users', 'Michael Kistler', 'workspace')

## directories
docpath = Path(wp,docs)
codepath = Path(wp, project)
sourcepath = Path(codepath,docs) #./
buildpath = Path(docpath,project,'.')
modulepath = Path(codepath,module)
fpjekyll = Path(buildpath, '.nojekyll')

if not fpjekyll.is_file():
    fpjekyll.touch()

if not sourcepath.is_dir():
    sourcepath.mkdir()

if not docpath.is_dir():
    print("doc directory does not exist, exit")
    sys.exit()

if not codepath.is_dir():
    print("code directory does not exist, exit")
    sys.exit()

if not buildpath.is_dir():
    print("build directory does not exist, exit")
    sys.exit()

if not modulepath.is_dir():
    print("module directory does not exist, exit")
    sys.exit()



# run this if module have change names etc
# -e -> build separete rst files for submodules
args = 'sphinx-apidoc -F -e -f -o "{0}" "{1}" -V "{2}" -R "{3}" -A "{4}" -H VSDConnect'.format(sourcepath, modulepath, version, release, author)
#args = 'sphinx-apidoc -e -f -o "{0}" "{1}" -V "{2}"'.format(sourcepath, modulepath, version)

#p = subprocess.check_call(args , shell=True) # Success! (args,shell= True,stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE) # Success!

args = 'sphinx-build -b html "{0}" "{1}" -D html_theme={2}'.format(sourcepath, buildpath, htmltheme)
pbuild = subprocess.check_call(args , shell=True)


