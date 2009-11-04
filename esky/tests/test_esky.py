
import sys
import os
from os.path import dirname
import subprocess
import shutil
import zipfile
import threading
import tempfile
import time
from SimpleHTTPServer import SimpleHTTPRequestHandler
from BaseHTTPServer import HTTPServer

from distutils.core import setup as dist_setup
from distutils.util import get_platform

import esky
from esky import bdist_esky


def test_esky():
    """Build and launch a simple self-testing esky application."""
    olddir = os.path.abspath(os.curdir)
    try:
        platform = get_platform()
        deploydir = "deploy.%s" % (platform,)
        esky_root = dirname(dirname(dirname(__file__)))
        os.chdir(os.path.join(esky_root,"esky","tests"))
        if os.path.isdir(deploydir):
            shutil.rmtree(deploydir)
        #  Build three increasing versions of the test package
        metadata = dict(name="eskytester",packages=["eskytester"],author="rfk",
                        description="the esky test package",script_args=["bdist_esky"])
        dist_setup(version="0.1",scripts=["eskytester/script1.py"],**metadata)
        dist_setup(version="0.2",scripts=["eskytester/script1.py","eskytester/script2.py"],**metadata)
        dist_setup(version="0.3",scripts=["eskytester/script2.py","eskytester/script3.py"],**metadata)
        #  Serve the updates at http://localhost:8000/dist/
        server = HTTPServer(("localhost",8000),SimpleHTTPRequestHandler)
        threading.Thread(target=server.serve_forever).start()
        #  Set up the deployed esky environment for the initial version
        zfname = os.path.join("dist","eskytester-0.1.%s.zip"%(platform,))
        zf = zipfile.ZipFile(zfname,"r")
        os.mkdir(deploydir)
        for nm in zf.namelist():
            outfilenm = os.path.join(deploydir,nm)
            if not os.path.isdir(os.path.dirname(outfilenm)):
                os.makedirs(os.path.dirname(outfilenm))
            infile = zf.open(nm,"r")
            outfile = open(outfilenm,"wb")
            try:
                shutil.copyfileobj(infile,outfile)
            finally:
                infile.close()
                outfile.close()
            mode = zf.getinfo(nm).external_attr >> 16L
            os.chmod(outfilenm,mode)
        #  Run the first script, which will perform the necessary tests
        #  and write "tests-completed" file when done.
        if os.path.exists("tests-completed"):
            os.unlink("tests-completed")
        if sys.platform == "win32":
            cmd = os.path.join(deploydir,"script1.exe")
        else:
            cmd = os.path.join(deploydir,"script1")
        p = subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
        (stdout,_) = p.communicate()
        sys.stdout.write(stdout)
        assert p.returncode == 0
        assert os.path.exists("tests-completed")
        os.unlink("tests-completed")
    finally:
        os.chdir(olddir)

 
def test_esky_locking():
    appdir = tempfile.mkdtemp()
    try: 
        os.mkdir(os.path.join(appdir,"testapp-0.1"))
        open(os.path.join(appdir,"testapp-0.1","library.zip"),"wb").close()
        e1 = esky.Esky(appdir,"http://example.com/downloads/")
        assert e1.name == "testapp"
        assert e1.version == "0.1"
        e2 = esky.Esky(appdir,"http://example.com/downloads/")
        assert e2.name == "testapp"
        assert e2.version == "0.1"
        locked = []; errors = [];
        trigger1 = threading.Event(); trigger2 = threading.Event()
        def runit(e,t1,t2):
            def runme():
                try:
                    e.lock()
                except Exception, err:
                    errors.append(err)
                else:
                    locked.append(e)
                t1.set()
                t2.wait()
            return runme
        t1 = threading.Thread(target=runit(e1,trigger1,trigger2))
        t2 = threading.Thread(target=runit(e2,trigger2,trigger1))
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(locked) == 1
        assert (e1 in locked or e2 in locked)
        assert len(errors) == 1
        assert isinstance(errors[0],esky.EskyLockedError)
    finally:
        shutil.rmtree(appdir)

 
def test_esky_lock_breaking():
    appdir = tempfile.mkdtemp()
    try: 
        os.mkdir(os.path.join(appdir,"testapp-0.1"))
        open(os.path.join(appdir,"testapp-0.1","library.zip"),"wb").close()
        e1 = esky.Esky(appdir,"http://example.com/downloads/")
        e2 = esky.Esky(appdir,"http://example.com/downloads/")
        trigger1 = threading.Event(); trigger2 = threading.Event()
        errors = []
        def run1():
            try:
                e1.lock()
            except Exception, err:
                errors.append(err)
            trigger1.set()
            trigger2.wait()
        def run2():
            trigger1.wait()
            try:
                e2.lock()
            except esky.EskyLockedError:
                pass
            except Exception, err:
                errors.append(err)
            else:
                errors.append("locked when I shouldn't have")
            e2.lock_timeout = 0.1
            time.sleep(0.5)
            try:
                e2.lock()
            except Exception, err:
                errors.append(err)
            trigger2.set()
        t1 = threading.Thread(target=run1)
        t2 = threading.Thread(target=run2)
        t1.start()
        t2.start()
        t1.join()
        t2.join()
        assert len(errors) == 0, str(errors)
    finally:
        shutil.rmtree(appdir)


def test_README():
    """Ensure that the README is in sync with the docstring.

    This test should always pass - it takes corrective action if the
    README has gotten out of sync.
    """
    dirname = os.path.dirname
    readme = os.path.join(dirname(dirname(dirname(__file__))),"README.txt")
    if not os.path.isfile(readme):
        f = open(readme,"wb")
        f.write(esky.__doc__)
        f.close()
    else:
        f = open(readme,"rb")
        if f.read() != esky.__doc__:
            f.close()
            f = open(readme,"wb")
            f.write(esky.__doc__)
            f.close()
