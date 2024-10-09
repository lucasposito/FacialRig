import os
import sys
from pathlib import Path, PurePath

try:
    from maya import cmds, mel
    from maya.api import OpenMaya

    is_maya = True

except ImportError():
    is_maya = False


def onMayaDroppedPythonFile(*args, **kwargs):
    """
    This function is only supported since Maya 2017 Update 3.
    Maya requires this in order to successfully execute.
    """
    pass


def _dropped_install():
    local_path = Path(__file__).parent.absolute()

    maya_mod_path = Path(os.path.join(os.environ['MAYA_APP_DIR'], 'modules'))
    maya_mod_path = maya_mod_path / 'FacialRig.mod'

    mod_file = open(str(maya_mod_path), 'w')
    mod_file.write('+ FacialRig 1.0 {}\n'.format(PurePath(local_path).as_posix()))
    mod_file.write('scripts: {}'.format(PurePath(local_path).as_posix()))
    mod_file.close()

    sys.path.append(local_path)


if is_maya:
    _dropped_install()
