"""Download and install explicitly selected Argos models from official index.

Run only with --yes; no silent installation or inferred direct DE/RU model.
"""
import argparse
from argostranslate import package

ALLOWED={("de","en"),("en","ru"),("ru","en"),("en","de")}
def install_pivot(*,consent=False):
    if not consent:
        raise ValueError("Explicit approval required")
    package.update_package_index()
    available={(p.from_code,p.to_code):p for p in package.get_available_packages()
               if (p.from_code,p.to_code) in ALLOWED}
    missing=ALLOWED-set(available)
    if missing:
        raise RuntimeError("Missing language packages: "+repr(sorted(missing)))
    installed=[]
    for direction in sorted(ALLOWED):
        p=available[direction]
        filename=p.download()
        package.install_from_path(filename)
        installed.append({"direction":direction,"package":str(p)})
    return installed
if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--yes",action="store_true",help="Approve four model downloads and installations")
    args=parser.parse_args()
    print(install_pivot(consent=args.yes))
