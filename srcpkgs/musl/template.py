pkgname = "musl"
reverts = "1.2.0_1"
version = "1.1.24"
revision = 7
archs = "*-musl"
bootstrap = True
build_style = "gnu_configure"
configure_args = ["--prefix=/usr", "--disable-gcc-wrapper"]
short_desc = "Musl C library"
maintainer = "Enno Boland <gottox@voidlinux.org>"
license = "MIT"
homepage = "http://www.musl-libc.org/"
distfiles = [f"http://www.musl-libc.org/releases/musl-{version}.tar.gz"]
checksum = ["1370c9a812b2cf2a7d92802510cca0058cc37e66a7bedd70051f0a34015022a3"]

shlib_provides = ["libc.so"]

def post_build(self):
    from cbuild.util import compiler
    cc = compiler.C(self)
    cc.invoke([self.chroot_files_path / "getent.c"], "getent")
    cc.invoke([self.chroot_files_path / "getconf.c"], "getconf")
    cc.invoke([self.chroot_files_path / "iconv.c"], "iconv")

def do_install(self):
    self.install_dir("usr/lib")
    # ensure all files go in /usr/lib
    self.install_link("usr/lib", "lib")

    self.make.install()

    # no need for the symlink anymore
    self.unlink("lib")

    self.install_dir("usr/bin")
    self.install_link("../lib/libc.so", "usr/bin/ldd")

    self.install_bin("iconv", "getent", "getconf")

    self.install_man(self.files_path / "getent.1")
    self.install_man(self.files_path / "getconf.1")

    self.install_link("true", "usr/bin/ldconfig")

@subpackage("musl-devel")
def _devel(self):
    self.depends = ["kernel-libc-headers", f"{pkgname}-{version}_{revision}"]
    self.short_desc = short_desc + " - development files"

    def install():
        self.take("usr/include")
        self.take("usr/lib/*.a")
        self.take("usr/lib/*.o")

    return install
