"""Inspect and explicitly install Argos language packages; no silent downloads."""
import argparse
from pathlib import Path

def installed():
    try:
        from argostranslate import translate
    except ImportError:
        return {"available":False,"languages":[],"reason":"argos_package_missing"}
    langs=translate.get_installed_languages()
    return {"available":True,"languages":[{"code":x.code,"name":x.name} for x in langs]}

def candidates():
    try:
        from argostranslate import package
    except ImportError:
        return {"available":False,"packages":[],"reason":"argos_package_missing"}
    package.update_package_index()
    packages=package.get_available_packages()
    return {"available":True,"packages":[{"from":p.from_code,"to":p.to_code,"name":str(p)}
        for p in packages if p.from_code in ("de","ru","en") and p.to_code in ("de","ru","en")]}

def install_file(path, *, consent=False):
    if not consent:
        raise ValueError("Explicit consent required to install a language model")
    p=Path(path)
    if not p.is_file() or p.suffix.lower()!=".argosmodel":
        raise ValueError("Expected existing .argosmodel package")
    from argostranslate import package
    package.install_from_path(str(p))
    return installed()

if __name__=="__main__":
    p=argparse.ArgumentParser(description="Study Argos model manager")
    p.add_argument("action",choices=("installed","candidates","install"))
    p.add_argument("--file")
    p.add_argument("--yes",action="store_true",help="I have reviewed this package and approve installation")
    args=p.parse_args()
    if args.action=="installed":
        print(installed())
    elif args.action=="candidates":
        print(candidates())
    else:
        print(install_file(args.file,consent=args.yes))
