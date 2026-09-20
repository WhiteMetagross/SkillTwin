import importlib
import pkgutil
import shutil

import mediaIntelligence


def main() -> None:
    modules = [
        module.name
        for module in pkgutil.iter_modules(
            mediaIntelligence.__path__, mediaIntelligence.__name__ + "."
        )
    ]
    for module in modules:
        importlib.import_module(module)
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise RuntimeError(f"Container is missing required binary: {binary}")
    print(f"Imported {len(modules)} media runtime modules; ffmpeg and ffprobe are available")


if __name__ == "__main__":
    main()
