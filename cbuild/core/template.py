# This file provides an interface for a parsed template that is sanitized
# (unlike a raw template, which is just plain python code).
#
# It also provides a reference to what is allowed and what is not.

from re import search
import fnmatch
import shutil
import glob
import sys
import os
import importlib
import pathlib
import contextlib
import subprocess
import shutil
import builtins

from cbuild.core import logger, chroot, paths
from cbuild import cpu

class PackageError(Exception):
    pass

@contextlib.contextmanager
def redir_allout(logpath):
    try:
        pr, pw = os.pipe()
        # save old descriptors
        oldout = os.dup(sys.stdout.fileno())
        olderr = os.dup(sys.stderr.fileno())
        # this will do the logging for us; this way we can get
        # both standard output and file redirection at once
        tee = subprocess.Popen(["tee", logpath], stdin = pr)
        # everything goes into the pipe
        os.dup2(pw, sys.stdout.fileno())
        os.dup2(pw, sys.stderr.fileno())
        # fire
        yield
    finally:
        # restore
        os.dup2(oldout, sys.stdout.fileno())
        os.dup2(olderr, sys.stderr.fileno())
        # close the pipe
        os.close(pw)
        os.close(pr)
        # wait for the tee to finish
        tee.wait()

# relocate "src" from root "root" to root "dest"
#
# e.g. _submove("foo/bar", "/a", "/b") will move "/b/foo/bar" to "/a/foo/bar"
#
def _submove(src, dest, root):
    dirs, fname = os.path.split(src)
    ddirs = os.path.join(dest, dirs)

    os.makedirs(ddirs, exist_ok = True)

    fsrc = os.path.join(root, src)
    fdest = os.path.join(dest, src)

    if not os.path.exists(fdest):
        shutil.move(fsrc, ddirs)
    else:
        if os.path.isdir(fdest) and os.path.isdir(fsrc):
            # merge the directories
            for fn in os.listdir(fsrc):
                _submove(fn, fdest, fsrc)
            # remove the source dir that should now be empty
            os.rmdir(os.path.join(dirp))
        else:
            raise FileExistsError(f"'{dirp}' and '{destp}' overlap")

hooks = {
    "pre_fetch": [],
    "do_fetch": [],
    "post_fetch": [],
    "pre_extract": [],
    "do_extract": [],
    "post_extract": [],
    "pre_patch": [],
    "do_patch": [],
    "post_patch": [],
    "pre_configure": [],
    "do_configure": [],
    "post_configure": [],
    "pre_build": [],
    "do_build": [],
    "post_build": [],
    "pre_install": [],
    "do_install": [],
    "post_install": [],
    "pre_pkg": [],
    "do_pkg": [],
    "post_pkg": []
}

def run_pkg_func(pkg, func, funcn = None, desc = None, on_subpkg = False):
    if not funcn:
        if not hasattr(pkg, func):
            return False
        funcn = func
        
        func = getattr(pkg, funcn)
    if not desc:
        desc = funcn
    if pkg.parent:
        logf = pkg.parent.statedir / f"{pkg.pkgname}__{funcn}.log"
    else:
        logf = pkg.statedir / f"{pkg.pkgname}__{funcn}.log"
    pkg.log(f"running {desc}...")
    with redir_allout(logf):
        if on_subpkg:
            func()
        else:
            func(pkg)
    return True

def call_pkg_hooks(pkg, stepn):
    for f in hooks[stepn]:
        run_pkg_func(pkg, f[0], f"{stepn}_{f[1]}", f"{stepn} hook: {f[1]}")

class Package:
    def __init__(self):
        self.logger = logger.get()
        self.pkgname = None
        self.pkgver = None

    def log(self, msg, end = "\n"):
        self.logger.out(self._get_pv() + ": " + msg, end)

    def log_red(self, msg, end = "\n"):
        self.logger.out_red(self._get_pv() + ": " + msg, end)

    def log_warn(self, msg, end = "\n"):
        self.logger.warn(self._get_pv() + ": " + msg, end)

    def error(self, msg, end = "\n"):
        self.log_red(msg)
        raise PackageError()

    def _get_pv(self):
        if self.pkgver:
            return self.pkgver
        elif self.pkgname:
            return self.pkgname
        return "cbuild"

