"""Bundle the whole standard library, so a yt-dlp newer than the built-in one
finds every module it might import."""
import pkgutil
import sys
import sysconfig

SKIP = {"test", "idlelib", "turtledemo", "lib2to3", "ensurepip", "antigravity", "this", "turtle"}
hiddenimports = [n for n in sys.stdlib_module_names if n not in SKIP]
stdlib = sysconfig.get_paths()["stdlib"]
for info in pkgutil.iter_modules([stdlib]):
    if info.ispkg and info.name in sys.stdlib_module_names and info.name not in SKIP:
        hiddenimports += [m.name for m in pkgutil.walk_packages([f"{stdlib}/{info.name}"], info.name + ".", lambda n: None)
                          if ".test" not in m.name and not m.name.endswith("__main__")]
