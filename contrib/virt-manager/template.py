pkgname = "virt-manager"
pkgver = "4.1.0"
pkgrel = 0
build_style = "python_pep517"
_deps = [
    "libxml2-python",
    "libosinfo",
    "python-libvirt",
    "python-gobject",
    "python-requests",
    "qemu-img",
]
hostmakedepends = [
    "gettext",
    "gtk-update-icon-cache",
    "python-build",
    "python-docutils",
    "python-installer",
    "python-setuptools",
    "python-wheel",
]
depends = [
    "gtk-vnc",
    "gtksourceview4",
    "libvirt-glib",
    "spice-gtk",
    "virt-manager-tools",
    "vte-gtk3",
]
checkdepends = ["python-pytest", "xorriso"] + _deps
pkgdesc = "GUI for managing virtual machines"
maintainer = "cesorious <cesorious@gmail.com>"
license = "GPL-2.0-or-later"
url = "https://virt-manager.org"
source = (
    f"https://releases.pagure.org/virt-manager/virt-manager-{pkgver}.tar.gz"
)
sha256 = "950681d7b32dc61669278ad94ef31da33109bf6fcf0426ed82dfd7379aa590a2"


def do_build(self):
    self.do(
        "python3",
        "setup.py",
        "build",
    )


def do_check(self):
    self.do(
        "python",
        "-m",
        "pytest",
        "-k",
        "not testDASDMdev "
        "and not testAPQNMdev "
        "and not testPCIMdev "
        "and not testPCIMdevNewFormat "
        "and not testCLI0001virt_install_many_devices "
        "and not testCLI0057virt_install_osinfo_url "
        "and not testCLI0079virt_install_osinfo_url_with_disk "
        "and not testCLI0114virt_install_osinfo_url_unattended "
        "and not testCLI0115virt_install_osinfo_unattended_treeapis "
        "and not testCLI0261virt_xml "
        "and not testCLI0284virt_xml_edit_cpu_host_copy "
        "and not testCLI0366virt_xml_add_hostdev_mdev "
        "and not testCLI0374virt_xml_add_hostdev_mdev_start "
        "and not testcli0168virt_install_s390x_cdrom "
        "and not testcli0394virt_clone_auto_unmanaged "
        "and not testcli0397virt_clone "
        "and not testcli0398virt_clone "
        "and not testcli0412virt_clone "
        "and not testcli0413virt_clone "
        "and not testcli0415virt_clone "
        "and not testcli0416virt_clone "
        "and not testcli0424virt_clone",
    )


def do_install(self):
    self.do("python", "setup.py", "install", f"--root={self.chroot_destdir}")


@subpackage("virt-manager-tools")
def _tools(self):
    self.depends = list(_deps)
    self.pkgdesc = "Programs to create and clone virtual machines"

    return [
        "usr/bin/virt-clone",
        "usr/bin/virt-install",
        "usr/bin/virt-xml",
        "usr/share/man/man1/virt-install.1",
        "usr/share/man/man1/virt-clone.1",
        "usr/share/man/man1/virt-xml.1",
        "usr/share/virt-manager/virtinst",
        "usr/share/bash-completion/completions/virt-install",
        "usr/share/bash-completion/completions/virt-clone",
        "usr/share/bash-completion/completions/virt-xml",
    ]