class Template(Package):
    def __init__(self):
        super().__init__()

        # mandatory fields
        self.pkgname = None
        self.version = None
        self.revision = None
        self.short_desc = None
        self.homepage = None
        self.license = None
    
        # optional core fields
        self.archs = None
        self.hostmakedepends = []
        self.makedepends = []
        self.depends = []
        self.shlib_provides = None
        self.shlib_requires = None
        self.bootstrap = None
        self.maintainer = None
        self.wrksrc = None
        self.build_wrksrc = ""
        self.create_wrksrc = False
        self.patch_args = None
        self.configure_args = []
        self.make_build_args = []
        self.make_install_args = []
        self.make_build_target = ""
        self.make_install_target = "install"
        self.distfiles = None
        self.checksum = None
        self.skip_extraction = []
        self.subpackages = []
        self.triggers = []
        self.broken = None
        self.nopie = False
        self.noverifyrdeps = False
        self.noshlibprovides = False
        self.skiprdeps = []
        self.shlib_requires = []
        self.shlib_provides = []
        self.make_dirs = []
        self.repository = None
        self.preserve = False
        self.provides = []
        self.replaces = []
        self.conflicts = []
        self.reverts = []
        self.mutable_files = []
        self.conf_files = []
        self.alternatives = []
        self.tags = []
        self.changelog = None
        self.CFLAGS = []
        self.CXXFLAGS = []
        self.LDFLAGS = []
        self.tools = {}
        self.env = {}
    
        # injected
        self.build_style = None
        self.run_depends = None
    
        # other fields
        self.parent = None
        self.rparent = self
        self.subpkg_list = []
        self.source_date_epoch = None

    def ensure_fields(self):
        for f in [
            "pkgname", "version", "revision",
            "short_desc", "homepage", "license"
        ]:
            if not getattr(self, f):
                self.error("missing field: %s" % f)

    def validate_version(self):
        if not isinstance(self.version, str):
            self.error("malformed version field")
        if "-" in self.version:
            self.error("version contains invalid character: -")
        if "_" in self.version:
            self.error("version contains invalid character: _")
        if not search("\d", self.version):
            self.error("version must contain a digit")

    def validate_arch(self):
        if not self.archs:
            return
        if not isinstance(self.archs, str):
            self.error("malformed archs field")
        archs = self.archs.split()
        matched = False
        for arch in archs:
            negarch = False
            if arch[0] == "~":
                negarch = True
                arch = arch[1:]
            if fnmatch.fnmatchcase(cpu.target(), arch):
                if not negarch:
                    matched = True
                    break
            else:
                if negarch:
                    matched = True
                    break
        if not matched:
            self.error(f"this package cannot be built for {cpu.target()}")

    def do(self, cmd, args, env = {}, build = False):
        cenv = dict(env);
        cenv["CFLAGS"] = " ".join(self.CFLAGS)
        cenv["CXXFLAGS"] = " ".join(self.CXXFLAGS)
        cenv["LDFLAGS"] = " ".join(self.LDFLAGS)
        cenv["XBPS_TARGET_MACHINE"] = cpu.target()
        cenv["XBPS_MACHINE"] = cpu.host()
        cenv["XBPS_TRIPLET"] = self.triplet
        if self.source_date_epoch:
            cenv["SOURCE_DATE_EPOCH"] = str(self.source_date_epoch)

        cenv.update(self.tools)
        cenv.update(self.env)
        return chroot.enter("/usr/bin/cbuild-do", [
            str(self.chroot_build_wrksrc if build else self.chroot_wrksrc), cmd
        ] + args, env = cenv, check = True)

    def run_step(self, stepn, optional = False, skip_post = False):
        call_pkg_hooks(self, "pre_" + stepn)

        # run pre_* phase
        run_pkg_func(self, "pre_" + stepn)

        # run do_* phase
        if not run_pkg_func(self, "do_" + stepn) and not optional:
            self.error(f"cannot find do_{stepn}")

        call_pkg_hooks(self, "do_" + stepn)

        # run post_* phase
        run_pkg_func(self, "post_" + stepn)

        if not skip_post:
            call_pkg_hooks(self, "post_" + stepn)

    def install_files(self, path, dest, symlinks = True):
        if os.path.isabs(dest):
            self.logger.out_red(
                f"install_files: path '{dest}' must not be absolute"
            )
            raise PackageError()
        if os.path.isabs(path):
            self.logger.out_red(f"path '{path}' must not be absolute")
            raise PackageError()

        path = os.path.join(self.abs_wrksrc, path)
        dest = os.path.join(self.destdir, dest, os.path.basename(path))

        shutil.copytree(path, dest, symlinks = symlinks)

    def install_dir(self, *args):
        for dn in args:
            if os.path.isabs(dn):
                self.logger.out_red(f"path '{dn}' must not be absolute")
                raise PackageError()
            dirp = os.path.join(self.destdir, dn)
            self.log(f"creating path: {dirp}")
            os.makedirs(dirp, exist_ok = True)

    def install_bin(self, *args):
        self.install_dir("usr/bin")
        for bn in args:
            spath = os.path.join(self.abs_wrksrc, bn)
            dpath = os.path.join(self.destdir, "usr/bin")
            self.log(f"copying (755): {spath} -> {dpath}")
            shutil.copy2(spath, dpath)
            os.chmod(os.path.join(dpath, os.path.split(spath)[1]), 0o755)

    def install_man(self, *args):
        self.install_dir("usr/share/man")
        manbase = os.path.join(self.destdir, "usr/share/man")
        for mn in args:
            absmn = os.path.join(self.abs_wrksrc, mn)
            mnf = os.path.split(absmn)[1]
            mnext = os.path.splitext(mnf)[1]
            if len(mnext) == 0:
                self.logger.out_red(f"manpage '{mnf}' has no section")
                raise PackageError()
            try:
                mnsec = int(mnext[1:])
            except:
                self.logger.out_red(f"manpage '{mnf}' has an invalid section")
                raise PackageError()
            mandir = os.path.join(manbase, "man" + mnext)
            os.makedirs(mandir, exist_ok = True)
            self.log(f"copying (644): {absmn} -> {mandir}")
            shutil.copy2(absmn, mandir)
            os.chmod(os.path.join(mandir, mnf), 0o644)

    def install_link(self, src, dest):
        if os.path.isabs(dest):
            self.logger.out_red(f"path '{dest}' must not be absolute")
            raise PackageError()
        dest = os.path.join(self.destdir, dest)
        self.log(f"symlinking: {src} -> {dest}")
        os.symlink(src, dest)

    def unlink(self, f, root = None):
        if os.path.isabs(f):
            self.logger.out_red(f"path '{f}' must not be absolute")
            raise PackageError()
        remp = os.path.join(root if root else self.destdir, f)
        self.log(f"removing: {remp}")
        os.unlink(remp)

    def rmtree(self, path, root = None):
        if os.path.isabs(path):
            self.logger.out_red(f"path '{path}' must not be absolute")
            raise PackageError()

        path = os.path.join(root if root else self.destdir, path)
        if not os.path.isdir(path):
            self.logger.out_red(f"path '{path}' must be a directory")
            raise PackageError()

        def _remove_ro(f, p, _):
            os.chmod(p, stat.S_IWRITE)
            f(p)

        shutil.rmtree(path, onerror = _remove_ro)

    def find(self, pattern, files = False, root = None):
        rootp = pathlib.Path(root if root else self.destdir)
        for fn in rootp.rglob(pattern):
            if not files or fn.is_file():
                yield fn.relative_to(rootp)

