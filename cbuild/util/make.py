_jobs = 1

def set_jobs(nj):
    global _jobs
    _jobs = nj

def jobs():
    return _jobs

class Make:
    def __init__(self, tmpl, jobs = None, command = "make", env = {}):
        self.template = tmpl
        self.command = command
        self.env = env
        if not jobs:
            self.jobs = _jobs
        else:
            self.jobs = jobs

    def invoke(self, target = None, args = [], jobs = None, env = {}):
        renv = dict(self.env)
        renv.update(env)

        if not jobs:
            jobs = self.jobs

        argsbase = ["-j" + str(jobs)]

        if target and len(target) > 0:
            argsbase.append(target)

        argsbase += args

        return self.template.do(
            self.command, argsbase, build = True, env = renv
        )

    def build(self, args = [], jobs = None, env = {}):
        pkg = self.template
        return self.invoke(
            pkg.make_build_target, pkg.make_build_args + args, jobs, env
        )

    def install(self, args = [], jobs = None, env = {}, default_args = True):
        pkg = self.template
        argsbase = []

        if default_args:
            argsbase.append("DESTDIR=" + str(pkg.chroot_destdir))

        argsbase += pkg.make_install_args
        argsbase += args

        return self.invoke(pkg.make_install_target, argsbase, jobs, env)
