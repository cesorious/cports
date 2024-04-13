pkgname = "qt6-qtspeech"
pkgver = "6.7.1"
pkgrel = 0
build_style = "cmake"
hostmakedepends = ["cmake", "ninja", "pkgconf"]
# FIXME: package Speech Dispatcher / Flite for an actual text-to-speech engine!
# QINFO  : tst_QVoice::initTestCase() Available text-to-speech engines:
# SKIP   : tst_QVoice::initTestCase() No speech engines available, skipping test case
makedepends = [
    "alsa-lib-devel",
    "qt6-qtdeclarative-devel",
    "qt6-qtmultimedia-devel",
]
pkgdesc = "Qt6 Speech component"
maintainer = "Jami Kettunen <jami.kettunen@protonmail.com>"
license = (
    "LGPL-2.1-only AND LGPL-3.0-only AND GPL-3.0-only WITH Qt-GPL-exception-1.0"
)
url = "https://www.qt.io"
source = f"https://download.qt.io/official_releases/qt/{pkgver[:-2]}/{pkgver}/submodules/qtspeech-everywhere-src-{pkgver}.tar.xz"
sha256 = "6c6f1d15c8fc0ef5cb0cfc401a07ecc56e34f1e8510126383cef658cf751eb88"
# FIXME?
hardening = ["!int"]
# TODO
options = ["!cross"]


def init_check(self):
    self.make_check_env = {
        "QT_QPA_PLATFORM": "offscreen",
        "QML2_IMPORT_PATH": str(
            self.chroot_cwd / f"{self.make_dir}/lib/qt6/qml"
        ),
    }


def post_install(self):
    self.rm(self.destdir / "usr/tests", recursive=True)


@subpackage("qt6-qtspeech-devel")
def _devel(self):
    self.depends += [
        f"qt6-qtbase-devel~{pkgver[:-2]}",
        f"qt6-qtdeclarative-devel~{pkgver[:-2]}",
        f"qt6-qtmultimedia-devel~{pkgver[:-2]}",
    ]
    return self.default_devel(
        extra=[
            "usr/lib/qt6/metatypes",
            "usr/lib/qt6/mkspecs",
            "usr/lib/qt6/modules",
            "usr/lib/*.prl",
        ]
    )