class Subpackage(Package):
    def __init__(self, name, parent):
        super().__init__()

        self.pkgname = name
        self.parent = parent
        self.rparent = parent

        self.short_desc = parent.short_desc
        self.depends = []
        self.make_dirs = []
        self.noverifyrdeps = False
        self.noshlibprovides = False
        self.skiprdeps = []
        self.shlib_requires = []
        self.shlib_provides = []
        self.repository = parent.repository
        self.preserve = False
        self.provides = []
        self.replaces = []
        self.conflicts = []
        self.reverts = []
        self.mutable_files = []
        self.conf_files = []
        self.alternatives = []
        self.tags = []
        self.triggers = []
        self.changelog = None
        self.run_depends = None

        self.force_mode = parent.force_mode
        self.bootstrapping = parent.bootstrapping

    def take(self, *args):
        for p in args:
            if os.path.isabs(p):
                self.logger.out_red(f"path '{p}' must not be absolute!")
                raise PackageError()
            origp = os.path.join(self.parent.destdir, p)
            got = glob.glob(origp)
            if len(got) == 0:
                self.logger.out_red(f"path '{p}' did not match anything!")
                raise PackageError()
            for fullp in got:
                # relative path to the file/dir in original destdir
                pdest = self.parent.destdir
                self.log(f"moving: {fullp} -> {self.destdir}")
                _submove(os.path.relpath(fullp, pdest), self.destdir, pdest)

def from_module(m, ret):
    # fill in required fields
    ret.pkgname = m.pkgname
    ret.version = m.version
    ret.revision = m.revision
    ret.short_desc = m.short_desc
    ret.homepage = m.homepage
    ret.license = m.license

    # basic validation
    ret.ensure_fields()
    ret.validate_version()

    # this is useful so we don't have to repeat ourselves
    ret.pkgver = f"{ret.pkgname}-{ret.version}_{ret.revision}"

    # other fields
    for fld in [
        "archs", "hostmakedepends", "makedepends", "depends",
        "shlib_provides", "shlib_requires", "bootstrap",
        "maintainer", "wrksrc", "build_wrksrc", "create_wrksrc", "patch_args",
        "configure_args", "make_build_args", "make_install_args",
        "make_build_target", "make_install_target",
        "distfiles", "checksum", "skip_extraction", "subpackages", "triggers",
        "broken", "nopie", "noverifyrdeps", "noshlibprovides", "skiprdeps",
        "shlib_requires", "shlib_provides", "make_dirs", "repository",
        "preserve", "provides", "replaces", "conflicts", "reverts",
        "mutable_files", "conf_files", "alternatives", "tags", "changelog",
        "CFLAGS", "CXXFLAGS", "LDFLAGS", "tools", "env", "build_style"
    ]:
        if hasattr(m, fld):
            setattr(ret, fld, getattr(m, fld))

    if not ret.wrksrc:
        ret.wrksrc = f"{ret.pkgname}-{ret.version}"

    ret.validate_arch()

    # also support build_style via string name for nicer syntax
    if isinstance(ret.build_style, str):
        bs = importlib.import_module("cbuild.build_style." + ret.build_style)
        bs.use(ret)

    # perform initialization (will inject build-style etc)
    if hasattr(m, "init"):
        m.init(ret)

    # add our own methods
    for phase in [
        "fetch", "patch", "extract", "configure", "build", "check", "install"
    ]:
        if hasattr(m, "pre_" + phase):
            setattr(ret, "pre_" + phase, getattr(m, "pre_" + phase))
        if hasattr(m, "do_" + phase):
            setattr(ret, "do_" + phase, getattr(m, "do_" + phase))
        if hasattr(m, "post_" + phase):
            setattr(ret, "post_" + phase, getattr(m, "post_" + phase))

    # paths that can be used by template methods
    ret.files_path = pathlib.Path(paths.templates()) / ret.pkgname / "files"
    ret.chroot_files_path = pathlib.Path("/void-packages/srcpkgs") \
        / ret.pkgname / "files"
    ret.patches_path = pathlib.Path(paths.templates()) \
        / ret.pkgname / "patches"
    ret.builddir = pathlib.Path(paths.masterdir()) / "builddir"
    ret.chroot_builddir = pathlib.Path("/builddir")
    ret.destdir_base = pathlib.Path(paths.masterdir()) / "destdir"
    ret.chroot_destdir_base = pathlib.Path("/destdir")
    ret.destdir = ret.destdir_base / f"{ret.pkgname}-{ret.version}"
    ret.chroot_destdir = ret.chroot_destdir_base / f"{ret.pkgname}-{ret.version}"
    ret.abs_wrksrc = pathlib.Path(paths.masterdir()) \
        / "builddir" / ret.wrksrc
    ret.abs_build_wrksrc = ret.abs_wrksrc / ret.build_wrksrc
    ret.chroot_wrksrc = pathlib.Path("/builddir") \
        / ret.wrksrc
    ret.chroot_build_wrksrc = ret.chroot_wrksrc / ret.build_wrksrc
    ret.statedir = ret.builddir / (".xbps-" + ret.pkgname)
    ret.wrapperdir = ret.statedir / "wrappers"

    ret.env["XBPS_STATEDIR"] = "/builddir/.xbps-" + ret.pkgname

    spdupes = {}
    # link subpackages and fill in their fields
    for spn, spf in ret.subpackages:
        if spn in spdupes:
            self.error(f"subpackage '{spn}' already exists")
        spdupes[spn] = True
        sp = Subpackage(spn, ret)
        sp.version = ret.version
        sp.revision = ret.revision
        sp.pkgver = f"{sp.pkgname}-{ret.version}_{ret.revision}"
        sp.destdir = ret.destdir_base / f"{sp.pkgname}-{ret.version}"
        sp.chroot_destdir = ret.chroot_destdir_base / f"{sp.pkgname}-{ret.version}"
        sp.statedir = ret.statedir
        sp.pkg_install = spf(sp)
        ret.subpkg_list.append(sp)

    if ret.broken:
        self.log_red("cannot be built, it's currently broken")
        if isinstance(ret.broken, str):
            ret.error(f"{ret.broken}")
        else:
            ret.error(f"yes")

    # try reading the profile
    if not ret.bootstrapping:
        bp = importlib.import_module(
            "cbuild.build_profiles." + cpu.target()
        )
        if not hasattr(bp, "XBPS_TRIPLET"):
            ret.error(f"no target triplet defined")
        ret.triplet = bp.XBPS_TRIPLET
    else:
        bp = importlib.import_module("cbuild.build_profiles.bootstrap")
        ret.triplet = None

    if hasattr(bp, "XBPS_TARGET_CFLAGS"):
        ret.CFLAGS = bp.XBPS_TARGET_CFLAGS + ret.CFLAGS
    if hasattr(bp, "XBPS_TARGET_CXXFLAGS"):
        ret.CXXFLAGS = bp.XBPS_TARGET_CXXFLAGS + ret.CXXFLAGS
    if hasattr(bp, "XBPS_TARGET_LDFLAGS"):
        ret.LDFLAGS = bp.XBPS_TARGET_LDFLAGS + ret.LDFLAGS

    if hasattr(bp, "XBPS_CFLAGS"):
        ret.CFLAGS = bp.XBPS_CFLAGS + ret.CFLAGS
    if hasattr(bp, "XBPS_CXXFLAGS"):
        ret.CXXFLAGS = bp.XBPS_CXXFLAGS + ret.CXXFLAGS
    if hasattr(bp, "XBPS_LDFLAGS"):
        ret.LDFLAGS = bp.XBPS_LDFLAGS + ret.LDFLAGS

    os.makedirs(ret.statedir, exist_ok = True)
    os.makedirs(ret.wrapperdir, exist_ok = True)

    ret.CFLAGS = ["-O2"] + ret.CFLAGS
    ret.CXXFLAGS = ["-O2"] + ret.CXXFLAGS

    if not "CC" in ret.tools:
        ret.tools["CC"] = "cc"
    if not "CXX" in ret.tools:
        ret.tools["CXX"] = "c++"
    if not "CPP" in ret.tools:
        ret.tools["CPP"] = "cpp"
    if not "LD" in ret.tools:
        ret.tools["LD"] = "ld"
    if not "AR" in ret.tools:
        ret.tools["AR"] = "ar"
    if not "AS" in ret.tools:
        ret.tools["AS"] = "as"
    if not "RANLIB" in ret.tools:
        ret.tools["RANLIB"] = "ranlib"
    if not "STRIP" in ret.tools:
        ret.tools["STRIP"] = "strip"
    if not "OBJDUMP" in ret.tools:
        ret.tools["OBJDUMP"] = "objdump"
    if not "OBJCOPY" in ret.tools:
        ret.tools["OBJCOPY"] = "objcopy"
    if not "NM" in ret.tools:
        ret.tools["NM"] = "nm"
    if not "READELF" in ret.tools:
        ret.tools["READELF"] = "readelf"
    if not "PKG_CONFIG" in ret.tools:
        ret.tools["PKG_CONFIG"] = "pkg-config"

    return ret

def read_pkg(pkgname, force_mode, bootstrapping):
    if not isinstance(pkgname, str):
        logger.get().out_red("Missing package name.")
        raise PackageError()
    if not os.path.isfile(os.path.join("srcpkgs", pkgname, "template")):
        logger.get().out_red("Missing template for '%s'" % cmd[0])
        raise PackageError()

    ret = Template()
    ret.force_mode = force_mode
    ret.bootstrapping = bootstrapping

    def subpkg_deco(spkgname):
        def deco(f):
            ret.subpackages.append((spkgname, f))
        return deco

    setattr(builtins, "subpackage", subpkg_deco)
    setattr(builtins, "bootstrapping", bootstrapping)
    mod = importlib.import_module("srcpkgs." + pkgname + ".template")
    delattr(builtins, "subpackage")
    delattr(builtins, "bootstrapping")

    return from_module(mod, ret)

def register_hooks():
    for step in [
        "fetch", "extract", "patch", "configure", "build", "install", "pkg"
    ]:
        for sstep in ["pre", "do", "post"]:
            stepn = f"{sstep}_{step}"
            dirn = "cbuild/hooks/" + stepn
            if os.path.isdir(dirn):
                for f in glob.glob(os.path.join(dirn, "*.py")):
                    # turn into module name
                    f = f[0:-3].replace("/", ".")
                    hookn = f[f.rfind(".") + 1:]
                    # __init__ is a special case and must be skipped
                    if hookn == "__init__":
                        pass
                    modh = importlib.import_module(f)
                    if not hasattr(modh, "invoke"):
                        logger.get().out_red(
                            f"Hook '{stepn}/{hookn}' does not have an entry point."
                        )
                        raise Exception()
                    hooks[stepn].append((modh.invoke, hookn))
